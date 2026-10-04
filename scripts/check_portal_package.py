#!/usr/bin/env python3
"""Run the Future Tech Portal package inside a real Home Assistant core.

This needs the ``homeassistant`` package (Python 3.13), so it is not part of
the release gate; run it when the package changes:

    uv venv --python 3.13 /tmp/ha && VIRTUAL_ENV=/tmp/ha uv pip install homeassistant
    /tmp/ha/bin/python scripts/check_portal_package.py

It loads the generated package through Home Assistant's own configuration
loader (packages and !secret included), registers fake devices from several
integrations, points rest_command at a local mock portal, and checks every
request: inventory chunks and categories, offline/recovered debounce, the
daily low-battery cap, heartbeats, error notifications, and the 401 pause.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import MappingProxyType
from unittest.mock import patch

from aiohttp import web
from aiohttp.resolver import ThreadedResolver

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "future_homes_tech_app"))

import fht_portal  # noqa: E402

from homeassistant import config as conf_util, config_entries, loader  # noqa: E402
from homeassistant.components import persistent_notification  # noqa: E402
from homeassistant.core import CoreState, HomeAssistant  # noqa: E402
from homeassistant.helpers import (  # noqa: E402
    area_registry as ar,
    category_registry as cr,
    condition,
    device_registry as dr,
    entity,
    entity_registry as er,
    floor_registry as fr,
    issue_registry as ir,
    label_registry as lr,
    restore_state as rs,
    translation,
    trigger,
)
from homeassistant.setup import async_setup_component  # noqa: E402

TOKEN = "Bearer fts_testtoken1234"
FAILURES: list[str] = []


def check(condition_met: bool, message: str) -> None:
    print(("ok   " if condition_met else "FAIL ") + message)
    if not condition_met:
        FAILURES.append(message)


class _Resolver(ThreadedResolver):
    """aiohttp's resolver with the close hook Home Assistant calls at shutdown."""

    async def real_close(self) -> None:
        await self.close()


class MockPortal:
    """Record each POST and answer with the next queued status (default 200)."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.statuses: list[int] = []

    async def handle(self, request: web.Request) -> web.Response:
        body = await request.read()
        self.requests.append(
            {
                "authorization": request.headers.get("Authorization"),
                "content_type": request.headers.get("Content-Type"),
                "size": len(body),
                "json": json.loads(body.decode("utf-8")),
            }
        )
        status = self.statuses.pop(0) if self.statuses else 200
        return web.json_response({"accepted": 1, "devices": 0, "duplicates": 0}, status=status)

    def take(self) -> list[dict]:
        taken, self.requests = self.requests, []
        return taken


async def make_hass(config_dir: Path) -> HomeAssistant:
    hass = HomeAssistant(str(config_dir))
    hass.config.skip_pip = True
    await hass.config.async_set_time_zone("America/Chicago")
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    entity.async_setup(hass)
    loader.async_setup(hass)
    await condition.async_setup(hass)
    await trigger.async_setup(hass)
    hass.data[translation.TRANSLATION_FLATTEN_CACHE] = translation._TranslationCache(hass)
    with patch("homeassistant.helpers.restore_state.RestoreStateData.async_setup_dump"), patch(
        "homeassistant.helpers.restore_state.start.async_at_start"
    ):
        for registry in (ar, cr, dr, er, fr, ir, lr, rs):
            await registry.async_load(hass)
    hass.set_state(CoreState.running)
    return hass


def add_entry(hass: HomeAssistant, domain: str) -> config_entries.ConfigEntry:
    entry = config_entries.ConfigEntry(
        data={},
        discovery_keys=MappingProxyType({}),
        domain=domain,
        minor_version=1,
        options={},
        source="user",
        subentries_data=None,
        title=f"{domain} entry",
        unique_id=None,
        version=1,
    )
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


async def main() -> int:
    # Short debounce and start-up window so the run takes seconds, not minutes.
    fht_portal.OFFLINE_DEBOUNCE_SECONDS = 2
    fht_portal.SPREAD_SECONDS = 1
    fht_portal.STARTUP_SECONDS = 0

    portal = MockPortal()
    app = web.Application()
    app.router.add_post("/api/beta/ingest", portal.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    config_dir = Path(tempfile.mkdtemp())
    (config_dir / "packages").mkdir()
    (config_dir / "configuration.yaml").write_text(
        "homeassistant:\n  packages: !include_dir_named packages\n"
        # One ordinary automation of the home, for the activity reports.
        "automation:\n"
        "  - id: porch_lights_at_sunset\n"
        "    alias: Porch lights at sunset\n"
        "    triggers:\n"
        "      - trigger: event\n"
        "        event_type: test_porch\n"
        "    actions:\n"
        "      - delay: 0\n",
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text(
        fht_portal.with_token("other_secret: keep-me\n", TOKEN), encoding="utf-8"
    )
    package = fht_portal.render_package([*fht_portal.DEFAULT_INTEGRATIONS])
    check("!secret future_tech_token" in package and "fts_" not in package, "package reads the token only through !secret")
    package = package.replace(fht_portal.INGEST_URL, f"http://127.0.0.1:{port}/api/beta/ingest")
    (config_dir / "packages" / fht_portal.PACKAGE_FILENAME).write_text(package, encoding="utf-8")

    hass = await make_hass(config_dir)
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    labels = lr.async_get(hass)
    sources: dict[str, dict] = {}
    entries = {domain: add_entry(hass, domain) for domain in (*fht_portal.DEFAULT_INTEGRATIONS, "hue")}

    def device(domain: str, key: str, **info):
        return devices.async_get_or_create(
            config_entry_id=entries[domain].entry_id, identifiers={(domain, key)}, **info
        )

    def add(domain: str, entity_id: str, device_entry, state: str, **attributes):
        platform_domain, object_id = entity_id.split(".", 1)
        entities.async_get_or_create(
            platform_domain, domain, object_id, suggested_object_id=object_id,
            device_id=device_entry.id if device_entry else None,
            config_entry=entries[domain] if device_entry else None,
        )
        sources[entity_id] = {"domain": domain}
        hass.states.async_set(entity_id, state, attributes)

    coordinator = device("zha", "coordinator", name="Zigbee Coordinator", manufacturer="Nabu Casa", model="SkyConnect")
    add("zha", "sensor.zigbee_coordinator_rssi", coordinator, "-60")
    motion = device("zha", "motion", name="Hall Motion", manufacturer="Aqara", model="RTCGQ11LM",
                    sw_version="0x00000005", hw_version="1", via_device=("zha", "coordinator"))
    add("zha", "binary_sensor.hall_motion", motion, "off", device_class="motion")
    add("zha", "sensor.hall_motion_battery", motion, "45", device_class="battery")
    add("zha", "update.hall_motion_firmware", motion, "off")
    light = device("zha", "light", name="Kitchen Light", manufacturer="IKEA", model="LED1545G12",
                   via_device=("zha", "coordinator"))
    add("zha", "light.kitchen", light, "on")
    add("zha", "update.kitchen_firmware", light, "on")
    lock = device("zwave_js", "lock", name="Front Door Lock", manufacturer="Yale", model="YRD256")
    add("zwave_js", "lock.front_door", lock, "locked")
    add("zwave_js", "sensor.front_door_lock_battery", lock, "62", device_class="battery")
    nvr = device("unifiprotect", "nvr", name="UNVR", manufacturer="Ubiquiti", model="UNVR")
    add("unifiprotect", "sensor.unvr_storage", nvr, "40")
    camera = device("unifiprotect", "cam", name="Driveway", manufacturer="Ubiquiti", model="G5 Bullet",
                    via_device=("unifiprotect", "nvr"))
    add("unifiprotect", "camera.driveway", camera, "idle")
    add("unifiprotect", "binary_sensor.driveway_motion", camera, "off")
    doorbell = device("unifiprotect", "bell", name="Front Doorbell", manufacturer="Ubiquiti",
                      model="G4 Doorbell Pro", via_device=("unifiprotect", "nvr"))
    add("unifiprotect", "camera.front_doorbell", doorbell, "idle")
    access_point = device("unifi", "ap", name="Living Room Access Point", manufacturer="Ubiquiti Networks", model="U6-Pro")
    add("unifi", "sensor.living_room_ap_uptime", access_point, "2026-10-01T00:00:00+00:00")
    add("unifi", "update.living_room_ap", access_point, "off")
    phone = device("unifi", "phone", name="Someone's Phone", manufacturer="Apple")
    add("unifi", "device_tracker.phone", phone, "home")
    plug = device("esphome", "plug", name="Garage Plug", manufacturer="Espressif", model="ESP32")
    add("esphome", "switch.garage_plug", plug, "unavailable")
    add("esphome", "button.garage_plug_restart", plug, "unknown")
    hue_bridge = device("hue", "bridge", name="Hue Bridge", manufacturer="Signify", model="BSB002")
    add("hue", "binary_sensor.hue_bridge_connected", hue_bridge, "on")
    skipped = device("zha", "skip", name="Leak Sensor", manufacturer="Aqara")
    add("zha", "binary_sensor.leak_sensor", skipped, "off")
    disabled = device("zha", "disabled", name="Old Sensor", manufacturer="Aqara")
    add("zha", "binary_sensor.old_sensor", disabled, "off")
    devices.async_update_device(disabled.id, disabled_by=dr.DeviceEntryDisabler.USER)
    for index in range(320):
        bulk = device("mqtt", f"bulk{index}", name=f"Temperature {index:03d} é", manufacturer="Sonoff", model="SNZB-02")
        add("mqtt", f"sensor.temperature_{index:03d}", bulk, "21.5", device_class="temperature")
    add("zha", "sensor.weather_station", None, "12")

    include = labels.async_create(fht_portal.INCLUDE_LABEL)
    exclude = labels.async_create(fht_portal.EXCLUDE_LABEL)
    devices.async_update_device(hue_bridge.id, labels={include.label_id})
    devices.async_update_device(skipped.id, labels={exclude.label_id})
    entities.async_update_entity("sensor.weather_station", labels={include.label_id})

    def entity_sources(_hass):
        return {
            entity_id: info
            for entity_id, info in sources.items()
            if (registry_entry := entities.async_get(entity_id)) is None or not registry_entry.disabled
        }

    # No zeroconf in this bare instance: resolve the mock portal with aiohttp's own resolver.
    with patch("homeassistant.helpers.entity.entity_sources", entity_sources), patch(
        "homeassistant.helpers.aiohttp_client._async_make_resolver", lambda _hass: _Resolver()
    ):
        config = await conf_util.async_hass_config_yaml(hass)
        for domain in ("homeassistant", "persistent_notification", "rest_command", "template", "script", "automation"):
            check(await async_setup_component(hass, domain, config), f"{domain} sets up from the package")
        await hass.async_block_till_done()

        def notification() -> str | None:
            item = persistent_notification._async_get_or_create_notifications(hass).get(
                "future_tech_portal_error"
            )
            return f"{item['title']}|{item['message']}" if item else None

        # --- inventory -----------------------------------------------------
        await hass.services.async_call("script", "future_tech_send_inventory", blocking=True)
        await hass.async_block_till_done()
        requests = portal.take()
        automation_requests = [r for r in requests if r["json"]["kind"] == "automations"]
        requests = [r for r in requests if r["json"]["kind"] != "automations"]
        check(len(automation_requests) == 1, "the inventory also sends the automations list")
        if automation_requests:
            listed = automation_requests[0]["json"]["automations"]
            check([a["automationId"] for a in listed] == ["automation.porch_lights_at_sunset"], f"automations list leaves out the portal's own ({[a['automationId'] for a in listed]})")
            check(listed[0] == {"automationId": "automation.porch_lights_at_sunset", "name": "Porch lights at sunset", "enabled": True, "configId": "porch_lights_at_sunset"}, f"automation entry fields ({listed[0]})")
        check(len(requests) == 1, f"inventory of 331 devices sent in one request (got {len(requests)})")
        check(all(r["authorization"] == TOKEN for r in requests), "Authorization header is the secret value")
        check(all(r["content_type"] == "application/json" for r in requests), "Content-Type is application/json")
        check(all(r["json"]["kind"] == "inventory" for r in requests), "kind is inventory")
        check(all(len(r["json"]["devices"]) <= 500 for r in requests), "each request has at most 500 devices")
        check(all(r["size"] < 256 * 1024 for r in requests), "each request is under 256 KB")
        sent = {d["externalId"]: d for r in requests for d in r["json"]["devices"]}
        check(len(sent) == 331, f"331 devices reported (got {len(sent)})")
        expected = {
            coordinator.id: "hub", motion.id: "sensor", light.id: "other", lock.id: "access",
            nvr.id: "hub", camera.id: "camera", doorbell.id: "access", access_point.id: "network",
            plug.id: "other", hue_bridge.id: "hub",
        }
        for device_id, category in expected.items():
            got = sent.get(device_id, {}).get("category")
            check(got == category, f"{sent.get(device_id, {}).get('name')} category {category} (got {got})")
        check(phone.id not in sent, "UniFi client devices are not reported")
        check(skipped.id not in sent, "devices labeled future_tech_exclude are skipped")
        check(disabled.id not in sent, "disabled devices are skipped")
        check("sensor.weather_station" in sent, "a labeled entity without a device uses its entity_id")
        check(sent[motion.id].get("integration") == "zha" and sent[motion.id].get("integrationName") == "zha entry", f"integration of a ZHA device ({sent[motion.id].get('integration')}, {sent[motion.id].get('integrationName')})")
        check(sent[camera.id].get("integration") == "unifiprotect" and sent[access_point.id].get("integration") == "unifi", "integration of Protect and UniFi Network devices")
        check(sent[hue_bridge.id].get("integration") == "hue", "a labeled device from another integration names it")
        check("integrations" not in sent[motion.id], "integrations list only when a device has more than one")
        check("integration" not in sent["sensor.weather_station"], "an entity with no integration entry leaves it out")
        check(sent[motion.id].get("battery") == 45, "battery comes from the device's battery sensor")
        check(sent[motion.id].get("firmwareUpdateAvailable") is False, "update entity off -> no firmware update")
        check(sent[light.id].get("firmwareUpdateAvailable") is True, "update entity on -> firmware update available")
        check(sent[motion.id].get("firmware") == "0x00000005" and sent[motion.id].get("hardware") == "1", "firmware/hardware from the device")
        check(sent[motion.id].get("manufacturer") == "Aqara" and sent[motion.id].get("model") == "RTCGQ11LM", "manufacturer/model from the device")
        check(sent[plug.id]["online"] is False and sent[motion.id]["online"] is True, "online is false only when the main entity is unavailable")
        check(all("lastSeenAt" in d for d in sent.values()), "every device has lastSeenAt")
        check("battery" not in sent[light.id] and "manufacturer" not in sent["sensor.weather_station"], "missing values are left out")
        status = hass.states.get(fht_portal.STATUS_SENSOR)
        check(status is not None and status.state == "200" and status.attributes.get("ok") is True, "status sensor shows 200")
        check(bool(status and status.attributes.get("last_inventory")), "status sensor records the last inventory")
        monitored_state = hass.states.get(fht_portal.DEVICES_SENSOR)
        monitored = monitored_state.attributes.get("monitored") if monitored_state else []
        check(monitored_state is not None and monitored_state.state == "331", "devices sensor counts 331 devices")
        check("binary_sensor.hall_motion" in monitored and "sensor.hall_motion_battery" not in monitored, "motion sensor's main entity is the binary sensor, not the battery")

        # --- activity ------------------------------------------------------
        hass.bus.async_fire("test_porch")
        await asyncio.sleep(1.5)
        await hass.async_block_till_done()
        requests = portal.take()
        check(len(requests) == 1, f"an automation run sends one activity report (got {len(requests)})")
        if requests:
            event = requests[0]["json"]["events"][0]
            check(event["type"] == "automation.triggered" and event["automationId"] == "automation.porch_lights_at_sunset"
                  and event["name"] == "Porch lights at sunset" and event["source"] == "event 'test_porch'"
                  and event["eventId"] and event["occurredAt"], f"activity event fields ({event})")

        # --- heartbeat -----------------------------------------------------
        await hass.services.async_call(
            "automation", "trigger", {"entity_id": "automation.future_tech_heartbeat"}, blocking=True
        )
        await hass.async_block_till_done()
        requests = portal.take()
        check(len(requests) == 1, "heartbeat sends one request")
        if requests:
            event = requests[0]["json"]["events"][0]
            check(requests[0]["json"]["kind"] == "events" and event["type"] == "heartbeat", "heartbeat payload kind/type")
            check(event["eventId"].startswith("hb-") and set(event) == {"eventId", "type", "occurredAt"}, "heartbeat eventId hb-<timestamp>, no extra keys")

        # --- offline / recovered -------------------------------------------
        hass.states.async_set("binary_sensor.hall_motion", "unavailable", {"device_class": "motion"})
        await asyncio.sleep(0.5)
        hass.states.async_set("binary_sensor.hall_motion", "off", {"device_class": "motion"})
        await asyncio.sleep(3.5)
        await hass.async_block_till_done()
        check(portal.take() == [], "a blip shorter than the debounce sends nothing")
        hass.states.async_set("binary_sensor.hall_motion", "unavailable", {"device_class": "motion"})
        await asyncio.sleep(4)
        await hass.async_block_till_done()
        requests = portal.take()
        types = [r["json"]["events"][0]["type"] for r in requests]
        check(types == ["device.offline"], f"offline after the debounce (got {types})")
        if requests:
            event = requests[0]["json"]["events"][0]
            check(event["externalId"] == motion.id and event["eventId"] and event["occurredAt"], "offline event fields")
        hass.states.async_set("binary_sensor.hall_motion", "off", {"device_class": "motion"})
        await asyncio.sleep(2)
        await hass.async_block_till_done()
        types = [r["json"]["events"][0]["type"] for r in portal.take()]
        check(types == ["device.recovered"], f"recovered when it returns (got {types})")
        hass.states.async_set("sensor.hall_motion_battery", "unavailable", {"device_class": "battery"})
        await asyncio.sleep(3)
        await hass.async_block_till_done()
        check(portal.take() == [], "a non-main entity going unavailable sends nothing")

        # --- low battery ---------------------------------------------------
        hass.states.async_set("sensor.hall_motion_battery", "15", {"device_class": "battery"})
        await asyncio.sleep(1.5)
        await hass.async_block_till_done()
        requests = portal.take()
        check(len(requests) == 1, "battery below 20% sends battery.low")
        if requests:
            event = requests[0]["json"]["events"][0]
            check(event["type"] == "battery.low" and event["batteryPercent"] == 15 and event["externalId"] == motion.id, "battery.low fields")
        hass.states.async_set("sensor.hall_motion_battery", "14", {"device_class": "battery"})
        await asyncio.sleep(1.5)
        await hass.async_block_till_done()
        check(portal.take() == [], "second low reading the same day sends nothing")

        # --- errors and the 401 pause -------------------------------------
        portal.statuses = [500]
        await hass.services.async_call("automation", "trigger", {"entity_id": "automation.future_tech_heartbeat"}, blocking=True)
        await hass.async_block_till_done()
        portal.take()
        check(notification() == "Future Tech Portal|Report failed: HTTP 500", f"HTTP 500 notification shows the status only (got {notification()})")
        check(hass.states.get(fht_portal.STATUS_SENSOR).attributes.get("paused") is False, "a 5xx does not pause reporting")
        portal.statuses = [401]
        await hass.services.async_call("automation", "trigger", {"entity_id": "automation.future_tech_heartbeat"}, blocking=True)
        await hass.async_block_till_done()
        portal.take()
        check(hass.states.get(fht_portal.STATUS_SENSOR).attributes.get("paused") is True, "a 401 pauses automatic reports")
        await hass.services.async_call(
            "automation", "trigger", {"entity_id": "automation.future_tech_heartbeat", "skip_condition": False}, blocking=True
        )
        await hass.async_block_till_done()
        check(portal.take() == [], "paused: the scheduled heartbeat sends nothing")
        await hass.services.async_call("script", "future_tech_send_inventory", blocking=True)
        await hass.async_block_till_done()
        check(len(portal.take()) == 2, "a manual inventory (devices and automations) still sends while paused")
        status = hass.states.get(fht_portal.STATUS_SENSOR)
        check(status.attributes.get("paused") is False and notification() is None, "success clears the pause and the notification")
        notified_text = json.dumps(persistent_notification._async_get_or_create_notifications(hass), default=str)
        check("fts_" not in notified_text, "no notification contains the token")

        await runner.cleanup()
        await hass.services.async_call("automation", "trigger", {"entity_id": "automation.future_tech_heartbeat"}, blocking=True)
        await hass.async_block_till_done()
        check(notification() == "Future Tech Portal|Report failed: no response from the portal", f"unreachable portal notification (got {notification()})")

        await hass.async_stop(force=True)

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
