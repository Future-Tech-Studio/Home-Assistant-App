#!/usr/bin/env python3
"""Ingress web server for Future Homes Tech App."""

from __future__ import annotations

from collections import deque
import copy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import gzip
import hashlib
import importlib.util
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import traceback
from typing import Any, Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

_access_spec = importlib.util.spec_from_file_location("fht_access", Path(__file__).with_name("fht_access.py"))
ACCESS = importlib.util.module_from_spec(_access_spec)
_access_spec.loader.exec_module(ACCESS)

_maintenance_spec = importlib.util.spec_from_file_location("fht_maintenance", Path(__file__).with_name("fht_maintenance.py"))
MAINTENANCE = importlib.util.module_from_spec(_maintenance_spec)
_maintenance_spec.loader.exec_module(MAINTENANCE)

_catalog_spec = importlib.util.spec_from_file_location("fht_catalog", Path(__file__).with_name("fht_catalog.py"))
CATALOG = importlib.util.module_from_spec(_catalog_spec)
_catalog_spec.loader.exec_module(CATALOG)

_beta_spec = importlib.util.spec_from_file_location("fht_beta", Path(__file__).with_name("fht_beta.py"))
BETA = importlib.util.module_from_spec(_beta_spec)
_beta_spec.loader.exec_module(BETA)

_site_spec = importlib.util.spec_from_file_location("fht_site", Path(__file__).with_name("fht_site.py"))
SITE = importlib.util.module_from_spec(_site_spec)
_site_spec.loader.exec_module(SITE)
# Values that differ between Future Homes Tech homes come from the site
# profile (site_profile.json, overridden by /data/site_profile.json), read once
# at start. docs/SITE_PROFILE.md describes every key.
SITE_PROFILE = SITE.load_site_profile()

_history_spec = importlib.util.spec_from_file_location("fht_history", Path(__file__).with_name("fht_history.py"))
HISTORY = importlib.util.module_from_spec(_history_spec)
_history_spec.loader.exec_module(HISTORY)
# Saved versions of every settings file in /data, so a page can undo a change.
SETTINGS_HISTORY = HISTORY.SettingsHistory()

_portal_spec = importlib.util.spec_from_file_location("fht_portal", Path(__file__).with_name("fht_portal.py"))
PORTAL = importlib.util.module_from_spec(_portal_spec)
_portal_spec.loader.exec_module(PORTAL)

_ha_client_spec = importlib.util.spec_from_file_location("fht_ha_client", Path(__file__).with_name("fht_ha_client.py"))
HA_CLIENT = importlib.util.module_from_spec(_ha_client_spec)
_ha_client_spec.loader.exec_module(HA_CLIENT)
# The Home Assistant WebSocket client lives in fht_ha_client.py; these names
# keep working for the code and tests that still use them from here.
HomeAssistantAPIError = HA_CLIENT.HomeAssistantAPIError
WebSocketProtocolError = HA_CLIENT.WebSocketProtocolError
MAX_WEBSOCKET_MESSAGE_SIZE = HA_CLIENT.MAX_WEBSOCKET_MESSAGE_SIZE
_read_exact = HA_CLIENT._read_exact
_send_websocket_frame = HA_CLIENT._send_websocket_frame
_receive_websocket_frame = HA_CLIENT._receive_websocket_frame
_receive_websocket_json = HA_CLIENT._receive_websocket_json
_send_websocket_json = HA_CLIENT._send_websocket_json
_open_websocket = HA_CLIENT._open_websocket
_PooledWebSocket = HA_CLIENT._PooledWebSocket
_WebSocketCommandRejected = HA_CLIENT._WebSocketCommandRejected
_WEBSOCKET_POOL = HA_CLIENT._WEBSOCKET_POOL
execute_websocket_commands = HA_CLIENT.execute_websocket_commands

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8099
DEFAULT_HOME_ASSISTANT_STATES_URL = (
    "http://supervisor/core/api/states"
)
DEFAULT_HOME_ASSISTANT_WEBSOCKET_URL = (
    "ws://supervisor/core/websocket"
)
DEFAULT_HOME_ASSISTANT_SERVICES_URL = (
    "http://supervisor/core/api/services"
)
ENTITY_CACHE_FALLBACK_TTL_SECONDS = 60
ENTITY_EVENT_HISTORY_LIMIT = 512
ENTITY_LIVE_RECONNECT_MAX_SECONDS = 30
APP_INFO_CACHE_TTL_SECONDS = 60
PHONE_NOTIFY_CACHE_TTL_SECONDS = 300
PHONE_NOTIFY_SERVICE_PREFIX = "notify.mobile_app_"
BETA_INSTALL_LOCK = threading.Lock()
PROTECT_ARM_CACHE_TTL_SECONDS = 15
PROTECT_NVR_CACHE_TTL_SECONDS = 60
PROTECT_RESOURCE_CACHE_TTL_SECONDS = 300
HTTP_MAX_WORKERS = 16
HTTP_MAX_LIVE_WAITERS = 8
HTTP_REQUEST_TIMEOUT_SECONDS = 35
DEFAULT_SUPERVISOR_APP_INFO_URL = "http://supervisor/addons/self/info"
DEFAULT_PROTECT_WEBHOOK_URL = SITE_PROFILE.protect_webhook_url("device_offline")
DEFAULT_WEATHER_ENTITY = str(SITE_PROFILE.get("weather_entity"))
HIDDEN_SETUP_AREAS = frozenset(SITE_PROFILE.get("rooms.hidden_areas"))
DEVICE_ALARM_ROOM_NAMES = frozenset(SITE_PROFILE.get("rooms.device_alarm_room_names"))
SLEEP_SOURCE_EXCLUDED_WORDS = tuple(SITE_PROFILE.get("rooms.sleep_source_excluded_words"))
CATALOG_RETIRED_UNAVAILABLE_LIGHTS = tuple(SITE_PROFILE.get("catalog.retired_unavailable_lights"))
CATALOG_INDICATOR_LIGHT_PATTERN = str(SITE_PROFILE.get("catalog.indicator_light_pattern"))
DEFAULT_INGRESS_PROXY_IP = "172.30.32.2"
DEFAULT_WEB_ROOT = Path("/opt/future-homes-tech/web")
INTERFACE_ASSETS = {
    "/app-background-red.webp": ("app-background-red.webp", "image/webp"),
    "/app-background-green.webp": ("app-background-green.webp", "image/webp"),
    "/app-logo-red.png": ("app-logo-red.png", "image/png"),
    "/app-logo-green.png": ("app-logo-green.png", "image/png"),
    "/maintenance.js": ("maintenance.js", "text/javascript; charset=utf-8"),
    "/maintenance.css": ("maintenance.css", "text/css; charset=utf-8"),
    "/users-access.js": ("users-access.js", "text/javascript; charset=utf-8"),
    "/users-access.css": ("users-access.css", "text/css; charset=utf-8"),
    "/future-homes-tech-logo.png": (
        "future-homes-tech-logo.png",
        "image/png",
    ),
    "/fht-infinite-vertical-warp-4da39efb.webp": (
        "fht-infinite-vertical-warp-4da39efb.webp",
        "image/webp",
    ),
}
DEFAULT_HOME_ASSISTANT_CONFIG_DIR = Path("/homeassistant")
DEFAULT_SWITCH_ASSIGNMENTS_PATH = Path(
    "/data/switch_light_group_assignments.json"
)
DEFAULT_SWITCH_CONTROL_SETTINGS_PATH = Path(
    "/data/switch_control_settings.json"
)
DEFAULT_CONTROL_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_control_automations.yaml"
)
DEFAULT_ROOM_ALIASES_PATH = Path("/data/room_aliases.json")
DEFAULT_DOOR_ASSIGNMENTS_PATH = Path("/data/door_light_group_assignments.json")
DEFAULT_PRESENCE_ASSIGNMENTS_PATH = Path(
    "/data/presence_light_group_assignments.json"
)
DEFAULT_PRESENCE_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_presence_automations.yaml"
)
DEFAULT_PRESENCE_GROUPS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_presence_groups.yaml"
)
DEFAULT_PRESENCE_TIMINGS_PATH = Path("/data/presence_light_group_timings.json")
DEFAULT_PRESENCE_MODE_SETTINGS_PATH = Path(
    "/data/presence_mode_settings.json"
)
DEFAULT_FRIDGE_ALARM_SETTINGS_PATH = Path("/data/fridge_alarm_settings.json")
DEFAULT_FRIDGE_ALARM_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_fridge_alarm_automations.yaml"
)
DEFAULT_DOOR_OPEN_ALERT_SETTINGS_PATH = Path("/data/door_open_alert_settings.json")
DEFAULT_FUTURE_TECH_PORTAL_SETTINGS_PATH = Path("/data/future_tech_portal_settings.json")
DEFAULT_DOOR_OPEN_ALERT_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_door_open_alerts.yaml"
)
DEFAULT_LIGHT_SCHEDULES_PATH = Path("/data/light_schedules.json")
DEFAULT_LIGHT_SCHEDULE_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_light_schedule_automations.yaml"
)
DEFAULT_ROOM_MODES_PATH = Path("/data/room_modes.json")
DEFAULT_ROOM_SCENES_PATH = Path("/data/room_scenes.json")
DEFAULT_ROOM_SCENE_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_room_scenes.yaml"
)
DEFAULT_BEDROOM_MODES_PATH = Path("/data/bedroom_modes.json")
DEFAULT_BEDROOM_MODE_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_bedroom_mode_automations.yaml"
)
DEFAULT_WAKE_ROUTINES_PATH = Path("/data/wake_routines.json")
DEFAULT_WAKE_ROUTINE_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_wake_routines.yaml"
)
DEFAULT_HOMEKIT_LIGHT_GROUPS_PATH = Path("/data/homekit_light_groups.json")
DEFAULT_HOMEKIT_CLIMATE_PATH = Path("/data/homekit_climate_entities.json")
DEFAULT_HOMEKIT_SECURITY_PATH = Path("/data/homekit_security_entities.json")
DEFAULT_HOMEKIT_PACKAGE_PATH = Path(
    "/homeassistant/packages/future_homes_tech_homekit.yaml"
)
DEFAULT_DOOR_AUTOMATIONS_PATH = Path(
    "/homeassistant/packages/future_homes_tech_door_automations.yaml"
)
PROTECT_STATUS_HELPER = (
    "input_text.future_homes_tech_protect_arm_mode"
)
PROTECT_STATUS_POLL_INTERVAL = 60
LIGHT_GROUP_CATEGORY_NAME = "Future Homes Tech Light Groups"
LEGACY_LIGHT_GROUP_CATEGORY_NAMES = (
    "Future Homes Tech, Light Groups",
    "Future Homes Tech Light Groups",
    "Light Groups",
)
LIGHT_GROUP_CATEGORY_SCOPE = "helpers"
LIGHT_GROUP_CATEGORY_ICON = "mdi:lightbulb-group"
CLIMATE_CATEGORY_NAME = "Future Homes Tech Climate"
CLIMATE_CATEGORY_SCOPE = "helpers"
CLIMATE_CATEGORY_ICON = "mdi:thermostat"
DOOR_TIMER_CATEGORY_NAME = "Future Homes Tech Door Timers"
DOOR_TIMER_CATEGORY_ICON = "mdi:timer-outline"
AUTOMATION_CATEGORY_NAME = "Future Homes Tech"
AUTOMATION_CATEGORY_SCOPE = "automation"
AUTOMATION_CATEGORY_ICON = "mdi:home-automation"
DOOR_AUTOMATION_CATEGORY_NAME = "Future Homes Tech Door Sensors"
SWITCH_AUTOMATION_CATEGORY_NAME = "Future Homes Tech Switches"
SWITCH_ACTIVATION_CATEGORY_NAME = "Future Homes Tech Switch Activation"
LIGHT_SYNC_CATEGORY_NAME = "Future Homes Tech Light Sync"
CLIMATE_AUTOMATION_CATEGORY_NAME = "Future Homes Tech Climate"
PRESENCE_AUTOMATION_CATEGORY_NAME = "Future Homes Tech Presence"
MOTION_AUTOMATION_CATEGORY_NAME = "Future Homes Tech Motion"
SCENE_AUTOMATION_CATEGORY_NAME = "Future Homes Tech Scenes"
DEVICE_ALARM_AUTOMATION_CATEGORY_NAME = "Future Homes Tech Device Alarms"
UNGROUPED_HELPER_CATEGORY_NAME = "Future Homes Tech Ungrouped"
LIGHT_GROUP_ENTITY_PREFIX = CATALOG.LIGHT_GROUP_ENTITY_PREFIX
LIGHT_GROUP_UNIQUE_ID_PREFIX = "fht_"
CONTROL_AUTOMATION_UNIQUE_ID_PREFIX = "fht_control_"
DOOR_AUTOMATION_UNIQUE_ID_PREFIX = "fht_door_"
PRESENCE_AUTOMATION_UNIQUE_ID_PREFIX = "fht_presence_"
HOUSE_MODE_HELPER = "input_select.fht_house_mode"
LIGHT_SCHEDULE_AUTOMATION_UNIQUE_ID_PREFIX = "fht_scene_light_schedule_"
FRIDGE_ALARM_AUTOMATION_UNIQUE_ID_PREFIX = "fht_device_alarm_fridge_"
DOOR_OPEN_ALERT_AUTOMATION_UNIQUE_ID_PREFIX = "fht_door_open_alert_"
ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX = "fht_scene_room_mode_"
CLIMATE_AUTOMATION_UNIQUE_ID_PREFIXES = (
    "fht_climate_",
    "fht_super_cool_",
)
ENTRY_DELAY_AUTOMATION_UNIQUE_ID = (
    "future_homes_tech_alarm_exterior_door_entry_delay"
)
INOVELLI_EVENT_TYPES = frozenset(
    {
        "multi_press_1",
        "multi_press_2",
        "multi_press_3",
        "multi_press_4",
        "multi_press_5",
        "long_press",
        "long_release",
    }
)
INOVELLI_EVENT_LABELS = {
    "multi_press_1": "Single Press",
    "multi_press_2": "Double Press",
    "multi_press_3": "Triple Press",
    "multi_press_4": "4x Press",
    "multi_press_5": "5x Press",
    "long_press": "Long Press",
    "long_release": "Long Release",
}
GENERATED_LIGHT_GROUP_PACKAGE = Path(
    "/homeassistant/packages/future_homes_tech_light_groups.yaml"
)
EXCLUDED_DOMAINS = frozenset(
    {
        "automation",
        "calendar",
        "conversation",
        "device_tracker",
        "notify",
        "number",
        "person",
        "remote",
        "script",
        "select",
        "stt",
        "sun",
        "text",
        "todo",
        "to_do",
        "tts",
        "update",
        "weather",
        "zone",
    }
)
EXCLUDED_DOMAIN_PREFIXES = ("input_",)
EXCLUDED_BUTTON_WORDS = frozenset({"identify", "calibrate"})
CONTROL_ENTITY_DOMAINS = frozenset({"switch", "light", "fan"})
MAX_JSON_BODY_BYTES = 1_048_576
CONFIGURATION_BACKUP_LIMIT = 5
CONFIGURATION_ACTIVATION_LOCK = threading.RLock()
CONFIGURATION_MUTATION_PATHS = frozenset(
    {
        "/api/bedroom-modes",
        "/api/door-open-alerts",
        "/api/fridge-alarms",
        "/api/future-tech-portal",
        "/api/homekit-climate",
        "/api/homekit-light-groups",
        "/api/homekit-security",
        "/api/light-groups/refresh",
        "/api/light-schedules",
        "/api/presence-groups/refresh",
        "/api/presence-light-groups",
        "/api/room-aliases",
        "/api/room-modes",
        "/api/room-scenes",
        "/api/settings/revert",
        "/api/switch-light-groups",
        "/api/wake-routines",
    }
)


class RequestBodyTooLarge(Exception):
    """Indicate a request body exceeded the App limit."""


def atomic_write_text(
    path: Path,
    content: str,
    *,
    retain_previous: bool = True,
) -> bool:
    """Atomically replace one file and retain bounded prior revisions."""
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = None
    if current == content:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    if retain_previous:
        SETTINGS_HISTORY.record(path, current)
    if retain_previous and current is not None:
        backup_directory = path.parent / ".fht-backups" / path.name
        backup_directory.mkdir(parents=True, exist_ok=True)
        backup_name = (
            f"{time.time_ns()}-{os.getpid()}-{threading.get_ident()}.bak"
        )
        backup_path = backup_directory / backup_name
        backup_path.write_text(current, encoding="utf-8")
        backups = sorted(
            backup_directory.glob("*.bak"),
            key=lambda candidate: candidate.name,
            reverse=True,
        )
        for obsolete_backup in backups[CONFIGURATION_BACKUP_LIMIT:]:
            obsolete_backup.unlink(missing_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return True


def atomic_write_json(path: Path, payload: Any) -> bool:
    """Atomically persist one deterministic JSON document."""
    return atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )


SLEEP_NUMBER_PATTERN = re.compile(r"sleep\s*number|sleepiq|\bis in bed\b")


def is_sleep_number_entity(*texts: Any) -> bool:
    """Return whether names or IDs belong to a Sleep Number (SleepIQ) bed."""
    searchable = " ".join(str(text or "") for text in texts).casefold().replace("_", " ")
    return bool(SLEEP_NUMBER_PATTERN.search(searchable))


CAMERA_NAME_PATTERN = re.compile(r"\b(?:camera|doorbell)\b")


def camera_device_ids(entities: list[dict[str, Any]]) -> set[str]:
    """Return devices that have a camera entity (UniFi Protect, Frigate, Reolink...)."""
    return {
        str(entity.get("device_id"))
        for entity in entities
        if isinstance(entity, dict)
        and str(entity.get("entity_id") or "").startswith("camera.")
        and entity.get("device_id")
    }


def is_camera_entity(entity: dict[str, Any], camera_devices: set[str]) -> bool:
    """Return whether a sensor belongs to a camera, whose motion is not presence."""
    if str(entity.get("device_id") or "") in camera_devices:
        return True
    searchable = " ".join(
        str(entity.get(key) or "")
        for key in ("entity_id", "friendly_name", "name", "original_name", "device_name")
    ).casefold().replace("_", " ")
    return bool(CAMERA_NAME_PATTERN.search(searchable))


def is_direct_control_entity_id(entity_id: str) -> bool:
    """Return whether an entity can represent a physical control channel."""
    domain, separator, object_id = entity_id.partition(".")
    return separator == "." and bool(object_id) and domain in CONTROL_ENTITY_DOMAINS


beta_mode_enabled = BETA.beta_mode_enabled


class SupervisorAppInfo:
    """Read installed and available App versions from Supervisor."""

    def __init__(
        self,
        token: str,
        info_url: str,
        cache_ttl: float = APP_INFO_CACHE_TTL_SECONDS,
        states_url: str = DEFAULT_HOME_ASSISTANT_STATES_URL,
        services_url: str = DEFAULT_HOME_ASSISTANT_SERVICES_URL,
    ) -> None:
        self._token = token
        self._info_url = info_url
        self._states_url = states_url
        self._services_url = services_url.rstrip("/")
        self._cache_ttl = max(0.0, float(cache_ttl))
        self._cache_lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._cache_at = 0.0
        # The update entity the last install used, for the interface to watch.
        self.update_entity = ""

    def fetch(self, force: bool = False) -> dict[str, Any]:
        """Return normalized App update status."""
        if not self._token:
            raise HomeAssistantAPIError(
                "Home Assistant App API access is unavailable."
            )
        with self._cache_lock:
            if (
                not force
                and self._cache is not None
                and time.monotonic() - self._cache_at < self._cache_ttl
            ):
                return copy.deepcopy(self._cache)
            request = Request(
                self._info_url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, OSError, ValueError) as err:
                raise HomeAssistantAPIError(
                    f"Unable to read App update status: {err}"
                ) from err

            group_state = "unknown"
            group_check_error = None
            try:
                group_check = subprocess.run(
                    ["future-homes-tech-generate-light-groups", "--check"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                group_state, _, _group_count = (
                    group_check.stdout.strip().partition(" ")
                )
            except (OSError, subprocess.SubprocessError) as err:
                group_check_error = f"Unable to inspect light groups: {err}"
                print(f"[App Info] WARNING {group_check_error}", flush=True)

            data = payload.get("data", payload)
            installed_version = str(data.get("version") or "")
            available_version = str(
                data.get("version_latest") or installed_version
            )
            self._cache = {
                "installed_version": installed_version,
                "available_version": available_version,
                "update_available": bool(data.get("update_available")),
                "slug": str(data.get("slug") or ""),
                "name": str(data.get("name") or ""),
                "light_groups_dirty": group_state == "changed",
                "light_group_check_error": group_check_error,
                "queried_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cache_at = time.monotonic()
            return copy.deepcopy(self._cache)

    def _ha_request(self, url: str, payload: dict[str, Any] | None = None, timeout: float = 10) -> Any:
        request = Request(
            url,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="GET" if payload is None else "POST",
        )
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "null")

    @staticmethod
    def update_entity_id(states: list[dict[str, Any]], slug: str, name: str) -> str:
        """Return the Home Assistant update entity for this App.

        Home Assistant's Supervisor integration makes one update entity per
        App; its picture names the App's slug, and its title is the App name.
        """
        candidates = [
            state for state in states
            if str(state.get("entity_id") or "").startswith("update.")
        ]
        for state in candidates:
            picture = str((state.get("attributes") or {}).get("entity_picture") or "")
            if slug and f"/addons/{slug}/" in picture:
                return str(state["entity_id"])
        for state in candidates:
            if name and str((state.get("attributes") or {}).get("title") or "") == name:
                return str(state["entity_id"])
        return ""

    def install_update(self) -> str:
        """Ask Home Assistant to install the waiting App update.

        The App can't update itself through Supervisor, so Home Assistant's
        update entity for the App installs it. Supervisor stops this App
        while it does, so the call runs in the background; the interface
        waits for the new version to answer. Returns the version installing.
        """
        info = self.fetch(force=True)
        if not info["update_available"]:
            raise HomeAssistantAPIError("No App update is waiting.")
        try:
            states = self._ha_request(self._states_url)
        except (HTTPError, URLError, OSError, ValueError) as err:
            raise HomeAssistantAPIError(f"Unable to read Home Assistant updates: {err}") from err
        entity_id = self.update_entity_id(states or [], info["slug"], info["name"])
        if not entity_id:
            raise HomeAssistantAPIError("Home Assistant has no update entity for this App.")
        errors: list[str] = []

        def install() -> None:
            try:
                self._ha_request(f"{self._services_url}/update/install", {"entity_id": entity_id}, timeout=900)
            except HTTPError as err:
                errors.append(f"Home Assistant returned HTTP {err.code}.")
            except (URLError, OSError, ValueError) as err:
                errors.append(str(err))
            if errors:
                print(f"[App Info] WARNING App update failed: {errors[0]}", flush=True)

        worker = threading.Thread(target=install, name="app-update", daemon=True)
        worker.start()
        # An immediate refusal is reported; otherwise the update is under way.
        worker.join(3)
        if errors:
            raise HomeAssistantAPIError(f"Unable to start the App update: {errors[0]}")
        print(f"[App Info] Installing App update {info['available_version']} with {entity_id}.", flush=True)
        self.update_entity = entity_id
        with self._cache_lock:
            self._cache = None
        return info["available_version"]


def parse_door_assignment_id(assignment_id: str) -> tuple[str, str]:
    """Return a door entity and optional Day/Night condition."""
    match = re.fullmatch(
        r"door:(binary_sensor\.[a-z0-9_]+)(?:\|(day|night|sleep|room:[a-z0-9_]+:[a-z0-9_]+|floor:[a-z0-9_-]+))?",
        str(assignment_id or "").casefold(),
    )
    return (match.group(1), match.group(2) or "") if match else ("", "")


def is_bedroom_closet_door(entity: dict[str, Any]) -> bool:
    name = str(entity.get("friendly_name") or entity.get("entity_id") or "").replace("_", " ").casefold()
    area = str(entity.get("original_area") or entity.get("area") or "").casefold()
    return "closet" in name and "bedroom" in area


class JsonSettingsStore:
    """Persist one settings document as JSON under /data.

    Subclasses keep their own ``normalize`` rules and ``save`` signatures and
    override ``_clean`` to turn the stored document into what ``read``
    returns.  The base owns the path, the lock, and how a missing, unreadable,
    or malformed file is reported.  Every write goes through
    ``atomic_write_json`` so settings history keeps recording revisions.
    """

    # Wording of the errors the interface shows; subclasses set their own.
    READ_ERROR = "Unable to read settings"
    SAVE_ERROR = "Unable to save settings"
    # Stores that never fail a request over a corrupt file read it as empty.
    TOLERATE_CORRUPT = False

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _read_raw(self, path: Path | None = None) -> Any:
        """Return the stored document as saved; a missing file reads as ``{}``."""
        try:
            return json.loads(
                (self._path if path is None else path).read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as err:
            if self.TOLERATE_CORRUPT:
                return {}
            raise HomeAssistantAPIError(f"{self.READ_ERROR}: {err}") from err

    def _read_dict(self) -> dict[str, Any]:
        """Return the stored object as saved, treating any other document as empty."""
        payload = self._read_raw()
        return payload if isinstance(payload, dict) else {}

    def _clean(self, payload: Any) -> Any:
        """Return the valid part of one stored document."""
        return payload if isinstance(payload, dict) else {}

    def _read_unlocked(self) -> Any:
        """Return the cleaned document; the caller holds the lock."""
        return self._clean(self._read_raw())

    def read(self) -> Any:
        """Return every valid saved setting."""
        with self._lock:
            return self._read_unlocked()

    def _write_unlocked(self, payload: Any) -> None:
        """Replace the stored document; the caller holds the lock."""
        try:
            atomic_write_json(self._path, payload)
        except OSError as err:
            raise HomeAssistantAPIError(f"{self.SAVE_ERROR}: {err}") from err


class SwitchLightGroupAssignments(JsonSettingsStore):
    """Persist switch-to-FHT-light-group assignments."""

    READ_ERROR = "Unable to read switch assignments"
    SAVE_ERROR = "Unable to save switch assignment"

    def _clean(self, payload: Any) -> dict[str, str]:
        """Return every valid saved assignment."""
        if not isinstance(payload, dict):
            return {}
        return {
            switch_id: group_id
            for switch_id, group_id in payload.items()
            if isinstance(switch_id, str)
            and self._valid_assignment_id(switch_id)
            and isinstance(group_id, str)
            and group_id.startswith("light.")
        }

    @staticmethod
    def _valid_assignment_id(assignment_id: str) -> bool:
        """Accept direct switches and supported event or device gestures."""
        if is_direct_control_entity_id(assignment_id):
            return True
        if parse_door_assignment_id(assignment_id)[0]:
            return True
        if assignment_id.startswith("button:"):
            trigger_parts = assignment_id.removeprefix("button:").split("|", 3)
            return (
                len(trigger_parts) == 4
                and bool(trigger_parts[0])
                and trigger_parts[1] == "zha"
                and trigger_parts[2].startswith("remote_button_")
            )
        event_entity_id, separator, event_type = assignment_id.partition("|")
        return (
            separator == "|"
            and event_entity_id.startswith("event.")
            and event_type in INOVELLI_EVENT_TYPES
        )

    def save(self, assignment_id: str, group_id: str) -> dict[str, str]:
        """Create, update, or remove one assignment."""
        if not self._valid_assignment_id(assignment_id):
            raise ValueError("A valid switch or button gesture is required.")
        if group_id and not group_id.startswith("light."):
            raise ValueError("A valid light or light group is required.")
        with self._lock:
            payload = self._read_dict()
            if group_id:
                payload[assignment_id] = group_id
            else:
                payload.pop(assignment_id, None)
            self._write_unlocked(payload)
        return {
            key: value
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, str)
        }


class SwitchControlSettings(JsonSettingsStore):
    """Persist room-mode actions and reusable named switch loads."""

    READ_ERROR = "Unable to read switch control settings"
    SAVE_ERROR = "Unable to save switch control settings"

    @staticmethod
    def _clean(payload: Any) -> dict[str, Any]:
        """Return saved mode actions and named reusable switch loads."""
        if not isinstance(payload, dict):
            payload = {}
        mode_assignments = payload.get("mode_assignments", {})
        actual_loads = payload.get("actual_loads", {})
        load_target_assignments = payload.get("load_target_assignments", {})
        action_assignments = payload.get("action_assignments", {})
        action_settings = payload.get("action_settings", {})
        if not isinstance(mode_assignments, dict):
            mode_assignments = {}
        if not isinstance(actual_loads, dict):
            actual_loads = {}
        if not isinstance(load_target_assignments, dict):
            load_target_assignments = {}
        if not isinstance(action_assignments, dict):
            action_assignments = {}
        if not isinstance(action_settings, dict):
            action_settings = {}
        cleaned_actual_loads = {
            switch_id: load_name.strip()
            for switch_id, load_name in actual_loads.items()
            if isinstance(switch_id, str)
            and switch_id.startswith("switch.")
            and isinstance(load_name, str)
            and load_name.strip()
        }
        cleaned_action_assignments = {
            assignment_id: actions
            for assignment_id, raw_actions in action_assignments.items()
            if isinstance(assignment_id, str)
            and SwitchLightGroupAssignments._valid_assignment_id(assignment_id)
            and (actions := SwitchControlSettings._clean_actions(raw_actions))
        }
        for assignment_id, actions in list(cleaned_action_assignments.items()):
            door_entity_id, house_mode = parse_door_assignment_id(assignment_id)
            if not door_entity_id or house_mode:
                continue
            cleaned_action_assignments.setdefault(
                f"door:{door_entity_id}|day", list(actions)
            )
            cleaned_action_assignments.setdefault(
                f"door:{door_entity_id}|night", list(actions)
            )
            cleaned_action_assignments.pop(assignment_id, None)
        cleaned_action_settings = {
            assignment_id: setting
            for assignment_id, raw_setting in action_settings.items()
            if isinstance(assignment_id, str)
            and parse_door_assignment_id(assignment_id)[0]
            and (setting := SwitchControlSettings._clean_action_setting(raw_setting))
        }
        return {
            "schema_version": 2
            if payload.get("schema_version") == 2
            else 1,
            "mode_assignments": {
                assignment_id: target_id
                for assignment_id, target_id in mode_assignments.items()
                if isinstance(assignment_id, str)
                and SwitchLightGroupAssignments._valid_assignment_id(assignment_id)
                and isinstance(target_id, str)
                and (
                    (
                        target_id.partition("|")[0].startswith("input_select.fht_")
                        and target_id.partition("|")[0].endswith("_mode")
                        and (not target_id.partition("|")[1] or target_id.partition("|")[2] in {"Sleep", "Toddler"})
                    )
                    or (
                        target_id.startswith("input_button.fht_")
                        and target_id.endswith("_wake_override")
                    )
                )
            },
            "actual_loads": cleaned_actual_loads,
            "load_target_assignments": {
                assignment_id: target_switch_id
                for assignment_id, target_switch_id
                in load_target_assignments.items()
                if isinstance(assignment_id, str)
                and SwitchLightGroupAssignments._valid_assignment_id(
                    assignment_id
                )
                and isinstance(target_switch_id, str)
                and target_switch_id in cleaned_actual_loads
                and assignment_id != target_switch_id
            },
            "action_assignments": cleaned_action_assignments,
            "action_settings": cleaned_action_settings,
            "exhaust_timers": {
                entity_id: minutes for entity_id, minutes in (payload.get("exhaust_timers") or {}).items()
                if isinstance(entity_id, str) and entity_id.startswith("switch.")
                and type(minutes) is int and 1 <= minutes <= 120
            } if isinstance(payload.get("exhaust_timers", {}), dict) else {},
            "exhaust_humidity": ExhaustFanHumidity.normalize(payload.get("exhaust_humidity")),
            "exhaust_presence": ExhaustFanPresence.normalize(payload.get("exhaust_presence")),
        }

    @staticmethod
    def _clean_action_setting(raw_setting: Any) -> dict[str, Any]:
        """Return safe light behavior for one mode-specific door action."""
        setting = raw_setting if isinstance(raw_setting, dict) else {}
        try:
            brightness = int(setting.get("brightness_pct", 100))
        except (TypeError, ValueError):
            brightness = 100
        brightness = max(0, min(100, brightness))
        color_mode = str(setting.get("color_mode") or "current").casefold()
        if color_mode not in {"current", "adaptive", "kelvin", "rgb"}:
            color_mode = "current"
        try:
            color_kelvin = int(setting.get("color_kelvin", 3000))
        except (TypeError, ValueError):
            color_kelvin = 3000
        color_kelvin = max(2000, min(6500, color_kelvin))
        color_rgb = setting.get("color_rgb", [255, 255, 255])
        if (
            not isinstance(color_rgb, list)
            or len(color_rgb) != 3
            or any(not isinstance(value, int) or isinstance(value, bool) for value in color_rgb)
        ):
            color_rgb = [255, 255, 255]
        color_rgb = [max(0, min(255, value)) for value in color_rgb]
        timeout = setting.get("timeout_minutes", 0)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 0 <= timeout <= 120:
            raise ValueError("Door timeout must be 0 to 120 whole minutes.")
        return {
            **({"timeout_minutes": timeout} if "timeout_minutes" in setting else {}),
            "enabled": bool(setting.get("enabled", True)),
            "brightness_pct": brightness,
            "color_mode": color_mode,
            "color_kelvin": color_kelvin,
            "color_rgb": color_rgb,
        }

    @staticmethod
    def _clean_actions(raw_actions: Any) -> list[str]:
        """Return valid, de-duplicated action targets."""
        if isinstance(raw_actions, str):
            raw_actions = [raw_actions]
        if not isinstance(raw_actions, list):
            return []
        actions: list[str] = []
        for raw_action in raw_actions:
            action = str(raw_action or "").strip()
            action_type, separator, target_id = action.partition(":")
            if not separator or not target_id:
                continue
            if action_type in {"actual_load", "switch_target"}:
                action_type = "entity_target"
                action = f"{action_type}:{target_id}"
            valid = (
                action_type == "light_group"
                and target_id.startswith("light.")
            ) or (
                action_type in {"actual_load", "switch_target"}
                and target_id.startswith("switch.")
            ) or (
                action_type == "entity_target"
                and target_id.partition(".")[0] in CONTROL_ENTITY_DOMAINS
                and bool(target_id.partition(".")[2])
            ) or (
                action_type == "room_mode"
                and target_id.partition("|")[0].startswith(
                    "input_select.fht_"
                )
                and target_id.partition("|")[0].endswith("_mode")
                and target_id.partition("|")[2] in {"Sleep", "Toddler"}
            ) or (
                action_type == "wake_override"
                and target_id.startswith("input_button.fht_")
                and target_id.endswith("_wake_override")
            )
            if valid and action not in actions:
                actions.append(action)
        return actions

    def migrate_legacy(
        self,
        legacy_light_assignments: dict[str, str],
        legacy_door_assignments: dict[str, str],
    ) -> dict[str, Any]:
        """Merge retired assignment stores into the shared action model."""
        with self._lock:
            payload = self._read_unlocked()
            if payload["schema_version"] == 2:
                return payload
            original = copy.deepcopy(payload)
            actions_by_assignment = {
                assignment_id: list(actions)
                for assignment_id, actions
                in payload["action_assignments"].items()
            }

            def add_action(assignment_id: str, action: str) -> None:
                if not SwitchLightGroupAssignments._valid_assignment_id(
                    assignment_id
                ):
                    return
                cleaned = self._clean_actions([action])
                if not cleaned:
                    return
                current = actions_by_assignment.setdefault(assignment_id, [])
                if cleaned[0] not in current:
                    current.append(cleaned[0])

            for assignment_id, group_id in legacy_light_assignments.items():
                add_action(assignment_id, f"light_group:{group_id}")
            for door_id, group_id in legacy_door_assignments.items():
                add_action(f"door:{door_id}", f"light_group:{group_id}")
            for assignment_id, target_id in payload["mode_assignments"].items():
                action_type = (
                    "wake_override"
                    if target_id.startswith("input_button.")
                    else "room_mode"
                )
                normalized_target = target_id
                if action_type == "room_mode" and "|" not in normalized_target:
                    normalized_target = f"{normalized_target}|Sleep"
                add_action(
                    assignment_id,
                    f"{action_type}:{normalized_target}",
                )
            for assignment_id, target_id in payload[
                "load_target_assignments"
            ].items():
                add_action(assignment_id, f"entity_target:{target_id}")

            payload["schema_version"] = 2
            payload["action_assignments"] = actions_by_assignment
            payload["mode_assignments"] = {}
            payload["load_target_assignments"] = {}
            if payload != original:
                self._write_unlocked(payload)
            return payload

    def reconcile_retired_fan_light_groups(
        self, entities: list[dict[str, Any]], expected_groups: set[str] | None = None,
    ) -> dict[str, Any]:
        entity_states = {entity.get("entity_id"): entity.get("state") for entity in entities}
        replacements = {}
        for replacement in expected_groups or set():
            if not replacement.startswith(LIGHT_GROUP_ENTITY_PREFIX) or not replacement.endswith("_fan_lights"):
                continue
            area = replacement.removeprefix(LIGHT_GROUP_ENTITY_PREFIX).removesuffix("_fan_lights")
            replacements[f"light_group:light.fht_{area}_all_lights"] = f"light_group:{replacement}"
            retired = f"light.{area}_fan_lights"
            if entity_states.get(retired) in {None, "unavailable", "unknown"}:
                replacements[f"light_group:{retired}"] = f"light_group:{replacement}"
        if not replacements:
            return self.read()
        with self._lock:
            payload = self._read_unlocked()
            changed = False
            for assignment_id, actions in payload["action_assignments"].items():
                updated = list(dict.fromkeys(
                    replacements.get(action, action)
                    for action in actions
                ))
                if updated != actions:
                    payload["action_assignments"][assignment_id] = updated
                    changed = True
            if changed:
                self._write_unlocked(payload)
            return payload

    def save_exhaust_timer(self, entity_id: str, minutes: int) -> dict[str, Any]:
        if not entity_id.startswith("switch.") or type(minutes) is not int or not 0 <= minutes <= 120:
            raise ValueError("Select Off or a whole number of minutes from 1 to 120.")
        with self._lock:
            payload = self._read_unlocked()
            if minutes:
                payload["exhaust_timers"][entity_id] = minutes
            else:
                payload["exhaust_timers"].pop(entity_id, None)
            self._write_unlocked(payload)
            return payload

    def save_exhaust_humidity(self, entity_id: str, sensor_id: str, start_above: Any, stop_below: Any) -> dict[str, Any]:
        """Pair an exhaust fan with a humidity sensor, or clear the pairing with an empty sensor."""
        if not entity_id.startswith("switch."):
            raise ValueError("A valid switch is required.")
        entry = ExhaustFanHumidity.clean(sensor_id, start_above, stop_below)
        with self._lock:
            payload = self._read_unlocked()
            if entry:
                payload["exhaust_humidity"][entity_id] = entry
            else:
                payload["exhaust_humidity"].pop(entity_id, None)
            self._write_unlocked(payload)
            return payload

    def save_exhaust_presence(self, entity_id: str, sensor_id: str, activation_minutes: Any, clear_minutes: Any) -> dict[str, Any]:
        """Run an exhaust fan from a presence sensor, or clear the pairing with an empty sensor."""
        if not entity_id.startswith("switch."):
            raise ValueError("A valid switch is required.")
        entry = ExhaustFanPresence.clean(sensor_id, activation_minutes, clear_minutes)
        with self._lock:
            payload = self._read_unlocked()
            if entry:
                payload["exhaust_presence"][entity_id] = entry
            else:
                payload["exhaust_presence"].pop(entity_id, None)
            self._write_unlocked(payload)
            return payload

    def save_mode(
        self,
        switch_id: str,
        target_id: str,
        option: str = "Sleep",
    ) -> dict[str, Any]:
        """Assign a switch to the room-mode helper it controls."""
        if not SwitchLightGroupAssignments._valid_assignment_id(switch_id):
            raise ValueError("A valid switch or button gesture is required.")
        valid_mode = target_id.startswith("input_select.fht_") and target_id.endswith("_mode")
        valid_wake_override = target_id.startswith("input_button.fht_") and target_id.endswith("_wake_override")
        if target_id and not (valid_mode or valid_wake_override):
            raise ValueError("A valid room mode is required.")
        if valid_mode and option not in {"Sleep", "Toddler"}:
            raise ValueError("A valid bedroom mode action is required.")
        with self._lock:
            payload = self._read_unlocked()
            if target_id:
                payload["mode_assignments"][switch_id] = target_id if valid_wake_override or option == "Sleep" else f"{target_id}|{option}"
            else:
                payload["mode_assignments"].pop(switch_id, None)
            self._write_unlocked(payload)
        return payload

    def save_actual_load(
        self,
        switch_id: str,
        load_name: str,
    ) -> dict[str, Any]:
        """Expose or remove a switch channel as a named reusable load."""
        if not switch_id.startswith("switch."):
            raise ValueError("A valid switch is required.")
        load_name = load_name.strip()
        if len(load_name) > 80:
            raise ValueError("The actual load name must be 80 characters or less.")
        with self._lock:
            payload = self._read_unlocked()
            if load_name:
                payload["actual_loads"][switch_id] = load_name
            else:
                payload["actual_loads"].pop(switch_id, None)
                payload["load_target_assignments"] = {
                    assignment_id: target_switch_id
                    for assignment_id, target_switch_id
                    in payload["load_target_assignments"].items()
                    if target_switch_id != switch_id
                }
                payload["action_assignments"] = {
                    assignment_id: [
                        action
                        for action in actions
                        if action != f"actual_load:{switch_id}"
                    ]
                    for assignment_id, actions
                    in payload["action_assignments"].items()
                }
                payload["action_assignments"] = {
                    assignment_id: actions
                    for assignment_id, actions
                    in payload["action_assignments"].items()
                    if actions
                }
            self._write_unlocked(payload)
        return payload

    def reconcile_actual_load_names(
        self,
        entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Keep enabled load names aligned with Home Assistant friendly names."""
        friendly_names = {
            str(entity.get("entity_id") or ""): str(
                entity.get("friendly_name")
                or entity.get("entity_id")
                or ""
            ).strip()
            for entity in entities
            if isinstance(entity, dict)
        }
        with self._lock:
            payload = self._read_unlocked()
            changed = False
            for switch_id in tuple(payload["actual_loads"]):
                friendly_name = friendly_names.get(switch_id)
                if friendly_name and payload["actual_loads"][switch_id] != friendly_name:
                    payload["actual_loads"][switch_id] = friendly_name[:80]
                    changed = True
            if changed:
                self._write_unlocked(payload)
        return payload

    def save_load_target(
        self,
        assignment_id: str,
        target_switch_id: str,
    ) -> dict[str, Any]:
        """Assign a switch or gesture to a named actual load."""
        if not SwitchLightGroupAssignments._valid_assignment_id(assignment_id):
            raise ValueError("A valid switch or button gesture is required.")
        with self._lock:
            payload = self._read_unlocked()
            if target_switch_id:
                if target_switch_id not in payload["actual_loads"]:
                    raise ValueError("A named actual load is required.")
                if assignment_id == target_switch_id:
                    raise ValueError("A switch cannot target its own actual load.")
                payload["load_target_assignments"][assignment_id] = (
                    target_switch_id
                )
            else:
                payload["load_target_assignments"].pop(assignment_id, None)
            self._write_unlocked(payload)
        return payload

    def save_door_card(self, assignment_id: str, actions: Any, modes: Any, timeout: Any) -> dict[str, Any]:
        door_id, mode = parse_door_assignment_id(assignment_id)
        if not door_id or mode or not isinstance(modes, dict) or not modes:
            raise ValueError("A door and its mode settings are required.")
        cleaned_actions = self._clean_actions(actions)
        if not isinstance(actions, list) or len(cleaned_actions) != len(actions):
            raise ValueError("Invalid door actions.")
        settings = {}
        for key, value in modes.items():
            if not parse_door_assignment_id(assignment_id + "|" + str(key))[0] or not isinstance(value, dict):
                raise ValueError("Invalid door mode.")
            settings[assignment_id + "|" + key] = self._clean_action_setting({**value, "timeout_minutes": timeout})
        with self._lock:
            payload = self._read_unlocked()
            for field in ("action_assignments", "action_settings", "mode_assignments", "load_target_assignments"):
                for key in list(payload[field]):
                    if key == assignment_id or key.startswith(assignment_id + "|"):
                        del payload[field][key]
            for key, setting in settings.items():
                payload["action_settings"][key] = setting
                if cleaned_actions:
                    payload["action_assignments"][key] = cleaned_actions
            self._write_unlocked(payload)
        return payload

    def save_actions(
        self,
        assignment_id: str,
        actions: Any,
        action_setting: Any = None,
    ) -> dict[str, Any]:
        """Save every selected target for one control or gesture."""
        if not SwitchLightGroupAssignments._valid_assignment_id(assignment_id):
            raise ValueError("A valid switch or button gesture is required.")
        cleaned_actions = self._clean_actions(actions)
        raw_count = len(actions) if isinstance(actions, list) else bool(actions)
        if raw_count and len(cleaned_actions) != raw_count:
            raise ValueError("One or more selected actions are invalid.")
        with self._lock:
            payload = self._read_unlocked()
            payload["mode_assignments"].pop(assignment_id, None)
            payload["load_target_assignments"].pop(assignment_id, None)
            if cleaned_actions:
                payload["action_assignments"][assignment_id] = cleaned_actions
            else:
                payload["action_assignments"].pop(assignment_id, None)
            if parse_door_assignment_id(assignment_id)[0] and action_setting is not None:
                payload["action_settings"][assignment_id] = self._clean_action_setting(
                    action_setting
                )
            self._write_unlocked(payload)
        return payload

    def save_discovered_switch_target(
        self,
        assignment_id: str,
        target_switch_id: str,
        entities: list[dict[str, Any]],
    ) -> dict[str, dict[str, str]]:
        """Expose and assign a discovered Home Assistant switch as a load."""
        if not SwitchLightGroupAssignments._valid_assignment_id(assignment_id):
            raise ValueError("A valid switch or button gesture is required.")
        if assignment_id == target_switch_id:
            raise ValueError("A switch cannot target its own load.")
        target = next(
            (
                entity
                for entity in entities
                if isinstance(entity, dict)
                and entity.get("entity_id") == target_switch_id
                and str(entity.get("domain") or "") == "switch"
            ),
            None,
        )
        if target is None:
            raise ValueError("The selected switch or plug was not found.")
        load_name = str(
            target.get("friendly_name") or target_switch_id
        ).strip()[:80]
        with self._lock:
            payload = self._read_unlocked()
            payload["actual_loads"][target_switch_id] = load_name
            payload["load_target_assignments"][assignment_id] = (
                target_switch_id
            )
            self._write_unlocked(payload)
        return payload


class PresenceLightGroupAssignments(SwitchLightGroupAssignments):
    """Persist presence-sensor action targets."""

    READ_ERROR = "Unable to read presence assignments"
    SAVE_ERROR = "Unable to save presence assignment"

    @staticmethod
    def _valid_assignment_id(assignment_id: str) -> bool:
        return assignment_id.startswith("binary_sensor.")

    @staticmethod
    def _valid_target_id(target_id: str) -> bool:
        return target_id.partition(".")[0] in CONTROL_ENTITY_DOMAINS

    @classmethod
    def _clean_targets(cls, raw_targets: Any) -> list[str]:
        if isinstance(raw_targets, str):
            raw_targets = [raw_targets]
        if not isinstance(raw_targets, list):
            return []
        targets: list[str] = []
        for raw_target in raw_targets:
            target_id = str(raw_target or "").strip()
            if cls._valid_target_id(target_id) and target_id not in targets:
                targets.append(target_id)
        return targets

    def _clean(self, payload: Any) -> dict[str, list[str]]:
        """Return saved individual-light, light-group, and load targets."""
        if not isinstance(payload, dict):
            return {}
        return {
            presence_id: targets
            for presence_id, raw_targets in payload.items()
            if isinstance(presence_id, str)
            and self._valid_assignment_id(presence_id)
            and (targets := self._clean_targets(raw_targets))
        }

    def save(
        self,
        assignment_id: str,
        target_ids: Any,
    ) -> dict[str, list[str]]:
        if not self._valid_assignment_id(assignment_id):
            raise ValueError("A valid presence sensor is required.")
        targets = self._clean_targets(target_ids)
        raw_count = (
            len(target_ids)
            if isinstance(target_ids, list)
            else bool(target_ids)
        )
        if raw_count and len(targets) != raw_count:
            raise ValueError("A valid light, light group, switch, fan, or plug is required.")
        with self._lock:
            payload = self._read_dict()
            if targets:
                payload[assignment_id] = targets
            else:
                payload.pop(assignment_id, None)
            self._write_unlocked(payload)
        return self.read()


class PresenceTimingSettings(JsonSettingsStore):
    """Persist per-sensor activation and clear delays."""

    SAVE_ERROR = "Unable to save presence timings"
    TOLERATE_CORRUPT = True

    def _clean(self, payload: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(payload, dict):
            return {}
        return {
            entity_id: {
                "activation_delay": int(values.get("activation_delay", 0)),
                "clear_delay": int(values.get("clear_delay", 0)),
                "parent_groups": list(dict.fromkeys(
                    str(parent_id).strip()
                    for parent_id in values.get("parent_groups", [])
                    if isinstance(parent_id, str)
                    and parent_id.startswith("binary_sensor.")
                    and parent_id != entity_id
                )),
            }
            for entity_id, values in payload.items()
            if entity_id.startswith("binary_sensor.") and isinstance(values, dict)
        }

    def save(
        self,
        entity_id: str,
        activation_delay: int | str,
        clear_delay: int | str,
        parent_groups: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not entity_id.startswith("binary_sensor."):
            raise ValueError("A valid presence sensor is required.")
        try:
            activation = int(activation_delay)
            clear = int(clear_delay)
        except (TypeError, ValueError) as err:
            raise ValueError("Presence delays must be whole seconds.") from err
        if not 0 <= activation <= 7200 or not 0 <= clear <= 7200:
            raise ValueError("Presence delays must be between 0 and 120 minutes.")
        if parent_groups is not None and not isinstance(parent_groups, list):
            raise ValueError("Parent presence groups must be a list.")
        normalized_parent_groups = list(dict.fromkeys(
            str(parent_id).strip()
            for parent_id in (parent_groups or [])
            if isinstance(parent_id, str)
            and parent_id.startswith("binary_sensor.")
            and parent_id != entity_id
        ))
        with self._lock:
            timings = self._read_unlocked()
            timings[entity_id] = {
                "activation_delay": activation,
                "clear_delay": clear,
                "parent_groups": normalized_parent_groups,
            }
            self._write_unlocked(timings)
        return timings


class PresenceModeSettings(JsonSettingsStore):
    """Persist per-presence behavior for Day, Night, and Sleep modes."""

    MODES = ("day", "night", "sleep")
    DEFAULT = {
        "day": {"enabled": False, "brightness": 100},
        "night": {"enabled": True, "brightness": 80},
        "sleep": {"enabled": True, "brightness": 25},
    }
    # "current" leaves the lights' colour alone, which every saved rule
    # keeps until the homeowner picks a tone.
    COLOR_MODES = ("current", "kelvin", "adaptive")
    DEFAULT_COLOR_KELVIN = 4000
    SAVE_ERROR = "Unable to save presence mode settings"
    TOLERATE_CORRUPT = True

    @classmethod
    def normalize(cls, value: Any) -> dict[str, dict[str, Any]]:
        """Return one validated three-mode presence configuration."""
        payload = value if isinstance(value, dict) else {}
        result: dict[str, dict[str, Any]] = {}
        extra_modes = set(payload) & (RoomModeSettings.ALLOWED_MODES - RoomModeSettings.ALARM_MODES)
        for mode in (*cls.MODES, *sorted(extra_modes - set(cls.MODES))):
            fallback = cls.DEFAULT.get(mode, {"enabled": False, "brightness": 100})
            raw = payload.get(mode, {})
            if not isinstance(raw, dict):
                raise ValueError("Presence mode settings must be objects.")
            try:
                brightness = int(
                    raw.get("brightness", fallback["brightness"])
                )
            except (TypeError, ValueError) as err:
                raise ValueError(
                    "Presence brightness must be a whole percentage."
                ) from err
            if not 1 <= brightness <= 100:
                raise ValueError(
                    "Presence brightness must be between 1 and 100 percent."
                )
            result[mode] = {
                "enabled": bool(
                    raw.get("enabled", fallback["enabled"])
                ),
                "brightness": brightness,
                **cls._normalize_tone(raw),
            }
        return result

    @classmethod
    def _normalize_tone(cls, raw: dict[str, Any]) -> dict[str, Any]:
        """Return one mode's validated colour tone."""
        color_mode = str(raw.get("color_mode") or "current").casefold()
        if color_mode not in cls.COLOR_MODES:
            raise ValueError(
                "Presence tone must be current, kelvin, or adaptive."
            )
        try:
            color_kelvin = int(raw.get("color_kelvin", cls.DEFAULT_COLOR_KELVIN))
        except (TypeError, ValueError) as err:
            raise ValueError(
                "Presence tone must be a whole Kelvin value."
            ) from err
        if not 2000 <= color_kelvin <= 6500:
            raise ValueError(
                "Presence tone must be between 2000 and 6500 Kelvin."
            )
        return {"color_mode": color_mode, "color_kelvin": color_kelvin}

    def _clean(self, payload: Any) -> dict[str, dict[str, dict[str, Any]]]:
        """Return every valid sensor mode configuration."""
        if not isinstance(payload, dict):
            return {}
        settings: dict[str, dict[str, dict[str, Any]]] = {}
        for entity_id, value in payload.items():
            if not str(entity_id).startswith("binary_sensor."):
                continue
            try:
                settings[str(entity_id)] = self.normalize(value)
            except ValueError:
                continue
        return settings

    def save(
        self,
        entity_id: str,
        value: Any,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Create or update one sensor's mode configuration."""
        if not entity_id.startswith("binary_sensor."):
            raise ValueError("A valid presence sensor is required.")
        setting = self.normalize(value)
        with self._lock:
            settings = self._read_unlocked()
            settings[entity_id] = setting
            self._write_unlocked(settings)
        return settings


class HomeKitLightGroupSelection(JsonSettingsStore):
    """Persist FHT light groups exposed by the managed HomeKit bridge."""

    TOLERATE_CORRUPT = True

    def __init__(
        self,
        path: Path,
        climate_path: Path,
        package_path: Path,
        security_path: Path | None = None,
    ) -> None:
        super().__init__(path)
        self._climate_path = climate_path
        self._security_path = security_path or path.with_name(
            "homekit_security_entities.json"
        )
        self._package_path = package_path

    # The three selections read unlocked: every writer below calls them while
    # already holding the selection lock, after the activation lock.
    def read(self) -> list[str]:
        payload = self._read_raw()
        return sorted(item for item in payload if isinstance(item, str) and item.startswith(LIGHT_GROUP_ENTITY_PREFIX)) if isinstance(payload, list) else []

    def reconcile_generated_groups(self, expected_groups: set[str], entity_names: dict[str, str]) -> bool:
        # Lock order everywhere in this class: activation lock, then the selection lock.
        with CONFIGURATION_ACTIVATION_LOCK, self._lock:
            current = self.read()
            selected = set()
            for entity_id in current:
                if entity_id in expected_groups:
                    selected.add(entity_id)
                elif entity_id.endswith("_all_lights"):
                    replacement = entity_id.removesuffix("_all_lights") + "_fan_lights"
                    if replacement in expected_groups:
                        selected.add(replacement)
                        entity_names.setdefault(replacement, entity_names.get(entity_id, replacement).replace("All Lights", "Fan Lights"))
            if selected == set(current):
                return False
            values = sorted(selected)
            atomic_write_json(self._path, values)
            self._write(values, self.read_climate(), self.read_security(), entity_names)
            return True

    def save(
        self,
        entity_id: str,
        included: bool,
        entity_names: dict[str, str],
    ) -> list[str]:
        if not entity_id.startswith(LIGHT_GROUP_ENTITY_PREFIX):
            raise ValueError("A Future Homes Tech light group is required.")
        with CONFIGURATION_ACTIVATION_LOCK, self._lock:
            selected = set(self.read())
            if included:
                selected.add(entity_id)
            else:
                selected.discard(entity_id)
            values = sorted(selected)
            atomic_write_text(
                self._path,
                json.dumps(values, indent=2) + "\n",
            )
            self._write(
                values,
                self.read_climate(),
                self.read_security(),
                entity_names,
            )
            return values

    def read_climate(self) -> list[str]:
        payload = self._read_raw(self._climate_path)
        return sorted(item for item in payload if isinstance(item, str) and item.startswith("climate.")) if isinstance(payload, list) else []

    def save_climate(self, entity_id: str, included: bool, entity_names: dict[str, str]) -> list[str]:
        if not entity_id.startswith("climate."):
            raise ValueError("A climate entity is required.")
        with CONFIGURATION_ACTIVATION_LOCK, self._lock:
            selected = set(self.read_climate())
            if included:
                selected.add(entity_id)
            else:
                selected.discard(entity_id)
            values = sorted(selected)
            atomic_write_text(
                self._climate_path,
                json.dumps(values, indent=2) + "\n",
            )
            self._write(
                self.read(),
                values,
                self.read_security(),
                entity_names,
            )
            return values

    def read_security(self) -> list[str]:
        payload = self._read_raw(self._security_path)
        return sorted(
            item
            for item in payload
            if isinstance(item, str) and item.startswith("binary_sensor.")
        ) if isinstance(payload, list) else []

    def save_security(
        self,
        entity_id: str,
        included: bool,
        entity_names: dict[str, str],
    ) -> list[str]:
        if not entity_id.startswith("binary_sensor.") or entity_id not in entity_names:
            raise ValueError("A door sensor is required.")
        with CONFIGURATION_ACTIVATION_LOCK, self._lock:
            selected = set(self.read_security())
            if included:
                selected.add(entity_id)
            else:
                selected.discard(entity_id)
            values = sorted(selected)
            atomic_write_text(
                self._security_path,
                json.dumps(values, indent=2) + "\n",
            )
            self._write(
                self.read(),
                self.read_climate(),
                values,
                entity_names,
            )
            return values

    def _write(
        self,
        lights: list[str],
        climate: list[str],
        security: list[str],
        names: dict[str, str],
    ) -> None:
        lines = ["# Managed by Future Homes Tech App.\n", "homekit:\n"]
        for bridge_name, port, entities in (
            ("FHT HomeKit Lights", 21063, lights),
            ("FHT HomeKit Climate", 21064, climate),
            ("FHT HomeKit Security", 21065, security),
        ):
            if not entities:
                continue
            lines.extend(
                [
                    f"  - name: {bridge_name}\n",
                    f"    port: {port}\n",
                    "    filter:\n",
                    "      include_entities:\n",
                ]
            )
            lines.extend(f"        - {json.dumps(value)}\n" for value in entities)
            lines.append("    entity_config:\n")
            for value in entities:
                lines.extend([f"      {json.dumps(value)}:\n", f"        name: {json.dumps(names.get(value, value))}\n"])
        atomic_write_text(self._package_path, "".join(lines))

    def rebuild_package(self, entity_names: dict[str, str]) -> None:
        """Write the bridge package from the saved selections as they are now."""
        with self._lock, CONFIGURATION_ACTIVATION_LOCK:
            self._write(self.read(), self.read_climate(), self.read_security(), entity_names)


class RoomAliases(JsonSettingsStore):
    """Persist App-only display names for Home Assistant Areas."""

    READ_ERROR = "Unable to read room aliases"
    SAVE_ERROR = "Unable to save room alias"

    def _clean(self, payload: Any) -> dict[str, str]:
        """Return valid room display aliases."""
        if not isinstance(payload, dict):
            return {}
        return {
            room: alias
            for room, alias in payload.items()
            if isinstance(room, str)
            and room.strip()
            and isinstance(alias, str)
            and alias.strip()
        }

    def save(self, room: str, alias: str) -> dict[str, str]:
        """Create, update, or remove one room alias."""
        room = room.strip()
        alias = alias.strip()
        if not room:
            raise ValueError("A room name is required.")
        if len(room) > 100 or len(alias) > 100:
            raise ValueError("Room names must be 100 characters or fewer.")
        with self._lock:
            payload = self._read_dict()
            if alias and alias.casefold() != room.casefold():
                payload[room] = alias
            else:
                payload.pop(room, None)
            self._write_unlocked(payload)
        return self.read()


class RoomModeSettings(JsonSettingsStore):
    """Persist enabled App room modes by area."""

    AVAILABLE_MODES = (
        ("sleep", "Sleep"),
        ("quiet", "Quiet"),
        ("wake_up", "Wake Up"),
        ("game", "Game"),
        ("relax", "Relax"),
        ("movie", "Movie"),
        ("study", "Study"),
        ("chill", "Chill"),
        ("infant", "Infant"),
        ("toddler", "Toddler"),
        ("baby", "Baby"),
        ("armed_away", "Armed Away"),
        ("armed_stay_kids", "Armed Stay Kids"),
        ("armed_stay_adult", "Armed Stay Adult"),
        ("disarmed", "Disarmed"),
    )
    HELPER_MODES = (
        ("day", "Day"),
        ("night", "Night"),
        *AVAILABLE_MODES,
    )
    CATALOG = {"bedroom": AVAILABLE_MODES}
    ALLOWED_MODES = frozenset(mode for mode, _label in AVAILABLE_MODES)
    ALARM_MODES = frozenset(("armed_away", "armed_stay_kids", "armed_stay_adult", "disarmed"))
    READ_ERROR = "Unable to read room modes"
    SAVE_ERROR = "Unable to save room modes"

    @classmethod
    def catalog(cls) -> dict[str, list[dict[str, str]]]:
        """Return the room-type mode catalog for the interface."""
        return {
            room_type: [
                {"id": mode, "label": label}
                for mode, label in cls.AVAILABLE_MODES
            ]
            for room_type in cls.CATALOG
        }

    def _clean(self, payload: Any) -> dict[str, list[str]]:
        """Return valid enabled modes by area."""
        if not isinstance(payload, dict):
            return {}
        return {
            area: sorted(
                {
                    str(mode)
                    for mode in modes
                    if str(mode) in self.ALLOWED_MODES
                }
            )
            for area, modes in payload.items()
            if isinstance(area, str)
            and area.strip()
            and isinstance(modes, list)
        }

    def save(self, area: str, enabled_modes: Any, *, scope: str = "") -> dict[str, list[str]]:
        """Save one area's enabled room modes."""
        area = area.strip()
        if not area or len(area) > 100:
            raise ValueError("A valid area name is required.")
        if not isinstance(enabled_modes, list):
            raise ValueError("Enabled room modes must be a list.")
        normalized_modes = sorted(
            {
                str(mode)
                for mode in enabled_modes
                if str(mode) in self.ALLOWED_MODES
            }
        )
        if len(normalized_modes) != len(set(map(str, enabled_modes))):
            raise ValueError("One or more room modes are not supported.")
        if not isinstance(scope, str):
            raise ValueError("Invalid mode settings scope.")
        if scope == "room":
            editable_modes = self.ALLOWED_MODES - self.ALARM_MODES
        elif scope in self.ALARM_MODES:
            editable_modes = frozenset((scope,))
        elif scope == "":
            editable_modes = self.ALLOWED_MODES
        else:
            raise ValueError("Invalid mode settings scope.")
        if not set(normalized_modes) <= editable_modes:
            raise ValueError("The selected modes do not belong to this settings page.")
        with self._lock:
            payload = self._read_dict()
            previous_modes = payload.get(area, [])
            preserved_modes = {
                mode for mode in previous_modes
                if isinstance(mode, str) and mode in self.ALLOWED_MODES and mode not in editable_modes
            } if isinstance(previous_modes, list) else set()
            payload[area] = sorted(preserved_modes | set(normalized_modes))
            self._write_unlocked(payload)
        return self.read()


class WakeRoutineSettings(JsonSettingsStore):
    """Persist per-room weekly wake schedules and one-time override defaults."""

    DAYS = (
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    )
    DEFAULT = {
        "enabled": False,
        "times": {day: "" for day in DAYS},
        "actions": [],
        "target_entities": [],
        "brightness_pct": 100,
        "override_time": "07:00",
    }
    READ_ERROR = "Unable to read wake routines"
    SAVE_ERROR = "Unable to save wake routines"

    @staticmethod
    def _time(value: Any, allow_empty: bool = False) -> str:
        candidate = str(value or "").strip()
        if allow_empty and not candidate:
            return ""
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
            raise ValueError("Wake times must use 24-hour HH:MM format.")
        return candidate

    @classmethod
    def normalize(
        cls,
        value: Any,
        valid_entities: set[str] | None = None,
    ) -> dict[str, Any]:
        """Return one safe wake-routine configuration."""
        payload = value if isinstance(value, dict) else {}
        raw_times = payload.get("times", {})
        if not isinstance(raw_times, dict):
            raise ValueError("Wake schedule times must be an object.")
        raw_actions = payload.get("actions", [])
        if not isinstance(raw_actions, list):
            raise ValueError("Wake actions must be a list.")
        actions: list[dict[str, Any]] = []
        action_targets: list[str] = []
        for raw_action in raw_actions:
            if not isinstance(raw_action, dict):
                raise ValueError("Wake actions must be objects.")
            action_type = str(raw_action.get("type") or "")
            if action_type not in {
                "lights", "light_groups", "room_mode", "audio"
            }:
                raise ValueError("One or more wake action types are unsupported.")
            raw_entities = raw_action.get("entities", [])
            if not isinstance(raw_entities, list):
                raise ValueError("Wake action entities must be a list.")
            action_entities = sorted({
                str(entity_id).strip()
                for entity_id in raw_entities
                if str(entity_id).strip()
            })
            if action_type in {"lights", "light_groups"}:
                expected_prefix = (
                    "light.fht_" if action_type == "light_groups" else "light."
                )
                if any(
                    not entity_id.startswith(expected_prefix)
                    for entity_id in action_entities
                ):
                    raise ValueError("One or more wake action entities are invalid.")
                if action_type == "lights" and any(
                    entity_id.startswith("light.fht_")
                    for entity_id in action_entities
                ):
                    raise ValueError("Light groups must use the Light Groups function.")
                actions.append({"type": action_type, "entities": action_entities})
                action_targets.extend(action_entities)
                continue
            if action_type == "room_mode":
                entity_id = str(raw_action.get("entity_id") or "").strip()
                option = str(raw_action.get("option") or "").strip()
                if not re.fullmatch(r"input_select\.fht_[a-z0-9_]+_mode", entity_id):
                    raise ValueError("Wake room mode helper is invalid.")
                if not option or len(option) > 100:
                    raise ValueError("A valid wake room mode is required.")
                actions.append({
                    "type": action_type,
                    "entities": [],
                    "entity_id": entity_id,
                    "option": option,
                })
                continue
            if any(
                not entity_id.startswith("media_player.")
                for entity_id in action_entities
            ):
                raise ValueError("Wake audio targets must be media players.")
            if (
                valid_entities is not None
                and not set(action_entities).issubset(valid_entities)
            ):
                raise ValueError("One or more wake audio targets are unavailable.")
            media_content_id = str(
                raw_action.get("media_content_id") or ""
            ).strip()
            media_content_type = str(
                raw_action.get("media_content_type") or "music"
            ).strip()
            if len(media_content_id) > 500 or len(media_content_type) > 100:
                raise ValueError("Wake audio settings are too long.")
            actions.append({
                "type": action_type,
                "entities": action_entities,
                "media_content_id": media_content_id,
                "media_content_type": media_content_type or "music",
            })
        raw_targets = payload.get("target_entities", action_targets)
        if not isinstance(raw_targets, list):
            raise ValueError("Wake targets must be a list.")
        targets = sorted({
            str(entity_id).strip()
            for entity_id in raw_targets
            if str(entity_id).strip()
        })
        if any(not target.startswith(("light.", "switch.")) for target in targets):
            raise ValueError("Wake targets must be lights, switches, or plugs.")
        if valid_entities is not None and not set(targets).issubset(valid_entities):
            raise ValueError("One or more wake targets are unavailable.")
        try:
            brightness = int(payload.get("brightness_pct", 100))
        except (TypeError, ValueError) as err:
            raise ValueError("Wake brightness must be a whole percentage.") from err
        if not 1 <= brightness <= 100:
            raise ValueError("Wake brightness must be between 1 and 100 percent.")
        return {
            "enabled": bool(payload.get("enabled")),
            "times": {
                day: cls._time(raw_times.get(day), allow_empty=True)
                for day in cls.DAYS
            },
            "actions": actions,
            "target_entities": targets,
            "brightness_pct": brightness,
            "override_time": cls._time(payload.get("override_time") or "07:00"),
        }

    def _clean(self, payload: Any) -> dict[str, dict[str, Any]]:
        """Return all saved room wake routines."""
        if not isinstance(payload, dict):
            return {}
        return {
            area: self.normalize(value)
            for area, value in payload.items()
            if isinstance(area, str) and area.strip()
        }

    def save(
        self,
        area: str,
        value: Any,
        valid_entities: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Save one room wake routine."""
        area = area.strip()
        if not area or len(area) > 100:
            raise ValueError("A valid area name is required.")
        setting = self.normalize(value, valid_entities)
        with self._lock:
            payload = self._read_dict()
            payload[area] = setting
            self._write_unlocked(payload)
        return self.read()


class BedroomModeSettings(JsonSettingsStore):
    """Persist functional bedroom security and day/night mode settings."""

    SOLAR_EVENTS = frozenset({"sunrise", "sunset"})
    DEFAULT = {
        "armed_away_enabled": False,
        "armed_away_notify_targets": [],
        "random_lights_enabled": False,
        "random_start_event": "sunset",
        "random_start_offset": -30,
        "random_end_event": "sunrise",
        "random_end_offset": 30,
        "armed_stay_kids_enabled": False,
        "armed_stay_kids_notify_targets": [],
        "kids_door_sensors": [],
        "disarmed_enabled": True,
        "day_event": "sunrise",
        "day_offset": 0,
        "night_event": "sunset",
        "night_offset": -15,
        "toddler_enabled": False,
        "toddler_door_sensor": "",
        "toddler_light_entities": [],
        "toddler_brightness": 35,
        "toddler_color": "#35aef7",
        "toddler_chime_entities": [],
        "toddler_chime_repeats": 1,
        "toddler_chime_interval_seconds": 5,
        "toddler_timeout_minutes": 30,
        "toddler_indicator_effect_entity": "",
        "toddler_indicator_effect": "",
        "toddler_indicator_off_effect": "Off",
        "toddler_indicator_color_entity": "",
        "toddler_indicator_color": 170,
        "toddler_indicator_brightness_entity": "",
        "toddler_indicator_brightness": 100,
    }
    READ_ERROR = "Unable to read bedroom modes"
    SAVE_ERROR = "Unable to save bedroom modes"

    @classmethod
    def normalize(
        cls,
        value: Any,
        valid_door_sensors: set[str] | None = None,
        valid_entities: set[str] | None = None,
    ) -> dict[str, Any]:
        """Return one safe bedroom mode configuration."""
        payload = value if isinstance(value, dict) else {}

        def solar_event(name: str) -> str:
            event = str(payload.get(name) or cls.DEFAULT[name])
            if event not in cls.SOLAR_EVENTS:
                raise ValueError("Bedroom mode timing must use sunrise or sunset.")
            return event

        def solar_offset(name: str) -> int:
            try:
                offset = int(payload.get(name, cls.DEFAULT[name]))
            except (TypeError, ValueError) as err:
                raise ValueError("Bedroom mode offsets must be whole minutes.") from err
            if not -120 <= offset <= 120:
                raise ValueError("Bedroom mode offsets must be between -120 and 120 minutes.")
            return offset

        raw_sensors = payload.get("kids_door_sensors", [])
        if not isinstance(raw_sensors, list):
            raise ValueError("Kids mode door sensors must be a list.")
        sensors = sorted({
            str(entity_id)
            for entity_id in raw_sensors
            if str(entity_id).startswith("binary_sensor.")
        })
        if len(sensors) != len(set(map(str, raw_sensors))):
            raise ValueError("One or more Kids mode door sensors are invalid.")
        if valid_door_sensors is not None and not set(sensors).issubset(valid_door_sensors):
            raise ValueError("One or more Kids mode door sensors are unavailable.")

        def entity_id(name: str, prefixes: tuple[str, ...]) -> str:
            candidate = str(payload.get(name) or "").strip()
            if candidate and not candidate.startswith(prefixes):
                raise ValueError("One or more Toddler mode entities are invalid.")
            if valid_entities is not None and candidate and candidate not in valid_entities:
                raise ValueError("One or more Toddler mode entities are unavailable.")
            return candidate

        def entity_list(name: str, prefixes: tuple[str, ...]) -> list[str]:
            raw_values = payload.get(name, [])
            if not isinstance(raw_values, list):
                raise ValueError("Toddler mode entity selections must be a list.")
            values = sorted({str(item).strip() for item in raw_values if str(item).strip()})
            if any(not item.startswith(prefixes) for item in values):
                raise ValueError("One or more Toddler mode entities are invalid.")
            if valid_entities is not None and not set(values).issubset(valid_entities):
                raise ValueError("One or more Toddler mode entities are unavailable.")
            return values

        def integer(name: str, minimum: int, maximum: int) -> int:
            try:
                result = int(payload.get(name, cls.DEFAULT[name]))
            except (TypeError, ValueError) as err:
                raise ValueError("Toddler mode values must be whole numbers.") from err
            if not minimum <= result <= maximum:
                raise ValueError(
                    f"Toddler mode values must be between {minimum} and {maximum}."
                )
            return result

        toddler_door_sensor = entity_id("toddler_door_sensor", ("binary_sensor.",))
        if (
            valid_door_sensors is not None
            and toddler_door_sensor
            and toddler_door_sensor not in valid_door_sensors
        ):
            raise ValueError("The Toddler mode door sensor is unavailable.")
        toddler_color = str(
            payload.get("toddler_color") or cls.DEFAULT["toddler_color"]
        ).strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", toddler_color):
            raise ValueError("Toddler mode color must be a valid hex color.")
        return {
            "armed_away_enabled": bool(payload.get("armed_away_enabled", False)),
            "armed_away_notify_targets": phone_notify_targets(
                payload.get("armed_away_notify_targets")
            ),
            "random_lights_enabled": bool(payload.get("random_lights_enabled", False)),
            "random_start_event": solar_event("random_start_event"),
            "random_start_offset": solar_offset("random_start_offset"),
            "random_end_event": solar_event("random_end_event"),
            "random_end_offset": solar_offset("random_end_offset"),
            "armed_stay_kids_enabled": bool(payload.get("armed_stay_kids_enabled", False)),
            "armed_stay_kids_notify_targets": phone_notify_targets(
                payload.get("armed_stay_kids_notify_targets")
            ),
            "kids_door_sensors": sensors,
            "disarmed_enabled": bool(payload.get("disarmed_enabled", True)),
            "day_event": solar_event("day_event"),
            "day_offset": solar_offset("day_offset"),
            "night_event": solar_event("night_event"),
            "night_offset": solar_offset("night_offset"),
            "toddler_enabled": bool(payload.get("toddler_enabled", False)),
            "toddler_door_sensor": toddler_door_sensor,
            "toddler_light_entities": entity_list(
                "toddler_light_entities", ("light.",)
            ),
            "toddler_brightness": integer("toddler_brightness", 1, 100),
            "toddler_color": toddler_color.lower(),
            "toddler_chime_entities": entity_list(
                "toddler_chime_entities", ("button.",)
            ),
            "toddler_chime_repeats": integer("toddler_chime_repeats", 1, 10),
            "toddler_chime_interval_seconds": integer(
                "toddler_chime_interval_seconds", 1, 300
            ),
            "toddler_timeout_minutes": integer("toddler_timeout_minutes", 0, 240),
            "toddler_indicator_effect_entity": entity_id(
                "toddler_indicator_effect_entity", ("select.",)
            ),
            "toddler_indicator_effect": str(
                payload.get("toddler_indicator_effect") or ""
            ).strip(),
            "toddler_indicator_off_effect": str(
                payload.get("toddler_indicator_off_effect") or "Off"
            ).strip(),
            "toddler_indicator_color_entity": entity_id(
                "toddler_indicator_color_entity", ("number.", "select.")
            ),
            "toddler_indicator_color": integer("toddler_indicator_color", 0, 255),
            "toddler_indicator_brightness_entity": entity_id(
                "toddler_indicator_brightness_entity", ("number.",)
            ),
            "toddler_indicator_brightness": integer(
                "toddler_indicator_brightness", 1, 100
            ),
        }

    def _clean(self, payload: Any) -> dict[str, dict[str, Any]]:
        """Return every valid bedroom configuration."""
        if not isinstance(payload, dict):
            return {}
        settings = {}
        for area, value in payload.items():
            if not isinstance(area, str) or not area.strip():
                continue
            try:
                settings[area] = self.normalize(value)
            except ValueError:
                continue
        return settings

    def save(
        self,
        area: str,
        value: Any,
        valid_door_sensors: set[str],
        valid_entities: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Create or update one bedroom mode configuration."""
        area = area.strip()
        if not area or len(area) > 100:
            raise ValueError("A valid bedroom area is required.")
        setting = self.normalize(value, valid_door_sensors, valid_entities)
        with self._lock:
            payload = self._read_dict()
            payload[area] = setting
            self._write_unlocked(payload)
        return self.read()


class DoorLightGroupAssignments(JsonSettingsStore):
    """Persist door-sensor-to-FHT-light-group assignments."""

    READ_ERROR = "Unable to read door assignments"
    SAVE_ERROR = "Unable to save door assignment"

    def _clean(self, payload: Any) -> dict[str, str]:
        return {
            door_id: group_id
            for door_id, group_id in payload.items()
            if isinstance(door_id, str)
            and door_id.startswith("binary_sensor.")
            and isinstance(group_id, str)
            and group_id.startswith(LIGHT_GROUP_ENTITY_PREFIX)
        } if isinstance(payload, dict) else {}

    def save(self, door_id: str, group_id: str) -> dict[str, str]:
        if not door_id.startswith("binary_sensor."):
            raise ValueError("A valid door sensor is required.")
        if group_id and not group_id.startswith(LIGHT_GROUP_ENTITY_PREFIX):
            raise ValueError("A Future Homes Tech light group is required.")
        with self._lock:
            payload = self._read_dict()
            if group_id:
                payload[door_id] = group_id
            else:
                payload.pop(door_id, None)
            self._write_unlocked(payload)
        return self.read()


def apply_room_aliases(
    entities: list[dict[str, Any]],
    aliases: dict[str, str],
) -> None:
    """Mask room text for App display without changing entity IDs."""
    replacements = sorted(
        aliases.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for entity in entities:
        original_area = _clean_value(entity.get("area"))
        original_name = _clean_value(entity.get("friendly_name"))
        entity["original_area"] = original_area
        entity["original_friendly_name"] = original_name
        alias = aliases.get(original_area)
        if alias:
            entity["area"] = alias
        if original_name:
            display_name = original_name
            for room, room_alias in replacements:
                display_name = re.sub(
                    re.escape(room),
                    lambda _match, replacement=room_alias: replacement,
                    display_name,
                    flags=re.IGNORECASE,
                )
            entity["friendly_name"] = display_name

class SwitchBrightnessOverride:
    """Build quick-cycle overrides for physical dimmable light targets."""

    @staticmethod
    def helper(entity_id: str) -> str:
        return "input_boolean.fht_bright_" + hashlib.sha1(entity_id.encode()).hexdigest()[:16]

    @staticmethod
    def light_members(entity_id: str, entities: dict[str, dict[str, Any]], seen=frozenset()) -> list[str]:
        if entity_id in seen or not entity_id.startswith("light.") or entity_id not in entities:
            return []
        entity = entities[entity_id]
        children = entity.get("members") or []
        if children:
            return sorted({leaf for child in children for leaf in SwitchBrightnessOverride.light_members(child, entities, seen | {entity_id})})
        return [entity_id]

    @classmethod
    def targets(cls, entities, automations):
        by_id = {entity["entity_id"]: entity for entity in entities}
        inovelli_devices = {entity.get("device_id") for entity in entities
                            if "inovelli" in str(entity.get("manufacturer", "")).lower()
                            or "inovelli" in str(entity.get("device_name", "")).lower()
                            or (entity.get("domain") == "event" and re.search(r"_button_(up|down|config)$", entity["entity_id"]))}
        result = {}
        for entity in entities:
            source = entity["entity_id"]
            if entity.get("domain") != "switch" or (entity.get("device_id") and entity.get("device_id") in inovelli_devices):
                continue
            if "inovelli" in str(entity.get("manufacturer", "")).lower():
                continue
            targets = set(entity.get("wired_load_ids") or [])
            targets.update(item.get("target_entity_id", "") for item in automations
                           if item.get("trigger_entity_id") == source and item.get("trigger_kind") == "state" and item.get("target_domain") == "light")
            lights = sorted({leaf for target in targets for leaf in cls.light_members(target, by_id)
                             if set(by_id[leaf].get("supported_color_modes") or []) & {"brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white"}})
            if lights:
                result[source] = lights
        return result

    @classmethod
    def render(cls, targets):
        lights = sorted({light for members in targets.values() for light in members})
        helpers = {cls.helper(light).split(".", 1)[1]: {"name": f"FHT Brightness Override {light}", "initial": False} for light in lights}
        automations = []
        physical = "{{ trigger.to_state.context.parent_id is none and trigger.to_state.context.user_id is none }}"
        for source, members in targets.items():
            helper_ids = [cls.helper(light) for light in members]
            automations.append({
                "id": "fht_quick_bright_" + hashlib.sha1(source.encode()).hexdigest()[:16],
                "alias": f"FHT - {source} Quick Brightness Override", "mode": "restart",
                "triggers": [{"trigger": "state", "entity_id": source, "from": "on", "to": "off"}],
                "conditions": [{"condition": "template", "value_template": physical}],
                "actions": [
                    {"wait_for_trigger": [{"trigger": "state", "entity_id": source, "from": "off", "to": "on"}], "timeout": "00:00:03", "continue_on_timeout": False},
                    {"condition": "template", "value_template": "{{ wait.trigger is not none and wait.trigger.to_state.context.parent_id is none and wait.trigger.to_state.context.user_id is none }}"},
                    {"action": "input_boolean.turn_on", "target": {"entity_id": helper_ids}},
                    {"action": "light.turn_on", "target": {"entity_id": members}, "data": {"brightness_pct": 100}},
                ],
            })
        for light in lights:
            automations.append({
                "id": "fht_bright_clear_" + hashlib.sha1(light.encode()).hexdigest()[:16],
                "alias": f"FHT - {light} Clear Brightness Override", "mode": "restart",
                "triggers": [{"trigger": "state", "entity_id": light, "to": "off"}],
                "actions": [{"condition": "state", "entity_id": light, "state": "off"}, {"action": "input_boolean.turn_off", "target": {"entity_id": cls.helper(light)}}],
            })
        return helpers, automations

    @classmethod
    def presence_guard(cls, target, entities):
        lights = cls.light_members(target, {entity["entity_id"]: entity for entity in entities})
        helpers = [cls.helper(light) for light in lights]
        return "{{ expand(" + repr(helpers) + ") | selectattr('state', 'eq', 'on') | list | count == 0 }}"


class ExhaustFanTimer:
    @staticmethod
    def eligible(entity):
        names = [entity.get("friendly_name", ""), *entity.get("wired_load_names", {}).values()]
        return entity.get("entity_id", "").startswith("switch.") and any(
            "exhaust" in str(name).lower() for name in names
        )

    @staticmethod
    def render(settings, entities, humidity=None, presence=None):
        eligible = {entity["entity_id"] for entity in entities if ExhaustFanTimer.eligible(entity)}
        return [{
            "id": "fht_exhaust_timer_" + hashlib.sha1(source.encode()).hexdigest()[:16],
            "alias": f"FHT - Exhaust Fan Timer {source}", "mode": "restart",
            "triggers": [
                {"trigger": "state", "entity_id": source, "to": "on"},
                {"trigger": "state", "entity_id": source, "to": "off"},
                {"trigger": "homeassistant", "event": "start"},
            ],
            "actions": [
                {"condition": "state", "entity_id": source, "state": "on"},
                *ExhaustFanHumidity.timer_arming_guard((humidity or {}).get(source) or (presence or {}).get(source)),
                {"delay": {"minutes": minutes}},
                {"condition": "state", "entity_id": source, "state": "on"},
                *ExhaustFanHumidity.timer_stop_guard((humidity or {}).get(source)),
                *ExhaustFanPresence.timer_stop_guard((presence or {}).get(source)),
                {"action": "switch.turn_off", "target": {"entity_id": source}},
            ],
        } for source, minutes in sorted(settings.items()) if source in eligible]


class ExhaustFanHumidity:
    """Run an exhaust fan automatically from a humidity sensor in the same room.

    The manual timer keeps its behaviour for fans without a sensor. For fans with a
    sensor the timer only arms when the fan was switched on by hand (not by an
    automation, so a humidity-started run is never cut short), and it skips the
    final turn-off while the room is still at or above the stop level; the humidity
    automation then turns the fan off once the air has stayed dry for two minutes.
    """

    START_RANGE = (50, 90)
    STOP_RANGE = (40, 80)
    DEFAULT_START = 65
    DEFAULT_STOP = 55
    DRY_MINUTES = 2

    @staticmethod
    def is_sensor(entity) -> bool:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id.startswith("sensor."):
            return False
        if str(entity.get("device_class") or "").casefold() == "humidity":
            return True
        names = f"{entity.get('friendly_name') or ''} {entity_id}".casefold()
        return str(entity.get("unit_of_measurement") or "").strip() == "%" and "humidity" in names

    @staticmethod
    def room_of(entity) -> str:
        """Return the room an entity was assigned to before any display alias."""
        return str((entity["original_area"] if "original_area" in entity else entity.get("area")) or "")

    @staticmethod
    def sensors(entities, room=None) -> list[dict[str, Any]]:
        """Return humidity sensors ready for a dropdown: one room's, or every room's when room is None."""
        matches = [
            {
                "entity_id": entity["entity_id"],
                "friendly_name": str(entity.get("friendly_name") or entity["entity_id"]),
                "state": entity.get("state"),
                "room": ExhaustFanHumidity.room_of(entity),
            }
            for entity in entities
            if ExhaustFanHumidity.is_sensor(entity)
            and (room is None or ExhaustFanHumidity.room_of(entity) == str(room or ""))
        ]
        return sorted(matches, key=lambda sensor: (sensor["room"], sensor["friendly_name"].casefold(), sensor["entity_id"]))

    @staticmethod
    def clean(sensor_id: Any, start_above: Any, stop_below: Any) -> dict[str, Any] | None:
        """Validate one pairing; an empty sensor means automatic mode is off."""
        sensor_id = str(sensor_id or "")
        if not sensor_id:
            return None
        if not sensor_id.startswith("sensor."):
            raise ValueError("Choose a humidity sensor.")
        start = ExhaustFanHumidity.DEFAULT_START if start_above is None else start_above
        stop = ExhaustFanHumidity.DEFAULT_STOP if stop_below is None else stop_below
        if type(start) is not int or not ExhaustFanHumidity.START_RANGE[0] <= start <= ExhaustFanHumidity.START_RANGE[1]:
            raise ValueError("Start above must be a whole number from 50 to 90 percent.")
        if type(stop) is not int or not ExhaustFanHumidity.STOP_RANGE[0] <= stop <= ExhaustFanHumidity.STOP_RANGE[1]:
            raise ValueError("Stop below must be a whole number from 40 to 80 percent.")
        if stop >= start:
            raise ValueError("Stop below must be lower than Start above.")
        return {"sensor": sensor_id, "start_above": start, "stop_below": stop}

    @staticmethod
    def normalize(raw: Any) -> dict[str, dict[str, Any]]:
        """Keep only valid saved pairings; anything malformed is dropped."""
        if not isinstance(raw, dict):
            return {}
        cleaned = {}
        for entity_id, entry in raw.items():
            if not isinstance(entity_id, str) or not entity_id.startswith("switch.") or not isinstance(entry, dict):
                continue
            try:
                valid = ExhaustFanHumidity.clean(entry.get("sensor"), entry.get("start_above"), entry.get("stop_below"))
            except ValueError:
                continue
            if valid:
                cleaned[entity_id] = valid
        return cleaned

    @staticmethod
    def timer_arming_guard(entry) -> list[dict[str, Any]]:
        """Arm the manual timer only for a fan switched on by hand, not by an automation."""
        if not entry:
            return []
        return [{"condition": "template", "value_template": "{{ trigger.to_state is not defined or trigger.to_state.context.parent_id is none }}"}]

    @staticmethod
    def timer_stop_guard(entry) -> list[dict[str, Any]]:
        """Let the manual timer turn the fan off only once the room is below the stop level."""
        if not entry:
            return []
        return [{"condition": "template", "value_template": f"{{{{ states({entry['sensor']!r}) | float(0) < {entry['stop_below']} }}}}"}]

    @staticmethod
    def render(settings, entities):
        eligible = {entity["entity_id"] for entity in entities if ExhaustFanTimer.eligible(entity)}
        automations = []
        for source, entry in sorted(settings.items()):
            if source not in eligible:
                continue
            sensor = entry["sensor"]
            automations.append({
                "id": "fht_exhaust_humidity_" + hashlib.sha1(source.encode()).hexdigest()[:16],
                "alias": f"FHT - Exhaust Fan Humidity {source}", "mode": "restart",
                "triggers": [
                    {"trigger": "numeric_state", "entity_id": sensor, "above": entry["start_above"], "id": "humid"},
                    {"trigger": "homeassistant", "event": "start", "id": "start"},
                    {"trigger": "numeric_state", "entity_id": sensor, "below": entry["stop_below"],
                     "for": {"minutes": ExhaustFanHumidity.DRY_MINUTES}, "id": "dry"},
                ],
                "actions": [{"choose": [
                    {
                        "conditions": [{"condition": "trigger", "id": "dry"}],
                        "sequence": [{"action": "switch.turn_off", "target": {"entity_id": source}}],
                    },
                    {
                        "conditions": [{"condition": "numeric_state", "entity_id": sensor, "above": entry["start_above"]}],
                        "sequence": [{"action": "switch.turn_on", "target": {"entity_id": source}}],
                    },
                ]}],
            })
        return automations


class ExhaustFanPresence:
    """Run an exhaust fan for a set time once someone is in the room.

    Once the presence sensor has seen someone for the activation delay the fan
    turns on and a Home Assistant timer starts for the run time (saved as
    clear_minutes). When the timer finishes the fan turns off, unless a paired
    humidity sensor still reads at or above its stop level (the humidity
    automation then finishes the run). Seeing someone again during the run
    neither restarts nor extends it. The timer keeps running through
    automation reloads and Home Assistant restarts; switching the fan off ends
    the run. The manual timer only arms for a fan switched on by hand and never
    turns the fan off while the room is occupied.
    """

    DELAY_RANGE = (0, 60)
    DEFAULT_ACTIVATION = 2
    DEFAULT_CLEAR = 5

    @staticmethod
    def is_sensor(entity, camera_devices=frozenset()) -> bool:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id.startswith("binary_sensor."):
            return False
        names = f"{entity.get('friendly_name') or ''} {entity_id}".casefold().replace("_", " ")
        if "door sensor" in names or is_sleep_number_entity(entity_id, entity.get("friendly_name")):
            return False
        if is_camera_entity(entity, set(camera_devices)):
            return False
        device_class = str(entity.get("device_class") or "").casefold()
        return device_class in {"occupancy", "motion", "presence"} or "presence" in names or "occupancy" in names

    @staticmethod
    def sensors(entities, room=None) -> list[dict[str, Any]]:
        """Presence sensors ready for a dropdown: one room's, or every room's when room is None."""
        cameras = camera_device_ids(entities)
        matches = [
            {
                "entity_id": entity["entity_id"],
                "friendly_name": str(entity.get("friendly_name") or entity["entity_id"]),
                "state": entity.get("state"),
                "room": ExhaustFanHumidity.room_of(entity),
            }
            for entity in entities
            if ExhaustFanPresence.is_sensor(entity, cameras)
            and (room is None or ExhaustFanHumidity.room_of(entity) == str(room or ""))
        ]
        return sorted(matches, key=lambda sensor: (sensor["room"], sensor["friendly_name"].casefold(), sensor["entity_id"]))

    @staticmethod
    def clean(sensor_id: Any, activation_minutes: Any, clear_minutes: Any) -> dict[str, Any] | None:
        """Validate one pairing; an empty sensor means presence control is off."""
        sensor_id = str(sensor_id or "")
        if not sensor_id:
            return None
        if not sensor_id.startswith("binary_sensor."):
            raise ValueError("Choose a presence sensor.")
        low, high = ExhaustFanPresence.DELAY_RANGE
        activation = ExhaustFanPresence.DEFAULT_ACTIVATION if activation_minutes is None else activation_minutes
        clear = ExhaustFanPresence.DEFAULT_CLEAR if clear_minutes is None else clear_minutes
        for value, label in ((activation, "Activation delay"), (clear, "Clear delay")):
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{label} must be a whole number of minutes from {low} to {high}.")
        return {"sensor": sensor_id, "activation_minutes": activation, "clear_minutes": clear}

    @staticmethod
    def normalize(raw: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(raw, dict):
            return {}
        cleaned = {}
        for entity_id, entry in raw.items():
            if not isinstance(entity_id, str) or not entity_id.startswith("switch.") or not isinstance(entry, dict):
                continue
            try:
                valid = ExhaustFanPresence.clean(entry.get("sensor"), entry.get("activation_minutes"), entry.get("clear_minutes"))
            except ValueError:
                continue
            if valid:
                cleaned[entity_id] = valid
        return cleaned

    @staticmethod
    def timer_stop_guard(entry) -> list[dict[str, Any]]:
        """Let the manual timer turn the fan off only once the room is clear."""
        if not entry:
            return []
        return [{"condition": "state", "entity_id": entry["sensor"], "state": "off"}]

    @staticmethod
    def timer_id(source: str) -> str:
        return "timer.fht_exhaust_run_" + hashlib.sha1(source.encode()).hexdigest()[:16]

    @staticmethod
    def timers(settings, entities) -> dict[str, dict[str, Any]]:
        """The run timer for each fan with presence control (at least one minute)."""
        eligible = {entity["entity_id"] for entity in entities if ExhaustFanTimer.eligible(entity)}
        timers = {}
        for source, entry in sorted(settings.items()):
            if source in eligible:
                minutes = max(1, int(entry["clear_minutes"]))
                timers[ExhaustFanPresence.timer_id(source).split(".", 1)[1]] = {
                    "name": f"FHT Exhaust Fan Run {source}",
                    "duration": f"{minutes // 60:02d}:{minutes % 60:02d}:00",
                    "restore": True,
                }
        return timers

    @staticmethod
    def render(settings, entities, humidity=None):
        eligible = {entity["entity_id"] for entity in entities if ExhaustFanTimer.eligible(entity)}
        automations = []
        for source, entry in sorted(settings.items()):
            if source not in eligible:
                continue
            sensor = entry["sensor"]
            humid = (humidity or {}).get(source)
            timer = ExhaustFanPresence.timer_id(source)
            automations.append({
                "id": "fht_exhaust_presence_" + hashlib.sha1(source.encode()).hexdigest()[:16],
                "alias": f"FHT - Exhaust Fan Presence {source}", "mode": "queued", "max": 10,
                "triggers": [
                    {"trigger": "state", "entity_id": sensor, "to": "on",
                     "for": {"minutes": entry["activation_minutes"]}, "id": "present"},
                    {"trigger": "event", "event_type": "timer.finished", "event_data": {"entity_id": timer}, "id": "done"},
                    {"trigger": "state", "entity_id": source, "to": "off", "id": "fan_off"},
                    {"trigger": "homeassistant", "event": "start", "id": "start"},
                ],
                "actions": [{"choose": [
                    {
                        # One run per arrival: seeing someone again during the run changes nothing.
                        "conditions": [
                            {"condition": "trigger", "id": "present"},
                            {"condition": "state", "entity_id": timer, "state": "idle"},
                        ],
                        "sequence": [
                            {"action": "switch.turn_on", "target": {"entity_id": source}},
                            {"action": "timer.start", "target": {"entity_id": timer}},
                        ],
                    },
                    {
                        "conditions": [
                            {"condition": "trigger", "id": "done"},
                            *ExhaustFanHumidity.timer_stop_guard(humid),
                        ],
                        "sequence": [{"action": "switch.turn_off", "target": {"entity_id": source}}],
                    },
                    {
                        "conditions": [
                            {"condition": "trigger", "id": "fan_off"},
                            {"condition": "state", "entity_id": timer, "state": ["active", "paused"]},
                        ],
                        "sequence": [{"action": "timer.cancel", "target": {"entity_id": timer}}],
                    },
                    {
                        # A run whose timer ran out while Home Assistant was off.
                        "conditions": [
                            {"condition": "trigger", "id": "start"},
                            {"condition": "state", "entity_id": source, "state": "on"},
                            {"condition": "state", "entity_id": timer, "state": "idle"},
                        ],
                        "sequence": [{"action": "timer.start", "target": {"entity_id": timer}}],
                    },
                ]}],
            })
        return automations


TONE_COLOR_MODES = frozenset({"color_temp", "hs", "xy", "rgb", "rgbw", "rgbww"})


def light_supports_tone(
    entity_id: str,
    entities_by_id: dict[str, dict[str, Any]],
    _seen: frozenset[str] = frozenset(),
) -> bool:
    """Return whether a colour tone can be applied to a light or light group.

    FHT light groups always take one; Home Assistant ignores it on members that
    cannot. A light the inventory does not describe is given the benefit of the
    doubt, while a light that only reports brightness or on/off is left alone.
    """
    if entity_id.startswith(LIGHT_GROUP_ENTITY_PREFIX):
        return True
    entity = entities_by_id.get(entity_id)
    if not isinstance(entity, dict):
        return True
    modes = entity.get("supported_color_modes") or []
    if set(modes) & TONE_COLOR_MODES or entity.get("min_color_temp_kelvin") is not None:
        return True
    seen = _seen | {entity_id}
    members = [
        str(member) for member in (entity.get("members") or [])
        if member and str(member) not in seen
    ]
    if members:
        return any(light_supports_tone(member, entities_by_id, seen) for member in members)
    return not modes


def tone_aware_light_setting(
    setting: dict[str, Any],
    entity_id: str,
    entities_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Keep a door rule's colour only for lights that can show it."""
    if light_supports_tone(entity_id, entities_by_id):
        return setting
    return {**setting, "color_mode": "current"}


class ControlAutomationManager:
    def _door_activation_template(self, automation: dict, automations: list[dict]) -> str:
        def priority(mode: str) -> int:
            if mode.startswith("room:") and mode.endswith(":sleep"):
                return 4
            return 3 if mode.startswith("room:") else 2 if mode.startswith("floor:") else 1 if mode == "sleep" else 0
        mode = automation["house_mode"]
        predicates = ["true" if automation.get("local_sleep_only") and mode in {"day", "night"} else self._door_mode_template(mode)[2:-2].strip()]
        overrides = {item.get("house_mode", "") for item in automations
                     if item.get("trigger_entity_id") == automation["trigger_entity_id"]
                     and priority(item.get("house_mode", "")) > priority(mode)}
        predicates.extend("not (" + self._door_mode_template(other)[2:-2].strip() + ")" for other in sorted(overrides))
        return "{{ " + " and ".join("(" + predicate + ")" for predicate in predicates) + " }}"

    def _door_condition_lines(self, automation: dict, automations: list[dict]) -> list[str]:
        lines = ["          - condition: and\n", "            conditions:\n", "              - condition: template\n",
                 "                value_template: " + json.dumps(self._door_activation_template(automation, automations)) + "\n"]
        mode = automation["house_mode"]
        if automation.get("local_sleep_only") and mode in {"day", "night"}:
            try:
                offsets = json.loads(self._path.with_name("future_homes_tech_bedroom_mode_automations.house.json").read_text())
            except (OSError, ValueError):
                offsets = {}
            day_offset = BedroomModeAutomationManager._offset_string(int(offsets.get("day_offset", 0)))
            night_offset = BedroomModeAutomationManager._offset_string(int(offsets.get("night_offset", 0)))
            if mode == "day":
                lines += ["              - condition: sun\n", "                after: sunrise\n", f"                after_offset: {json.dumps(day_offset)}\n", "                before: sunset\n", f"                before_offset: {json.dumps(night_offset)}\n"]
            else:
                lines += ["              - condition: or\n", "                conditions:\n", "                  - condition: sun\n", "                    before: sunrise\n", f"                    before_offset: {json.dumps(day_offset)}\n", "                  - condition: sun\n", "                    after: sunset\n", f"                    after_offset: {json.dumps(night_offset)}\n"]
        return lines

    def _door_mode_template(self, mode: str) -> str:
        if mode.startswith("room:"):
            _, slug, selected = mode.split(":", 2)
            return "{{ states(" + repr(f"input_select.fht_{slug}_mode") + ") | lower | replace(' ', '_') == " + repr(selected) + " }}"
        if mode.startswith("floor:"):
            floor_id = mode.split(":", 1)[1]
            try:
                settings = json.loads(self._path.with_name("future_homes_tech_bedroom_mode_automations.house.json").read_text())
                sources = settings.get("floor_sleep_modes", {}).get(floor_id, {}).get("sources", [])
            except (OSError, ValueError):
                sources = []
            return "{{ expand(" + repr(sources) + ") | selectattr('state', 'eq', 'Sleep') | list | count > 0 }}"
        return "{{ is_state(" + repr(HOUSE_MODE_HELPER) + ", " + repr(mode.title()) + ") }}"

    """Generate native Home Assistant automations for Controls."""

    def __init__(
        self,
        path: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
    ) -> None:
        self._path = path
        self._publisher = publisher

    @staticmethod
    def describe(
        assignments: dict[str, str],
        entities: list[dict[str, Any]],
        button_devices: list[dict[str, Any]] | None = None,
        mode_assignments: dict[str, str] | None = None,
        load_target_assignments: dict[str, str] | None = None,
        actual_loads: dict[str, str] | None = None,
        action_assignments: dict[str, list[str]] | None = None,
        action_settings: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """Describe direct switches and Matter gestures as automations."""
        mode_assignments = mode_assignments or {}
        load_target_assignments = load_target_assignments or {}
        actual_loads = actual_loads or {}
        action_assignments = action_assignments or {}
        action_settings = action_settings or {}
        names = {
            str(entity.get("entity_id") or ""): str(
                entity.get("friendly_name")
                or entity.get("entity_id")
                or ""
            )
            for entity in entities
        }
        button_names = {
            str(button.get("device_id") or ""): str(
                button.get("friendly_name") or "Button"
            )
            for button in button_devices or []
        }
        automations = []
        direct_assignments: dict[str, list[str]] = {}
        multi_assignment_ids = set(action_assignments)
        light_assignment_items = [
            (assignment_id, group_id, "")
            for assignment_id, group_id in assignments.items()
            if assignment_id not in multi_assignment_ids
        ]
        mode_assignment_items = [
            (assignment_id, target_id, "")
            for assignment_id, target_id in mode_assignments.items()
            if assignment_id not in multi_assignment_ids
        ]
        load_assignment_items = [
            (assignment_id, target_id, "")
            for assignment_id, target_id in load_target_assignments.items()
            if assignment_id not in multi_assignment_ids
        ]
        for assignment_id, actions in action_assignments.items():
            if (
                parse_door_assignment_id(assignment_id)[0]
                and not action_settings.get(assignment_id, {}).get("enabled", True)
            ):
                continue
            for action_value in actions:
                action_type, _, target_id = action_value.partition(":")
                target_domain = target_id.partition(".")[0]
                if action_type == "light_group" or (
                    action_type == "entity_target"
                    and target_domain == "light"
                ):
                    light_assignment_items.append(
                        (assignment_id, target_id, action_value)
                    )
                elif action_type in {
                    "actual_load",
                    "switch_target",
                    "entity_target",
                } and target_domain in {"switch", "fan"}:
                    load_assignment_items.append(
                        (assignment_id, target_id, action_value)
                    )
                elif action_type in {"room_mode", "wake_override"}:
                    mode_assignment_items.append(
                        (assignment_id, target_id, action_value)
                    )
        for assignment_id, group_id, action_key in sorted(
            light_assignment_items
        ):
            if (
                assignment_id in mode_assignments
                or assignment_id in load_target_assignments
            ) and not action_key:
                continue
            group_name = names.get(group_id) or group_id
            if assignment_id.startswith("button:"):
                trigger_parts = assignment_id.removeprefix("button:").split("|", 3)
                if len(trigger_parts) != 4:
                    continue
                device_id, domain, trigger_type, subtype = trigger_parts
                if not device_id or not domain or not trigger_type:
                    continue
                trigger_entity_id = ""
                event_type = ""
                action = "toggle"
                trigger_kind = "device"
                control_name = button_names.get(device_id, "Button")
                trigger_label = " ".join(
                    part.replace("_", " ")
                    for part in (subtype, trigger_type)
                    if part
                ).title()
            elif is_direct_control_entity_id(assignment_id):
                trigger_entity_id = assignment_id
                control_name = names.get(assignment_id) or assignment_id
                event_type = ""
                action = "mirror"
                trigger_kind = "state"
                controls = direct_assignments.setdefault(group_id, [])
                if assignment_id not in controls:
                    controls.append(assignment_id)
            elif assignment_id.startswith("door:"):
                trigger_entity_id, house_mode = parse_door_assignment_id(assignment_id)
                control_name = names.get(trigger_entity_id) or trigger_entity_id
                event_type = ""
                action = "mirror"
                trigger_kind = "door"
            else:
                trigger_entity_id, separator, event_type = (
                    assignment_id.partition("|")
                )
                if (
                    separator != "|"
                    or event_type not in INOVELLI_EVENT_TYPES
                ):
                    continue
                button_match = re.search(
                    r"_button_(up|down|config)$",
                    trigger_entity_id,
                    flags=re.IGNORECASE,
                )
                action = "toggle"
                trigger_kind = "event"
                if button_match:
                    button_name = button_match.group(1).casefold()
                    action = {
                        "up": "turn_on",
                        "down": "turn_off",
                        "config": "toggle",
                    }[button_name]
                event_name = names.get(trigger_entity_id) or trigger_entity_id
                control_name = (
                    f"{event_name} - "
                    f"{INOVELLI_EVENT_LABELS[event_type]}"
                )
            automations.append(
                {
                    "id": "fht_control_"
                    + hashlib.sha1(
                        (
                            f"{assignment_id}|{action_key}"
                            if action_key else assignment_id
                        ).encode("utf-8")
                    ).hexdigest()[:16],
                    "alias": f"FHT - {control_name} → {group_name}",
                    "assignment_id": assignment_id,
                    "trigger_entity_id": trigger_entity_id,
                    "device_id": device_id if assignment_id.startswith("button:") else "",
                    "device_domain": domain if assignment_id.startswith("button:") else "",
                    "device_trigger_type": trigger_type if assignment_id.startswith("button:") else "",
                    "device_subtype": subtype if assignment_id.startswith("button:") else "",
                    "trigger_label": trigger_label if assignment_id.startswith("button:") else "",
                    "event_type": event_type,
                    "trigger_kind": trigger_kind,
                    "action": action,
                    "action_label": {
                        "mirror": "Mirror ON / OFF",
                        "turn_on": "Turn On",
                        "turn_off": "Turn Off",
                        "toggle": "Toggle",
                    }[action],
                    "switch_entity_id": trigger_entity_id,
                    "light_group_entity_id": group_id,
                    "switch_name": control_name,
                    "light_group_name": group_name,
                    "target_entity_id": group_id,
                    "target_domain": "light",
                    "house_mode": house_mode if assignment_id.startswith("door:") else "",
                    "action_setting": action_settings.get(assignment_id, {}),
                }
            )
        for assignment_id, mode_target, action_key in sorted(
            mode_assignment_items
        ):
            mode_helper, _, mode_option = mode_target.partition("|")
            mode_option = mode_option or "Sleep"
            wake_override = mode_helper.startswith("input_button.fht_")
            device_id = ""
            domain = ""
            trigger_type = ""
            subtype = ""
            event_type = ""
            trigger_label = ""
            if assignment_id.startswith("button:"):
                trigger_parts = assignment_id.removeprefix("button:").split("|", 3)
                if len(trigger_parts) != 4:
                    continue
                device_id, domain, trigger_type, subtype = trigger_parts
                control_name = button_names.get(device_id, "Button")
                trigger_label = " ".join(
                    part.replace("_", " ")
                    for part in (subtype, trigger_type)
                    if part
                ).title()
                trigger_entity_id = ""
                trigger_kind = "device"
            elif is_direct_control_entity_id(assignment_id):
                trigger_entity_id = assignment_id
                control_name = names.get(assignment_id) or assignment_id
                trigger_kind = "state"
            elif assignment_id.startswith("door:"):
                trigger_entity_id, house_mode = parse_door_assignment_id(assignment_id)
                control_name = names.get(trigger_entity_id) or trigger_entity_id
                trigger_kind = "door"
            else:
                trigger_entity_id, separator, event_type = assignment_id.partition("|")
                if separator != "|" or event_type not in INOVELLI_EVENT_TYPES:
                    continue
                event_name = names.get(trigger_entity_id) or trigger_entity_id
                control_name = f"{event_name} - {INOVELLI_EVENT_LABELS[event_type]}"
                trigger_kind = "event"
            mode_name = re.sub(
                r"^(?:input_select|input_button)\.fht_|_(?:mode|wake_override)$",
                "",
                mode_helper,
            ).replace("_", " ").title()
            target_name = f"{mode_name} Wake Override" if wake_override else f"{mode_name} {mode_option} Mode"
            automations.append(
                {
                    "id": "fht_control_mode_"
                    + hashlib.sha1(
                        (
                            f"{assignment_id}|{action_key}"
                            if action_key else assignment_id
                        ).encode("utf-8")
                    ).hexdigest()[:16],
                    "alias": f"FHT - {control_name} → {target_name}",
                    "assignment_id": assignment_id,
                    "trigger_entity_id": trigger_entity_id,
                    "device_id": device_id,
                    "device_domain": domain,
                    "device_trigger_type": trigger_type,
                    "device_subtype": subtype,
                    "trigger_label": trigger_label,
                    "event_type": event_type,
                    "trigger_kind": trigger_kind,
                    "action": "wake_override" if wake_override else "room_mode",
                    "action_label": (
                        "Arm Next Wake Override"
                        if wake_override
                        else "Set Sleep / Restore Solar Mode"
                        if mode_option == "Sleep" and is_direct_control_entity_id(assignment_id)
                        else f"Set {mode_option} Mode"
                    ),
                    "switch_entity_id": trigger_entity_id,
                    "light_group_entity_id": "",
                    "switch_name": control_name,
                    "light_group_name": target_name,
                    "mode_entity_id": mode_helper,
                    "mode_option": mode_option,
                    "restore_on_off": is_direct_control_entity_id(assignment_id) and not wake_override,
                    "house_mode": house_mode if assignment_id.startswith("door:") else "",
                }
            )
        for assignment_id, target_switch_id, action_key in sorted(
            load_assignment_items
        ):
            target_domain = target_switch_id.partition(".")[0]
            if target_domain not in {"switch", "fan"}:
                continue
            load_name = (
                actual_loads.get(target_switch_id)
                or names.get(target_switch_id)
                or target_switch_id
            )
            if not load_name or assignment_id == target_switch_id:
                continue
            if assignment_id.startswith("button:"):
                trigger_parts = assignment_id.removeprefix("button:").split(
                    "|", 3
                )
                if len(trigger_parts) != 4:
                    continue
                device_id, domain, trigger_type, subtype = trigger_parts
                if not device_id or not domain or not trigger_type:
                    continue
                trigger_entity_id = ""
                event_type = ""
                action = "toggle"
                trigger_kind = "device"
                control_name = button_names.get(device_id, "Button")
                trigger_label = " ".join(
                    part.replace("_", " ")
                    for part in (subtype, trigger_type)
                    if part
                ).title()
            elif is_direct_control_entity_id(assignment_id):
                trigger_entity_id = assignment_id
                control_name = names.get(assignment_id) or assignment_id
                event_type = ""
                action = "mirror_load"
                trigger_kind = "state"
            elif assignment_id.startswith("door:"):
                trigger_entity_id, house_mode = parse_door_assignment_id(assignment_id)
                control_name = names.get(trigger_entity_id) or trigger_entity_id
                event_type = ""
                action = "mirror_load"
                trigger_kind = "door"
            else:
                trigger_entity_id, separator, event_type = (
                    assignment_id.partition("|")
                )
                if separator != "|" or event_type not in INOVELLI_EVENT_TYPES:
                    continue
                button_match = re.search(
                    r"_button_(up|down|config)$",
                    trigger_entity_id,
                    flags=re.IGNORECASE,
                )
                action = "toggle"
                trigger_kind = "event"
                if button_match:
                    action = {
                        "up": "turn_on",
                        "down": "turn_off",
                        "config": "toggle",
                    }[button_match.group(1).casefold()]
                event_name = names.get(trigger_entity_id) or trigger_entity_id
                control_name = (
                    f"{event_name} - {INOVELLI_EVENT_LABELS[event_type]}"
                )
            automations.append(
                {
                    "id": "fht_control_load_"
                    + hashlib.sha1(
                        (
                            f"{assignment_id}|{action_key}"
                            if action_key else assignment_id
                        ).encode("utf-8")
                    ).hexdigest()[:16],
                    "alias": f"FHT - {control_name} → {load_name}",
                    "assignment_id": assignment_id,
                    "trigger_entity_id": trigger_entity_id,
                    "device_id": (
                        device_id if assignment_id.startswith("button:") else ""
                    ),
                    "device_domain": (
                        domain if assignment_id.startswith("button:") else ""
                    ),
                    "device_trigger_type": (
                        trigger_type
                        if assignment_id.startswith("button:")
                        else ""
                    ),
                    "device_subtype": (
                        subtype if assignment_id.startswith("button:") else ""
                    ),
                    "trigger_label": (
                        trigger_label
                        if assignment_id.startswith("button:")
                        else ""
                    ),
                    "event_type": event_type,
                    "trigger_kind": trigger_kind,
                    "action": action,
                    "action_label": {
                        "mirror_load": "Mirror ON / OFF",
                        "turn_on": "Turn On",
                        "turn_off": "Turn Off",
                        "toggle": "Toggle",
                    }[action],
                    "switch_entity_id": trigger_entity_id,
                    "light_group_entity_id": "",
                    "switch_name": control_name,
                    "light_group_name": load_name,
                    "target_entity_id": target_switch_id,
                    "target_domain": target_domain,
                    "house_mode": house_mode if assignment_id.startswith("door:") else "",
                }
            )
        for group_id, switch_ids in sorted(direct_assignments.items()):
            group_name = names.get(group_id) or group_id
            switch_count = len(switch_ids)
            automations.append(
                {
                    "id": "fht_control_sync_"
                    + hashlib.sha1(group_id.encode("utf-8")).hexdigest()[:16],
                    "alias": (
                        f"FHT - Sync {group_name} → "
                        f"{switch_count} assigned control"
                        f"{'s' if switch_count != 1 else ''}"
                    ),
                    "assignment_id": group_id,
                    "trigger_entity_id": group_id,
                    "event_type": "",
                    "trigger_kind": "state",
                    "action": "sync_controls",
                    "action_label": "Sync Assigned Controls",
                    "switch_entity_id": ", ".join(switch_ids),
                    "light_group_entity_id": group_id,
                    "switch_name": (
                        f"{switch_count} assigned control"
                        f"{'s' if switch_count != 1 else ''}"
                    ),
                    "light_group_name": group_name,
                    "switch_entity_ids": switch_ids,
                }
            )
        entities_by_id = {entity.get("entity_id"): entity for entity in entities}
        for automation in automations:
            automation["local_sleep_only"] = is_bedroom_closet_door(entities_by_id.get(automation.get("trigger_entity_id"), {}))
        return [automation for automation in automations if not (automation["local_sleep_only"] and (automation.get("house_mode") == "sleep" or automation.get("house_mode", "").startswith("floor:")))]

    @staticmethod
    def _target_action_lines(
        action: str,
        entity_id: str,
        domain: str = "light",
    ) -> list[str]:
        """Run a button action once its assigned target is available."""
        lines = [
            "      - if:\n",
            "          - condition: template\n",
            "            value_template: \"{{ states("
            f"'{entity_id}') in ['unknown', 'unavailable'] }}}}\"\n",
            "        then:\n",
            "          - wait_template: \"{{ states("
            f"'{entity_id}') not in ['unknown', 'unavailable'] }}}}\"\n",
            '            timeout: "00:05:00"\n',
            "            continue_on_timeout: false\n",
            f"      - action: {domain}.{action}\n",
            "        target:\n",
            f"          entity_id: {entity_id}\n",
        ]
        if domain == "light" and action == "turn_on":
            lines.extend(
                [
                    "        data:\n",
                    "          brightness_pct: 100\n",
                ]
            )
        return lines

    @staticmethod
    def _door_light_data_lines(
        setting: dict[str, Any],
        indent: str,
    ) -> list[str]:
        """Render mode-specific brightness and color for a door light action."""
        normalized = SwitchControlSettings._clean_action_setting(setting)
        lines = [
            f"{indent}data:\n",
            f"{indent}  brightness_pct: {normalized['brightness_pct']}\n",
        ]
        if normalized["color_mode"] == "kelvin":
            lines.append(
                f"{indent}  color_temp_kelvin: {normalized['color_kelvin']}\n"
            )
        elif normalized["color_mode"] == "rgb":
            lines.append(
                f"{indent}  rgb_color: {json.dumps(normalized['color_rgb'])}\n"
            )
        elif normalized["color_mode"] == "adaptive":
            lines.append(
                f"{indent}  color_temp_kelvin: {json.dumps(LightScheduleAutomationManager._adaptive_kelvin_template())}\n"
            )
        return lines

    def sync(
        self,
        assignments: dict[str, str],
        entities: list[dict[str, Any]],
        button_devices: list[dict[str, Any]] | None = None,
        mode_assignments: dict[str, str] | None = None,
        load_target_assignments: dict[str, str] | None = None,
        actual_loads: dict[str, str] | None = None,
        action_assignments: dict[str, list[str]] | None = None,
        action_settings: dict[str, dict[str, Any]] | None = None,
        reload_automations: bool = True,
        exhaust_timers: dict[str, int] | None = None,
        exhaust_humidity: dict[str, dict[str, Any]] | None = None,
        exhaust_presence: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """Write Control assignments and reload Home Assistant."""
        automations = self.describe(
            assignments,
            entities,
            button_devices,
            mode_assignments,
            load_target_assignments,
            actual_loads,
            action_assignments,
            action_settings,
        )
        lines = [
            "# Managed by Future Homes Tech App. Changes may be overwritten.\n",
        ]
        override_helpers, override_automations = SwitchBrightnessOverride.render(SwitchBrightnessOverride.targets(entities, automations))
        override_automations.extend(ExhaustFanTimer.render(exhaust_timers or {}, entities, exhaust_humidity or {}, exhaust_presence or {}))
        override_automations.extend(ExhaustFanHumidity.render(exhaust_humidity or {}, entities))
        override_automations.extend(ExhaustFanPresence.render(exhaust_presence or {}, entities, exhaust_humidity or {}))
        exhaust_run_timers = ExhaustFanPresence.timers(exhaust_presence or {}, entities)
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity
            for entity in entities
            if isinstance(entity, dict)
        }
        if not automations and not override_automations:
            lines.append("automation: []\n")
        else:
            lines.append("automation:\n")
            for automation in automations:
                lines.extend([
                    f"  - id: {json.dumps(automation['id'])}\n",
                    f"    alias: {json.dumps(automation['alias'])}\n",
                    "    mode: restart\n",
                ])
                if automation["action"] == "wake_override":
                    lines.append("    triggers:\n")
                    if automation["device_id"]:
                        lines.extend([
                            "      - trigger: device\n",
                            f"        domain: {automation['device_domain']}\n",
                            f"        device_id: {automation['device_id']}\n",
                            f"        type: {automation['device_trigger_type']}\n",
                            *([f"        subtype: {automation['device_subtype']}\n"] if automation["device_subtype"] else []),
                        ])
                    elif automation.get("trigger_kind") in {"state", "door"}:
                        lines.extend([
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            '        to: "on"\n',
                        ])
                    else:
                        lines.extend([
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            "    conditions:\n",
                            "      - condition: template\n",
                            "        value_template: >-\n",
                            "          {{ trigger.to_state is not none and trigger.to_state.attributes.event_type == "
                            f"'{automation['event_type']}' }}}}\n",
                        ])
                    lines.extend([
                        "    actions:\n",
                        "      - action: input_button.press\n",
                        f"        target: {{entity_id: {automation['mode_entity_id']}}}\n",
                    ])
                elif automation["action"] == "room_mode":
                    lines.append("    triggers:\n")
                    if automation["restore_on_off"]:
                        lines.extend([
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            '        to: "on"\n',
                            "        id: activate\n",
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            '        to: "off"\n',
                            "        id: restore\n",
                        ])
                    elif automation["device_id"]:
                        lines.extend([
                            "      - trigger: device\n",
                            f"        domain: {automation['device_domain']}\n",
                            f"        device_id: {automation['device_id']}\n",
                            f"        type: {automation['device_trigger_type']}\n",
                            *(
                                [f"        subtype: {automation['device_subtype']}\n"]
                                if automation["device_subtype"] else []
                            ),
                            "        id: activate\n",
                        ])
                    elif automation.get("trigger_kind") == "door":
                        lines.extend([
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            '        to: "on"\n',
                            "        id: activate\n",
                        ])
                    else:
                        lines.extend([
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            "        id: activate\n",
                            "    conditions:\n",
                            "      - condition: template\n",
                            "        value_template: >-\n",
                            "          {{ trigger.to_state is not none and trigger.to_state.attributes.event_type == "
                            f"'{automation['event_type']}' }}}}\n",
                        ])
                    lines.extend([
                        "    actions:\n",
                        "      - choose:\n",
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: activate\n",
                        "            sequence:\n",
                        "              - action: input_select.select_option\n",
                        f"                target: {{entity_id: {automation['mode_entity_id']}}}\n",
                        f"                data: {{option: {automation['mode_option']}}}\n",
                    ])
                    if automation["restore_on_off"]:
                        lines.extend([
                            "          - conditions:\n",
                            "              - condition: trigger\n",
                            "                id: restore\n",
                            "              - condition: state\n",
                            f"                entity_id: {automation['mode_entity_id']}\n",
                            f"                state: {automation['mode_option']}\n",
                            "            sequence:\n",
                            "              - choose:\n",
                            "                  - conditions: >-\n",
                            f"                      {{{{ 'away' in states('{PROTECT_STATUS_HELPER}') | lower }}}}\n",
                            "                    sequence:\n",
                            "                      - action: input_select.select_option\n",
                            f"                        target: {{entity_id: {automation['mode_entity_id']}}}\n",
                            "                        data: {option: Armed Away}\n",
                            "                  - conditions: >-\n",
                            f"                      {{{{ 'stay' in states('{PROTECT_STATUS_HELPER}') | lower }}}}\n",
                            "                    sequence:\n",
                            "                      - action: input_select.select_option\n",
                            f"                        target: {{entity_id: {automation['mode_entity_id']}}}\n",
                            "                        data: {option: Armed Stay Kids}\n",
                            "                  - conditions:\n",
                            "                      - condition: state\n",
                            "                        entity_id: sun.sun\n",
                            "                        state: above_horizon\n",
                            "                    sequence:\n",
                            "                      - action: input_select.select_option\n",
                            f"                        target: {{entity_id: {automation['mode_entity_id']}}}\n",
                            "                        data: {option: Day}\n",
                            "                default:\n",
                            "                  - action: input_select.select_option\n",
                            f"                    target: {{entity_id: {automation['mode_entity_id']}}}\n",
                            "                    data: {option: Night}\n",
                        ])
                elif automation["action"] == "sync_controls":
                    lines.extend(
                        [
                            "    triggers:\n",
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            '        to: "on"\n',
                            "        id: turn_on\n",
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            '        to: "off"\n',
                            "        id: turn_off\n",
                            "    actions:\n",
                            "      - choose:\n",
                            "          - conditions:\n",
                            "              - condition: trigger\n",
                            "                id: turn_on\n",
                            "            sequence:\n",
                        ]
                    )
                    for switch_id in automation["switch_entity_ids"]:
                        switch_domain = switch_id.partition(".")[0]
                        lines.extend(
                            [
                                "              - if:\n",
                                "                  - condition: state\n",
                                f"                    entity_id: {switch_id}\n",
                                '                    state: "off"\n',
                                "                then:\n",
                                f"                  - action: {switch_domain}.turn_on\n",
                                "                    target:\n",
                                f"                      entity_id: {switch_id}\n",
                            ]
                        )
                    lines.extend(
                        [
                            "          - conditions:\n",
                            "              - condition: trigger\n",
                            "                id: turn_off\n",
                            "            sequence:\n",
                        ]
                    )
                    for switch_id in automation["switch_entity_ids"]:
                        switch_domain = switch_id.partition(".")[0]
                        lines.extend(
                            [
                                "              - if:\n",
                                "                  - condition: state\n",
                                f"                    entity_id: {switch_id}\n",
                                '                    state: "on"\n',
                                "                then:\n",
                                f"                  - action: {switch_domain}.turn_off\n",
                                "                    target:\n",
                                f"                      entity_id: {switch_id}\n",
                            ]
                        )
                elif automation["device_id"]:
                    lines.extend(
                        [
                            "    triggers:\n",
                            "      - trigger: device\n",
                            f"        domain: {automation['device_domain']}\n",
                            f"        device_id: {automation['device_id']}\n",
                            f"        type: {automation['device_trigger_type']}\n",
                            *(
                                [f"        subtype: {automation['device_subtype']}\n"]
                                if automation["device_subtype"]
                                else []
                            ),
                            "    actions:\n",
                        ]
                    )
                    lines.extend(
                        self._target_action_lines(
                            "toggle",
                            automation.get("target_entity_id")
                            or automation["light_group_entity_id"],
                            automation.get("target_domain") or "light",
                        )
                    )
                elif automation["action"] in {"mirror", "mirror_load"}:
                    target_entity_id = (
                        automation.get("target_entity_id")
                        or automation["light_group_entity_id"]
                    )
                    target_domain = automation.get("target_domain") or "light"
                    door_timeout = (
                        automation.get("action_setting", {}).get("timeout_minutes", 0)
                        if automation.get("trigger_kind") == "door"
                        else 0
                    )
                    trigger_entity_id = automation["trigger_entity_id"]
                    lines.extend(
                        [
                        "    triggers:\n",
                        "      - trigger: state\n",
                        f"        entity_id: {trigger_entity_id}\n",
                        '        to: "on"\n',
                        # A sensor that drops out and comes back open is not a
                        # new opening: it must not restart the door timeout.
                        *(["        not_from: [unavailable, unknown]\n"] if door_timeout else []),
                        "        id: turn_on\n",
                        "      - trigger: state\n",
                        f"        entity_id: {trigger_entity_id}\n",
                        '        to: "off"\n',
                        "        id: turn_off\n",
                        # Backup for the timeout delay, which a Home Assistant
                        # restart or automation reload cancels: fires once the
                        # door has been open for the timeout.
                        *([
                            "      - trigger: template\n",
                            "        value_template: >-\n",
                            f"          {{{{ is_state('{trigger_entity_id}', 'on') and states.{trigger_entity_id}.last_changed is defined\n",
                            f"             and (now() - states.{trigger_entity_id}.last_changed).total_seconds() >= {door_timeout * 60} }}}}\n",
                            "        id: door_timeout\n",
                        ] if door_timeout else []),
                        *(
                            [
                                "    conditions:\n",
                                "      - condition: or\n",
                                "        conditions:\n",
                                "          - condition: trigger\n",
                                "            id: turn_off\n",
                                *self._door_condition_lines(automation, automations),
                            ]
                            if automation.get("house_mode")
                            else []
                        ),
                        "    actions:\n",
                        "      - choose:\n",
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: turn_on\n",
                        "            sequence:\n",
                        *([] if automation.get("trigger_kind") == "door" else [
                            "              - condition: template\n",
                            "                value_template: \"{{ not is_state("
                            f"'{target_entity_id}', 'on') }}}}\"\n",
                        ]),
                        f"              - action: {target_domain}.turn_on\n",
                        "                target:\n",
                        f"                  entity_id: {target_entity_id}\n",
                        *(
                            self._door_light_data_lines(
                                tone_aware_light_setting(
                                    automation.get("action_setting", {}),
                                    target_entity_id,
                                    entities_by_id,
                                ),
                                "                ",
                            )
                            if target_domain == "light"
                            else []
                        ),
                        *([
                            "              - delay:\n",
                            f"                  minutes: {door_timeout}\n",
                            f"              - action: {target_domain}.turn_off\n",
                            "                target:\n",
                            f"                  entity_id: {target_entity_id}\n",
                            "          - conditions:\n",
                            "              - condition: trigger\n",
                            "                id: door_timeout\n",
                            "            sequence:\n",
                            "              - condition: template\n",
                            "                value_template: \"{{ not is_state("
                            f"'{target_entity_id}', 'off') }}}}\"\n",
                            f"              - action: {target_domain}.turn_off\n",
                            "                target:\n",
                            f"                  entity_id: {target_entity_id}\n",
                        ] if door_timeout else []),
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: turn_off\n",
                        "            sequence:\n",
                        "              - condition: template\n",
                        "                value_template: \"{{ not is_state("
                        f"'{target_entity_id}', 'off') }}}}\"\n",
                        f"              - action: {target_domain}.turn_off\n",
                        "                target:\n",
                        f"                  entity_id: {target_entity_id}\n",
                        ]
                    )
                else:
                    lines.extend(
                        [
                            "    triggers:\n",
                            "      - trigger: state\n",
                            f"        entity_id: {automation['trigger_entity_id']}\n",
                            "    conditions:\n",
                            "      - condition: template\n",
                            "        value_template: >-\n",
                            "          {{ trigger.to_state is not none and\n",
                            "             trigger.to_state.attributes.event_type == "
                            f"'{automation['event_type']}' }}}}\n",
                            "    actions:\n",
                        ]
                    )
                    lines.extend(
                        self._target_action_lines(
                            automation["action"],
                            automation.get("target_entity_id")
                            or automation["light_group_entity_id"],
                            automation.get("target_domain") or "light",
                        )
                    )

        for override in override_automations:
            lines.append("  - " + json.dumps(override) + "\n")
        if override_helpers:
            lines.append("input_boolean: " + json.dumps(override_helpers) + "\n")
        if exhaust_run_timers:
            lines.append("timer: " + json.dumps(exhaust_run_timers) + "\n")
        content = "".join(lines)
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                try:
                    had_timers = "\ntimer: " in self._path.read_text(encoding="utf-8")
                except OSError:
                    had_timers = False
                changed = atomic_write_text(self._path, content)
                if changed and reload_automations and self._publisher:
                    if override_helpers or exhaust_run_timers or had_timers:
                        self._publisher.reload_domains((
                            *(("input_boolean",) if override_helpers else ()),
                            *(("timer",) if exhaust_run_timers or had_timers else ()),
                            "automation",
                        ))
                    else:
                        self._publisher.reload_automations()
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write Control automations: {err}"
            ) from err
        return automations


class DoorAutomationManager:
    """Generate native automations for assigned door sensors."""

    def __init__(
        self,
        path: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
    ) -> None:
        self._path = path
        self._publisher = publisher

    @staticmethod
    def describe(
        assignments: dict[str, str],
        entities: list[dict[str, Any]],
        automation_prefix: str = DOOR_AUTOMATION_UNIQUE_ID_PREFIX,
        source_key: str = "door",
        timings: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        names = {
            str(entity.get("entity_id") or ""): str(
                entity.get("friendly_name") or entity.get("entity_id") or ""
            )
            for entity in entities
        }
        return [
            {
                "id": automation_prefix
                + hashlib.sha1(door_id.encode("utf-8")).hexdigest()[:16],
                "alias": (
                    f"FHT - {names.get(door_id) or door_id} → "
                    f"{names.get(group_id) or group_id}"
                ),
                f"{source_key}_entity_id": door_id,
                "light_group_entity_id": group_id,
                "activation_delay": int((timings or {}).get(door_id, {}).get("activation_delay", 0)),
                "clear_delay": int((timings or {}).get(door_id, {}).get("clear_delay", 0)),
            }
            for door_id, group_id in sorted(assignments.items())
        ]

    def sync(
        self,
        assignments: dict[str, str],
        entities: list[dict[str, Any]],
        automation_prefix: str = DOOR_AUTOMATION_UNIQUE_ID_PREFIX,
        source_key: str = "door",
        timings: dict[str, dict[str, int]] | None = None,
        reload_automations: bool = True,
    ) -> list[dict[str, str]]:
        automations = self.describe(
            assignments,
            entities,
            automation_prefix,
            source_key,
            timings,
        )
        lines = ["# Managed by Future Homes Tech App. Changes may be overwritten.\n"]
        if not automations:
            lines.append("automation: []\n")
        else:
            lines.append("automation:\n")
            for automation in automations:
                lines.extend(
                    [
                        f"  - id: {json.dumps(automation['id'])}\n",
                        f"    alias: {json.dumps(automation['alias'])}\n",
                        "    mode: restart\n",
                        "    triggers:\n",
                        "      - trigger: state\n",
                        f"        entity_id: {automation[f'{source_key}_entity_id']}\n",
                        '        to: "on"\n',
                        "        id: opened\n",
                        "      - trigger: state\n",
                        f"        entity_id: {automation[f'{source_key}_entity_id']}\n",
                        '        to: "off"\n',
                        "        id: closed\n",
                        "    actions:\n",
                        "      - choose:\n",
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: opened\n",
                        "            sequence:\n",
                        *(
                            [f"              - delay: {automation['activation_delay']}\n"]
                            if automation["activation_delay"]
                            else []
                        ),
                        "              - action: light.turn_on\n",
                        "                target:\n",
                        f"                  entity_id: {automation['light_group_entity_id']}\n",
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: closed\n",
                        "            sequence:\n",
                        *(
                            [f"              - delay: {automation['clear_delay']}\n"]
                            if automation["clear_delay"]
                            else []
                        ),
                        "              - action: light.turn_off\n",
                        "                target:\n",
                        f"                  entity_id: {automation['light_group_entity_id']}\n",
                    ]
                )
        content = "".join(lines)
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, content)
                if changed and reload_automations and self._publisher:
                    self._publisher.reload_automations()
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write door automations: {err}"
            ) from err
        return automations


class PresenceAutomationManager(DoorAutomationManager):
    """Generate native automations for assigned presence sensors."""

    SETTINGS_SAVED_EVENT = "fht_presence_settings_saved"

    def apply_saved_settings(
        self, presence_entity_id: str, previous: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Re-apply brightness where the lights still show the previous setting.

        ``previous`` is the sensor's mode settings before the save.
        """
        if self._publisher is None:
            return
        self._publisher.fire_event(
            self.SETTINGS_SAVED_EVENT,
            {
                "presence_entity_id": presence_entity_id,
                "previous": {
                    mode: int(setting["brightness"])
                    for mode, setting in PresenceModeSettings.normalize(previous).items()
                    if setting.get("enabled")
                },
            },
        )

    @staticmethod
    def still_at_previous_template(target_id: str) -> str:
        """Return whether a light is within 3% of the App's previous brightness."""
        return (
            "{% set previous = (trigger.event.data.get('previous') or {}).get(fht_mode) %}"
            "{{ previous is number and ((state_attr(" + repr(target_id) + ", 'brightness') or 0)"
            " / 255 * 100 - previous) | abs <= 3 }}"
        )

    @staticmethod
    def mode_tones(setting: dict[str, dict[str, Any]]) -> dict[str, int | str]:
        """Return the colour tone each mode applies: Kelvin, "adaptive", or nothing."""
        tones: dict[str, int | str] = {}
        for mode, values in setting.items():
            if values.get("color_mode") == "adaptive":
                tones[mode] = "adaptive"
            elif values.get("color_mode") == "kelvin":
                tones[mode] = int(values.get("color_kelvin") or PresenceModeSettings.DEFAULT_COLOR_KELVIN)
        return tones

    @staticmethod
    def tone_template(tones: dict[str, int | str]) -> str:
        """Render the Kelvin for the active mode, or nothing for "current"."""
        return (
            "{% set tone = " + json.dumps(tones) + ".get(fht_mode) %}"
            + LightScheduleAutomationManager.ADAPTIVE_ELEVATION_PREFIX.strip()
            + "{{ (" + LightScheduleAutomationManager.ADAPTIVE_KELVIN_EXPRESSION
            + ") if tone == 'adaptive' else (tone if tone else '') }}"
        )

    @staticmethod
    def _light_data_lines(automation: dict[str, Any]) -> list[str]:
        """Render the turn_on data: brightness, plus the tone when one applies."""
        if not automation.get("tones"):
            return [
                "                data:\n",
                '                  brightness_pct: "{{ fht_brightness | int }}"\n',
            ]
        template = (
            "{% set data = {'brightness_pct': fht_brightness | int} %}"
            "{{ data if not fht_tone else dict(data, color_temp_kelvin=fht_tone | int) }}"
        )
        return [f"                data: {json.dumps(template)}\n"]

    def sync(
        self,
        assignments: dict[str, str | list[str]],
        entities: list[dict[str, Any]],
        timings: dict[str, dict[str, int]] | None = None,
        mode_settings: dict[str, dict[str, dict[str, Any]]] | None = None,
        reload_automations: bool = True,
        room_modes: dict[str, list[str]] | None = None,
    ) -> list[dict[str, str]]:
        names = {
            str(entity.get("entity_id") or ""): str(
                entity.get("friendly_name") or entity.get("entity_id") or ""
            )
            for entity in entities
        }
        camera_devices = camera_device_ids(entities)
        cameras = {
            str(entity.get("entity_id") or "")
            for entity in entities
            if str(entity.get("entity_id") or "").startswith("binary_sensor.")
            and is_camera_entity(entity, camera_devices)
        }
        children_by_parent: dict[str, list[str]] = {}
        for child_id, child_timing in sorted((timings or {}).items()):
            for parent_id in (child_timing or {}).get("parent_groups", []) or []:
                if parent_id != child_id:
                    children_by_parent.setdefault(str(parent_id), []).append(str(child_id))
        automations: list[dict[str, Any]] = []
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity
            for entity in entities
            if isinstance(entity, dict)
        }
        for presence_id, target_ids in sorted(assignments.items()):
            if isinstance(target_ids, str):
                target_ids = [target_ids]
            setting = PresenceModeSettings.normalize(
                (mode_settings or {}).get(presence_id)
            )
            tones = self.mode_tones(setting)
            timing = (timings or {}).get(presence_id, {})
            sensor = next((entity for entity in entities if entity.get("entity_id") == presence_id), {})
            room = str(sensor.get("original_area") or sensor.get("area") or "")
            helper = f"input_select.fht_{BedroomModeAutomationManager._slug(room)}_mode" if room else ""
            enabled_room_modes = (room_modes or {}).get(room, [])
            overrides = [mode for mode in setting if mode in enabled_room_modes]
            mode_template = "{{ states(" + repr(HOUSE_MODE_HELPER) + ") | lower }}"
            if helper and overrides:
                mode_template = ("{% set room_mode = states(" + repr(helper)
                    + ") | lower | replace(' ', '_') %}{{ room_mode if room_mode in "
                    + repr(overrides) + " else states(" + repr(HOUSE_MODE_HELPER) + ") | lower }}")
            if is_sleep_number_entity(presence_id, names.get(presence_id)) or presence_id in cameras:
                # Sleep Number beds and camera motion are not room presence;
                # saved choices are kept but no longer generate automations.
                continue
            for target_id in target_ids:
                service_domain = target_id.partition(".")[0]
                if service_domain not in CONTROL_ENTITY_DOMAINS:
                    continue
                automation_key = f"{presence_id}|{target_id}"
                automations.append(
                    {
                        "id": PRESENCE_AUTOMATION_UNIQUE_ID_PREFIX
                        + hashlib.sha1(
                            automation_key.encode("utf-8")
                        ).hexdigest()[:16],
                        "alias": (
                            f"FHT - {names.get(presence_id) or presence_id} → "
                            f"{names.get(target_id) or target_id}"
                        ),
                        "presence_entity_id": presence_id,
                        "target_entity_id": target_id,
                        "light_group_entity_id": target_id,
                        "service_domain": service_domain,
                        "activation_delay": int(
                            timing.get("activation_delay", 0)
                        ),
                        "clear_delay": int(timing.get("clear_delay", 0)),
                        # Sensors that chose this group as their Parent Presence
                        # Group keep its lights on; they never turn them on.
                        "child_presence_ids": children_by_parent.get(presence_id, []),
                        "mode_settings": setting,
                        "mode_template": mode_template,
                        "room_mode_helper": helper if overrides else "",
                        # Tones only reach lights that can show them.
                        "tones": tones if service_domain == "light"
                        and light_supports_tone(target_id, entities_by_id) else {},
                    }
                )

        lines = [
            "# Managed by Future Homes Tech App. Changes may be overwritten.\n"
        ]
        if not automations:
            lines.append("automation: []\n")
        else:
            lines.append("automation:\n")
            for automation in automations:
                settings = automation["mode_settings"]
                enabled_map = {
                    mode: bool(settings[mode]["enabled"])
                    for mode in settings
                }
                brightness_map = {
                    mode: int(settings[mode]["brightness"])
                    for mode in settings
                }
                enabled_template = (
                    "{{ " + json.dumps(enabled_map)
                    + ".get(fht_mode, false) }}"
                )
                brightness_template = (
                    "{{ " + json.dumps(brightness_map)
                    + ".get(fht_mode, 100) }}"
                )
                lines.extend(
                    [
                        f"  - id: {json.dumps(automation['id'])}\n",
                        f"    alias: {json.dumps(automation['alias'])}\n",
                        "    mode: restart\n",
                        "    triggers:\n",
                        "      - trigger: state\n",
                        f"        entity_id: {automation['presence_entity_id']}\n",
                        '        to: "on"\n',
                        "        id: detected\n",
                        "      - trigger: state\n",
                        f"        entity_id: {automation['presence_entity_id']}\n",
                        '        to: "off"\n',
                        "        id: clear\n",
                        "      - trigger: state\n",
                        f"        entity_id: {HOUSE_MODE_HELPER}\n",
                        "        id: mode_changed\n",
                        *(["      - trigger: state\n", f"        entity_id: {automation['room_mode_helper']}\n", "        id: mode_changed\n"] if automation["room_mode_helper"] else []),
                        "      - trigger: event\n",
                        f"        event_type: {PresenceAutomationManager.SETTINGS_SAVED_EVENT}\n",
                        "        event_data:\n",
                        f"          presence_entity_id: {automation['presence_entity_id']}\n",
                        "        id: settings_saved\n",
                        "    actions:\n",
                        "      - variables:\n",
                        f"          fht_mode: {json.dumps(automation['mode_template'])}\n",
                        f"          fht_enabled: {json.dumps(enabled_template)}\n",
                        f"          fht_brightness: {json.dumps(brightness_template)}\n",
                        *(
                            [f"          fht_tone: {json.dumps(PresenceAutomationManager.tone_template(automation['tones']))}\n"]
                            if automation["tones"]
                            else []
                        ),
                        "      - choose:\n",
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: clear\n",
                        "            sequence:\n",
                        *(
                            [f"              - delay: {automation['clear_delay']}\n"]
                            if automation["clear_delay"]
                            else []
                        ),
                        "              - condition: state\n",
                        f"                entity_id: {automation['presence_entity_id']}\n",
                        '                state: "off"\n',
                        *sum(([
                            "              - condition: state\n",
                            f"                entity_id: {child_id}\n",
                            '                state: "off"\n',
                        ] for child_id in automation["child_presence_ids"]), []),
                        f"              - action: {automation['service_domain']}.turn_off\n",
                        "                target:\n",
                        f"                  entity_id: {automation['target_entity_id']}\n",
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: detected\n",
                        "            sequence:\n",
                        *(
                            [f"              - delay: {automation['activation_delay']}\n"]
                            if automation["activation_delay"]
                            else []
                        ),
                        "              - condition: state\n",
                        f"                entity_id: {automation['presence_entity_id']}\n",
                        '                state: "on"\n',
                        "              - condition: template\n",
                        '                value_template: "{{ fht_enabled | bool }}"\n',
                        "              - condition: template\n",
                        f"                value_template: {json.dumps(SwitchBrightnessOverride.presence_guard(automation['target_entity_id'], entities))}\n",
                        f"              - action: {automation['service_domain']}.turn_on\n",
                        "                target:\n",
                        f"                  entity_id: {automation['target_entity_id']}\n",
                        *(
                            self._light_data_lines(automation)
                            if automation["service_domain"] == "light"
                            else []
                        ),
                        "          - conditions:\n",
                        "              - condition: trigger\n",
                        "                id: mode_changed\n",
                        "              - condition: state\n",
                        f"                entity_id: {automation['presence_entity_id']}\n",
                        '                state: "on"\n',
                        "              - condition: template\n",
                        '                value_template: "{{ fht_enabled | bool }}"\n',
                        "            sequence:\n",
                        "              - condition: template\n",
                        f"                value_template: {json.dumps(SwitchBrightnessOverride.presence_guard(automation['target_entity_id'], entities))}\n",
                        f"              - action: {automation['service_domain']}.turn_on\n",
                        "                target:\n",
                        f"                  entity_id: {automation['target_entity_id']}\n",
                        *(
                            self._light_data_lines(automation)
                            if automation["service_domain"] == "light"
                            else []
                        ),
                        # A saved change applies only while the lights are
                        # still at the brightness the App set before; lights
                        # someone dimmed or turned off are left alone.
                        *([
                            "          - conditions:\n",
                            "              - condition: trigger\n",
                            "                id: settings_saved\n",
                            "              - condition: state\n",
                            f"                entity_id: {automation['presence_entity_id']}\n",
                            '                state: "on"\n',
                            "              - condition: state\n",
                            f"                entity_id: {automation['target_entity_id']}\n",
                            '                state: "on"\n',
                            "              - condition: template\n",
                            '                value_template: "{{ fht_enabled | bool }}"\n',
                            "              - condition: template\n",
                            f"                value_template: {json.dumps(PresenceAutomationManager.still_at_previous_template(automation['target_entity_id']))}\n",
                            "            sequence:\n",
                            "              - action: light.turn_on\n",
                            "                target:\n",
                            f"                  entity_id: {automation['target_entity_id']}\n",
                            *self._light_data_lines(automation),
                        ] if automation["service_domain"] == "light" else []),
                    ]
                )
                if automation["child_presence_ids"]:
                    # A child clearing after the group already cleared still
                    # lets the group's lights turn off.
                    children = automation["child_presence_ids"]
                    lines.extend(
                        [
                            f"  - id: {json.dumps(automation['id'].replace(PRESENCE_AUTOMATION_UNIQUE_ID_PREFIX, PRESENCE_AUTOMATION_UNIQUE_ID_PREFIX + 'hold_', 1))}\n",
                            f"    alias: {json.dumps(automation['alias'] + ' (child presence hold)')}\n",
                            "    mode: restart\n",
                            "    triggers:\n",
                            "      - trigger: state\n",
                            f"        entity_id: {json.dumps(children)}\n",
                            '        to: "off"\n',
                            "    conditions:\n",
                            "      - condition: state\n",
                            f"        entity_id: {automation['presence_entity_id']}\n",
                            '        state: "off"\n',
                            "    actions:\n",
                            *(
                                [f"      - delay: {automation['clear_delay']}\n"]
                                if automation["clear_delay"]
                                else []
                            ),
                            "      - condition: state\n",
                            f"        entity_id: {json.dumps([automation['presence_entity_id'], *children])}\n",
                            '        state: "off"\n',
                            f"      - action: {automation['service_domain']}.turn_off\n",
                            "        target:\n",
                            f"          entity_id: {automation['target_entity_id']}\n",
                        ]
                    )
        content = "".join(lines)
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, content)
                if changed and reload_automations and self._publisher:
                    self._publisher.reload_automations()
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write presence automations: {err}"
            ) from err
        return automations


class PresenceGroupManager:
    """Generate grouped occupancy sensors for numbered presence channels."""

    def __init__(self, path: Path, config_directory: Path) -> None:
        self._path = path
        self._config_directory = config_directory

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"_+", "_", re.sub(
            r"[^a-z0-9]+", "_", value.casefold()
        )).strip("_")

    @staticmethod
    def _numbered_base(value: str) -> tuple[str, bool]:
        normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
        match = re.search(r"_(\d+)$", normalized)
        if not match:
            return normalized, False
        return normalized[:match.start()], True

    def discover(self) -> list[dict[str, Any]]:
        """Return grouped sensors discovered from Home Assistant registries."""
        storage_directory = self._config_directory / ".storage"

        def load(filename: str, key: str) -> list[dict[str, Any]]:
            try:
                payload = json.loads(
                    storage_directory.joinpath(filename).read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, json.JSONDecodeError):
                return []
            values = payload.get("data", {}).get(key, [])
            return values if isinstance(values, list) else []

        areas = load("core.area_registry", "areas")
        devices = load("core.device_registry", "devices")
        entities = load("core.entity_registry", "entities")
        area_names = {
            str(area.get("area_id") or area.get("id")): str(area.get("name"))
            for area in areas
            if (area.get("area_id") or area.get("id")) and area.get("name")
        }
        device_values = {
            str(device.get("id")): device
            for device in devices
            if isinstance(device, dict) and device.get("id")
        }
        camera_devices = camera_device_ids(entities)
        candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}
        presence_entities: list[dict[str, Any]] = []
        for entity in entities:
            if not isinstance(entity, dict) or entity.get("disabled_by"):
                continue
            entity_id = str(entity.get("entity_id") or "")
            if not entity_id.startswith("binary_sensor."):
                continue
            if entity_id.startswith("binary_sensor.fht_"):
                continue
            device_class = str(
                entity.get("device_class")
                or entity.get("original_device_class")
                or ""
            ).casefold()
            name = str(
                entity.get("name")
                or entity.get("original_name")
                or entity_id.split(".", 1)[-1].replace("_", " ")
            )
            searchable = f"{name} {entity_id}".casefold().replace("_", " ")
            if "door sensor" in searchable:
                continue
            bed_device = device_values.get(str(entity.get("device_id") or ""), {})
            if entity.get("platform") == "sleepiq" or is_sleep_number_entity(
                searchable, bed_device.get("manufacturer"), bed_device.get("name")
            ):
                continue
            if is_camera_entity(
                {**entity, "device_name": bed_device.get("name_by_user") or bed_device.get("name")},
                camera_devices,
            ):
                continue
            if (
                device_class not in {"motion", "occupancy", "presence"}
                and "occupancy" not in searchable
                and "presence" not in searchable
            ):
                continue
            object_base, entity_is_numbered = self._numbered_base(
                entity_id.split(".", 1)[-1]
            )
            name_base, name_is_numbered = self._numbered_base(name)
            base = object_base or name_base
            device_id = str(entity.get("device_id") or "")
            device = device_values.get(device_id, {})
            device_label = str(
                device.get("name_by_user")
                or device.get("name")
                or ""
            ).strip()
            # Match entity_areas_from_storage: a valid entity area wins.
            area_id = str(
                (entity.get("area_id") if str(entity.get("area_id") or "") in area_names else "")
                or device.get("area_id")
                or ""
            )
            key = (device_id or base, base)
            candidate = {
                "entity_id": entity_id,
                "device_id": device_id,
                "device_label": device_label,
                "entity_is_numbered": entity_is_numbered,
                "name_is_numbered": name_is_numbered,
                "name_base": name_base,
                "area_id": area_id,
            }
            candidates.setdefault(key, []).append(candidate)
            presence_entities.append(candidate)

        groups: list[dict[str, Any]] = []
        for members in candidates.values():
            if len(members) < 2 or not any(
                member["entity_is_numbered"] or member["name_is_numbered"]
                for member in members
            ):
                continue
            device = device_values.get(members[0]["device_id"], {})
            label = str(
                device.get("name_by_user")
                or device.get("name")
                or members[0]["name_base"].replace("_", " ").title()
            ).strip()
            if not label:
                continue
            area_id = str(members[0]["area_id"] or device.get("area_id") or "")
            area = area_names.get(area_id, "")
            friendly_name = f"FHT - {label} Group Presence"
            entity_id = f"binary_sensor.{self._slug(friendly_name)}"
            member_ids = sorted({member["entity_id"] for member in members})
            groups.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "area": area,
                    "members": member_ids,
                    "unique_id": "fht_presence_group_"
                    + hashlib.sha1(
                        "|".join(member_ids).encode("utf-8")
                    ).hexdigest()[:16],
                }
            )

        device_families: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for entity in presence_entities:
            device_label = str(entity.get("device_label") or "")
            device_base, device_is_numbered = self._numbered_base(device_label)
            if not device_is_numbered:
                continue
            key = (str(entity.get("area_id") or ""), device_base)
            device_families.setdefault(key, []).append(entity)
        for (area_id, device_base), members in device_families.items():
            device_ids = {
                str(member.get("device_id") or "")
                for member in members
                if member.get("device_id")
            }
            if len(device_ids) < 2:
                continue
            example_label = str(members[0].get("device_label") or "")
            label = re.sub(
                r"\s*(?:\(\d+\)|\d+)\s*$",
                "",
                example_label,
            ).strip() or device_base.replace("_", " ").title()
            member_ids = sorted(
                {str(member["entity_id"]) for member in members}
            )
            friendly_name = f"FHT - {label} Group"
            entity_id = f"binary_sensor.{self._slug(friendly_name)}"
            if any(group["entity_id"] == entity_id for group in groups):
                continue
            groups.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "area": area_names.get(area_id, ""),
                    "members": member_ids,
                    "unique_id": "fht_presence_group_"
                    + hashlib.sha1(
                        "|".join(member_ids).encode("utf-8")
                    ).hexdigest()[:16],
                }
            )
        return sorted(
            groups,
            key=lambda group: str(group["friendly_name"]).casefold(),
        )

    def sync(self) -> tuple[bool, list[dict[str, Any]]]:
        """Write current grouped presence sensors to a managed package."""
        groups = self.discover()
        lines = ["# Managed by Future Homes Tech App.\n"]
        if not groups:
            lines.append("template: []\n")
        else:
            lines.extend(["template:\n", "  - binary_sensor:\n"])
            for group in groups:
                members = json.dumps(group["members"])
                lines.extend(
                    [
                        f"      - name: {json.dumps(group['friendly_name'])}\n",
                        f"        unique_id: {json.dumps(group['unique_id'])}\n",
                        "        device_class: occupancy\n",
                        "        state: >-\n",
                        f"          {{{{ expand({members}) | selectattr('state', 'eq', 'on') | list | count > 0 }}}}\n",
                        "        availability: >-\n",
                        f"          {{{{ expand({members}) | rejectattr('state', 'in', ['unknown', 'unavailable']) | list | count > 0 }}}}\n",
                        "        attributes:\n",
                        f"          fht_area: {json.dumps(group['area'])}\n",
                        "          fht_presence_members: >-\n",
                        f"            {{{{ {members} }}}}\n",
                    ]
                )
        content = "".join(lines)
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, content)
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write grouped presence sensors: {err}"
            ) from err
        return changed, groups


class FridgeAlarmSettings(JsonSettingsStore):
    """Persist refrigerator temperature and door-open alert settings."""

    DEFAULTS = {
        "temperature": {
            "enabled": False,
            "threshold": 40,
            "delay_minutes": 5,
            "alert_targets": [],
            "alert_behavior": "until_clear",
            "notify_targets": [],
        },
        "door": {
            "enabled": False,
            "delay_minutes": 5,
            "alert_targets": [],
            "alert_behavior": "until_clear",
            "notify_targets": [],
        },
    }
    READ_ERROR = "Unable to read refrigerator alarms"
    SAVE_ERROR = "Unable to save refrigerator alarm"

    @classmethod
    def normalize(cls, kind: str, value: Any) -> dict[str, Any]:
        """Return one validated refrigerator sensor alert."""
        if kind not in cls.DEFAULTS:
            raise ValueError("Refrigerator alerts must use a temperature or door sensor.")
        payload = value if isinstance(value, dict) else {}
        try:
            delay_minutes = int(
                payload.get("delay_minutes", cls.DEFAULTS[kind]["delay_minutes"])
            )
        except (TypeError, ValueError) as err:
            raise ValueError("Alert delay must be a whole number of minutes.") from err
        if not 0 <= delay_minutes <= 180:
            raise ValueError("Alert delay must be between 0 and 180 minutes.")
        setting: dict[str, Any] = {
            "kind": kind,
            "enabled": bool(payload.get("enabled", False)),
            "delay_minutes": delay_minutes,
        }
        raw_targets = payload.get("alert_targets")
        if not isinstance(raw_targets, list):
            legacy_target = str(payload.get("alert_target") or "").strip()
            raw_targets = [legacy_target] if legacy_target else []
        alert_targets: list[str] = []
        for target in raw_targets:
            entity_id = str(target or "").strip()
            if not entity_id or entity_id in alert_targets:
                continue
            if not entity_id.startswith(("button.", "siren.")):
                raise ValueError("Alarm outputs must be sirens or chime buttons.")
            alert_targets.append(entity_id)
        alert_behavior = str(
            payload.get("alert_behavior") or "once"
        ).strip().casefold()
        if alert_behavior not in {"once", "until_clear"}:
            raise ValueError("Alarm behavior must be one time or until clear.")
        setting["alert_targets"] = alert_targets
        setting["alert_behavior"] = "until_clear"
        setting["unifi_webhook"] = payload.get("unifi_webhook") is True
        setting["notify_targets"] = phone_notify_targets(payload.get("notify_targets"))
        if kind == "temperature":
            try:
                threshold = float(
                    payload.get("threshold", cls.DEFAULTS[kind]["threshold"])
                )
            except (TypeError, ValueError) as err:
                raise ValueError("Temperature threshold must be a number.") from err
            if not -100 <= threshold <= 200:
                raise ValueError("Temperature threshold must be between -100 and 200.")
            setting["threshold"] = int(threshold) if threshold.is_integer() else threshold
        return setting

    def _clean(self, payload: Any) -> dict[str, dict[str, Any]]:
        """Return every valid saved refrigerator alert."""
        if not isinstance(payload, dict):
            return {}
        settings: dict[str, dict[str, Any]] = {}
        for entity_id, value in payload.items():
            if not isinstance(entity_id, str) or "." not in entity_id:
                continue
            kind = str(value.get("kind") or "") if isinstance(value, dict) else ""
            try:
                settings[entity_id] = self.normalize(kind, value)
            except ValueError:
                continue
        return settings

    def save(
        self,
        entity_id: str,
        kind: str,
        value: Any,
    ) -> dict[str, dict[str, Any]]:
        """Save one refrigerator sensor alert."""
        entity_id = entity_id.strip()
        expected_domain = "sensor" if kind == "temperature" else "binary_sensor"
        if not entity_id.startswith(f"{expected_domain}."):
            raise ValueError("A valid refrigerator sensor is required.")
        setting = self.normalize(kind, value)
        with self._lock:
            payload = self._read_dict()
            payload[entity_id] = setting
            self._write_unlocked(payload)
        return self.read()


class FridgeAlarmAutomationManager:
    """Generate native Home Assistant refrigerator alert automations."""

    def __init__(
        self,
        path: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
    ) -> None:
        self._path = path
        self._publisher = publisher

    @staticmethod
    def _delay_lines(minutes: int) -> list[str]:
        return device_alarm_delay_lines(minutes)

    def sync(
        self,
        settings: dict[str, dict[str, Any]],
        entities: list[dict[str, Any]],
        reload_automations: bool = True,
        notify_services: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Write one managed automation per enabled refrigerator sensor.

        ``notify_services`` lists the phones Home Assistant can notify right
        now; a saved phone that is no longer signed in is left out so a
        missing notify service cannot stop the sirens and chimes. ``None``
        keeps every saved phone.
        """
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity
            for entity in entities
        }
        automations: list[dict[str, Any]] = []
        lines = ["# Managed by Future Homes Tech App.\n", "automation:\n"]
        for entity_id, raw_setting in sorted(device_alarm_buzzer_settings(settings, entities).items()):
            entity = entities_by_id.get(entity_id)
            if not entity:
                continue
            kind = fridge_alarm_sensor_kind(entity)
            if not kind:
                continue
            setting = FridgeAlarmSettings.normalize(kind, raw_setting)
            if not setting["enabled"]:
                continue
            name = str(entity.get("friendly_name") or entity_id)
            unit = str(entity.get("unit_of_measurement") or "")
            digest = hashlib.sha1(f"{kind}:{entity_id}".encode("utf-8")).hexdigest()[:16]
            unique_id = FRIDGE_ALARM_AUTOMATION_UNIQUE_ID_PREFIX + digest
            notification_id = f"fht_fridge_{digest}"
            siren_targets, button_targets = device_alarm_output_targets(
                setting["alert_targets"], entities_by_id
            )
            phone_targets = [
                service
                for service in setting["notify_targets"]
                if notify_services is None or service in notify_services
            ]
            automations.append(
                {
                    "entity_id": entity_id,
                    "name": name,
                    **setting,
                }
            )
            lines.extend(
                [
                    f"  - id: {unique_id}\n",
                    f"    alias: {json.dumps(f'FHT - {name} Alert')}\n",
                    "    mode: restart\n",
                    "    triggers:\n",
                ]
            )
            if kind == "temperature":
                threshold = setting["threshold"]
                message = (
                    f"{name} is {{{{ states({entity_id!r}) }}}}{unit}. "
                    f"The configured limit is {threshold}{unit}."
                )
                lines.extend(
                    [
                        "      - trigger: numeric_state\n",
                        f"        entity_id: {entity_id}\n",
                        f"        above: {threshold}\n",
                        *self._delay_lines(setting["delay_minutes"]),
                        "        id: alert\n",
                        "      - trigger: numeric_state\n",
                        f"        entity_id: {entity_id}\n",
                        f"        below: {threshold}\n",
                        "        id: clear\n",
                    ]
                )
                title = "Refrigerator Temperature Alert"
            else:
                duration = setting["delay_minutes"]
                message = (
                    f"{name} is open."
                    if not duration
                    else f"{name} has been open for {duration} minutes."
                )
                lines.extend(
                    [
                        "      - trigger: state\n",
                        f"        entity_id: {entity_id}\n",
                        '        to: "on"\n',
                        *self._delay_lines(duration),
                        "        id: alert\n",
                        "      - trigger: state\n",
                        f"        entity_id: {entity_id}\n",
                        '        to: "off"\n',
                        "        id: clear\n",
                    ]
                )
                title = "Refrigerator Door Alert"
            lines.extend(
                [
                    "    actions:\n",
                    "      - choose:\n",
                    "          - conditions:\n",
                    "              - condition: trigger\n",
                    "                id: alert\n",
                    "            sequence:\n",
                    "              - action: persistent_notification.create\n",
                    "                data:\n",
                    f"                  notification_id: {notification_id}\n",
                    f"                  title: {json.dumps(title)}\n",
                    f"                  message: {json.dumps(message)}\n",
                ]
            )
            if kind == "door":
                still_active_lines = door_open_condition_lines(entity_id)
            else:
                still_active_lines = [
                    "                    - condition: numeric_state\n",
                    f"                      entity_id: {entity_id}\n",
                    f"                      above: {setting['threshold']}\n",
                ]
            lines.extend(
                phone_notify_action_lines(
                    phone_targets,
                    "              ",
                    title,
                    message,
                    tag=notification_id,
                )
            )
            lines.extend(
                device_alarm_alert_output_lines(
                    siren_targets,
                    button_targets,
                    unifi_webhook=setting["unifi_webhook"],
                    alert_behavior=setting["alert_behavior"],
                    still_active_lines=still_active_lines,
                )
            )
            lines.extend(
                device_alarm_clear_lines(
                    notification_id,
                    siren_targets,
                    after_dismiss=phone_notify_action_lines(
                        phone_targets,
                        "              ",
                        tag=notification_id,
                        clear=True,
                    ),
                )
            )
        if not automations:
            lines = ["# Managed by Future Homes Tech App.\n", "automation: []\n"]
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, "".join(lines))
                if changed and reload_automations and self._publisher:
                    self._publisher.reload_automations()
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write refrigerator alarm automations: {err}"
            ) from err
        return automations


def device_alarm_delay_lines(minutes: int, indent: str = "        ") -> list[str]:
    """Return the `for:` lines that hold a device alarm back for some minutes."""
    if not minutes:
        return []
    return [f"{indent}for:\n", f"{indent}  minutes: {minutes}\n"]


def device_alarm_webhook_configured() -> bool:
    """Return whether the App has a UniFi device alarm webhook to call."""
    return bool(os.environ.get("DEVICE_ALARM_WEBHOOK", "").strip())


def device_alarm_output_targets(
    alert_targets: list[str],
    entities_by_id: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Split saved alert outputs into current siren and chime button IDs."""
    siren_targets: list[str] = []
    button_targets: list[str] = []
    for target in alert_targets:
        output_kind = fridge_alarm_output_kind(entities_by_id.get(target) or {})
        if output_kind == "siren":
            siren_targets.append(target)
        elif output_kind == "button":
            button_targets.append(target)
    return siren_targets, button_targets


def door_open_condition_lines(
    entity_id: str, indent: str = "                    "
) -> list[str]:
    """Return a `while:` condition that holds while a door sensor is open."""
    return [
        f"{indent}- condition: state\n",
        f"{indent}  entity_id: {entity_id}\n",
        f'{indent}  state: "on"\n',
    ]


def device_alarm_alert_output_lines(
    siren_targets: list[str],
    button_targets: list[str],
    *,
    unifi_webhook: bool,
    alert_behavior: str,
    still_active_lines: list[str],
) -> list[str]:
    """Return the alert actions every device alarm shares.

    Sirens turn on, the UniFi webhook is called when configured, and chime
    buttons are pressed once or repeated every 10 seconds while the
    `still_active_lines` condition holds.
    """
    lines: list[str] = []
    if siren_targets:
        lines.extend(
            [
                "              - action: siren.turn_on\n",
                f"                target: {{entity_id: {json.dumps(siren_targets)}}}\n",
            ]
        )
    if unifi_webhook and device_alarm_webhook_configured():
        lines.extend(
            [
                "              - action: rest_command.fht_device_alarm_webhook\n",
                "                continue_on_error: true\n",
            ]
        )
    if button_targets and alert_behavior == "once":
        lines.extend(
            [
                "              - action: button.press\n",
                f"                target: {{entity_id: {json.dumps(button_targets)}}}\n",
            ]
        )
    if button_targets and alert_behavior == "until_clear":
        lines.extend(
            [
                "              - repeat:\n",
                "                  while:\n",
                *still_active_lines,
                "                  sequence:\n",
                "                    - action: button.press\n",
                f"                      target: {{entity_id: {json.dumps(button_targets)}}}\n",
                "                    - delay: 10\n",
            ]
        )
    if siren_targets and alert_behavior == "once":
        lines.extend(
            [
                "              - delay: 5\n",
                "              - action: siren.turn_off\n",
                f"                target: {{entity_id: {json.dumps(siren_targets)}}}\n",
            ]
        )
    return lines


def device_alarm_clear_lines(
    notification_id: str | None,
    siren_targets: list[str],
    after_dismiss: list[str] | None = None,
) -> list[str]:
    """Return the `clear` branch that dismisses the notice and silences sirens.

    ``after_dismiss`` holds extra sequence lines (phone clear notices) that
    run between the dismiss and the sirens.
    """
    sequence: list[str] = []
    if notification_id:
        sequence.extend(
            [
                "              - action: persistent_notification.dismiss\n",
                "                data:\n",
                f"                  notification_id: {notification_id}\n",
            ]
        )
    sequence.extend(after_dismiss or [])
    if siren_targets:
        sequence.extend(
            [
                "              - action: siren.turn_off\n",
                f"                target: {{entity_id: {json.dumps(siren_targets)}}}\n",
            ]
        )
    if not sequence:
        return []
    return [
        "          - conditions:\n",
        "              - condition: trigger\n",
        "                id: clear\n",
        "            sequence:\n",
        *sequence,
    ]


class DoorOpenAlertSettings(JsonSettingsStore):
    """Persist door-left-open reminders for door and window sensors."""

    WHEN_HOUSE_MODES: dict[str, tuple[str, ...]] = {
        "any": (),
        "night": ("Night",),
        "night_sleep": ("Night", "Sleep"),
    }
    DEFAULT = {
        "enabled": False,
        "delay_minutes": 5,
        "when": "any",
        "alert_targets": [],
        "unifi_webhook": False,
        "notification": True,
    }
    READ_ERROR = "Unable to read door left open reminders"
    SAVE_ERROR = "Unable to save door left open reminder"

    @classmethod
    def normalize(cls, value: Any) -> dict[str, Any]:
        """Return one validated door-left-open reminder."""
        payload = value if isinstance(value, dict) else {}
        try:
            delay_minutes = int(
                payload.get("delay_minutes", cls.DEFAULT["delay_minutes"])
            )
        except (TypeError, ValueError) as err:
            raise ValueError("Open longer than must be a whole number of minutes.") from err
        if not 0 <= delay_minutes <= 180:
            raise ValueError("Open longer than must be between 0 and 180 minutes.")
        when = str(payload.get("when") or cls.DEFAULT["when"]).strip().casefold()
        if when not in cls.WHEN_HOUSE_MODES:
            raise ValueError("When must be any time, night, or night and sleep.")
        raw_targets = payload.get("alert_targets")
        if raw_targets is None:
            raw_targets = []
        if not isinstance(raw_targets, list):
            raise ValueError("Alarm outputs must be a list.")
        alert_targets: list[str] = []
        for target in raw_targets:
            entity_id = str(target or "").strip()
            if not entity_id or entity_id in alert_targets:
                continue
            if not entity_id.startswith(("button.", "siren.")):
                raise ValueError("Alarm outputs must be sirens or chime buttons.")
            alert_targets.append(entity_id)
        return {
            "enabled": bool(payload.get("enabled", False)),
            "delay_minutes": delay_minutes,
            "when": when,
            "alert_targets": alert_targets,
            "unifi_webhook": payload.get("unifi_webhook") is True,
            "notification": bool(payload.get("notification", cls.DEFAULT["notification"])),
        }

    def _clean(self, payload: Any) -> dict[str, dict[str, Any]]:
        """Return every valid saved door-left-open reminder."""
        if not isinstance(payload, dict):
            return {}
        settings: dict[str, dict[str, Any]] = {}
        for entity_id, value in payload.items():
            if not isinstance(entity_id, str) or not entity_id.startswith("binary_sensor."):
                continue
            try:
                settings[entity_id] = self.normalize(value)
            except ValueError:
                continue
        return settings

    def save(self, entity_id: str, value: Any) -> dict[str, dict[str, Any]]:
        """Save one door-left-open reminder."""
        entity_id = str(entity_id or "").strip()
        if not entity_id.startswith("binary_sensor.") or len(entity_id) <= len("binary_sensor."):
            raise ValueError("A valid door or window sensor is required.")
        setting = self.normalize(value)
        with self._lock:
            payload = self._read_dict()
            payload[entity_id] = setting
            self._write_unlocked(payload)
        return self.read()


class DoorOpenAlertAutomationManager:
    """Generate native Home Assistant door-left-open reminder automations."""

    NOTIFICATION_TITLE = "Door Left Open"

    def __init__(
        self,
        path: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
    ) -> None:
        self._path = path
        self._publisher = publisher

    @staticmethod
    def describe(
        settings: dict[str, dict[str, Any]],
        entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return every reminder that produces an automation, in package order."""
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity
            for entity in entities
        }
        described: list[dict[str, Any]] = []
        for entity_id, raw_setting in sorted(
            device_alarm_buzzer_settings(settings, entities).items()
        ):
            entity = entities_by_id.get(entity_id)
            if not entity or not is_door_sensor_entity(entity) or is_refrigerator_entity(entity):
                continue
            try:
                setting = DoorOpenAlertSettings.normalize(raw_setting)
            except ValueError:
                continue
            if not setting["enabled"]:
                continue
            siren_targets, button_targets = device_alarm_output_targets(
                setting["alert_targets"], entities_by_id
            )
            webhook = setting["unifi_webhook"] and device_alarm_webhook_configured()
            if not (setting["notification"] or siren_targets or button_targets or webhook):
                continue
            digest = hashlib.sha1(entity_id.encode("utf-8")).hexdigest()[:16]
            described.append(
                {
                    "entity_id": entity_id,
                    "name": door_open_alert_display_name(entity),
                    "unique_id": DOOR_OPEN_ALERT_AUTOMATION_UNIQUE_ID_PREFIX + digest,
                    "notification_id": f"fht_door_open_{digest}",
                    "siren_targets": siren_targets,
                    "button_targets": button_targets,
                    "webhook": webhook,
                    **setting,
                }
            )
        return described

    def _automation_lines(self, item: dict[str, Any]) -> list[str]:
        entity_id = item["entity_id"]
        name = item["name"]
        duration = item["delay_minutes"]
        house_modes = list(DoorOpenAlertSettings.WHEN_HOUSE_MODES[item["when"]])
        message = (
            f"{name} is open."
            if not duration
            else f"{name} has been open for {duration} minutes."
        )
        lines = [
            f"  - id: {item['unique_id']}\n",
            f"    alias: {json.dumps(f'FHT - {name} Left Open')}\n",
            "    mode: restart\n",
            "    triggers:\n",
            "      - trigger: state\n",
            f"        entity_id: {entity_id}\n",
            '        to: "on"\n',
            *device_alarm_delay_lines(duration),
            "        id: alert\n",
        ]
        if house_modes:
            # Also look again when the house changes mode while the door is open.
            lines.extend(
                [
                    "      - trigger: state\n",
                    f"        entity_id: {HOUSE_MODE_HELPER}\n",
                    f"        to: {json.dumps(house_modes)}\n",
                    "        id: house_mode\n",
                ]
            )
        lines.extend(
            [
                "      - trigger: state\n",
                f"        entity_id: {entity_id}\n",
                '        to: "off"\n',
                "        id: clear\n",
                "    actions:\n",
                "      - choose:\n",
                "          - conditions:\n",
            ]
        )
        if house_modes:
            lines.extend(
                [
                    "              - condition: state\n",
                    f"                entity_id: {HOUSE_MODE_HELPER}\n",
                    f"                state: {json.dumps(house_modes)}\n",
                    "              - condition: or\n",
                    "                conditions:\n",
                    "                  - condition: trigger\n",
                    "                    id: alert\n",
                    "                  - condition: and\n",
                    "                    conditions:\n",
                    "                      - condition: trigger\n",
                    "                        id: house_mode\n",
                    "                      - condition: state\n",
                    f"                        entity_id: {entity_id}\n",
                    '                        state: "on"\n',
                    *device_alarm_delay_lines(duration, indent="                        "),
                ]
            )
        else:
            lines.extend(
                [
                    "              - condition: trigger\n",
                    "                id: alert\n",
                ]
            )
        lines.append("            sequence:\n")
        if item["notification"]:
            lines.extend(
                [
                    "              - action: persistent_notification.create\n",
                    "                data:\n",
                    f"                  notification_id: {item['notification_id']}\n",
                    f"                  title: {json.dumps(self.NOTIFICATION_TITLE)}\n",
                    f"                  message: {json.dumps(message)}\n",
                ]
            )
        lines.extend(
            device_alarm_alert_output_lines(
                item["siren_targets"],
                item["button_targets"],
                unifi_webhook=item["unifi_webhook"],
                alert_behavior="until_clear",
                still_active_lines=door_open_condition_lines(entity_id),
            )
        )
        lines.extend(
            device_alarm_clear_lines(
                item["notification_id"] if item["notification"] else None,
                item["siren_targets"],
            )
        )
        return lines

    def sync(
        self,
        settings: dict[str, dict[str, Any]],
        entities: list[dict[str, Any]],
        reload_automations: bool = True,
    ) -> list[dict[str, Any]]:
        """Write one managed automation per enabled door-left-open reminder."""
        described = self.describe(settings, entities)
        lines = ["# Managed by Future Homes Tech App.\n"]
        if not described:
            lines.append("automation: []\n")
        else:
            lines.append("automation:\n")
            for item in described:
                lines.extend(self._automation_lines(item))
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, "".join(lines))
                if changed and reload_automations and self._publisher:
                    self._publisher.reload_automations()
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write door left open automations: {err}"
            ) from err
        return [
            {
                key: value
                for key, value in item.items()
                if key not in {"siren_targets", "button_targets", "webhook", "notification_id"}
            }
            for item in described
        ]


class FutureTechPortalSettings(JsonSettingsStore):
    """Persist whether portal reports are on and which integrations report.

    The portal token is never stored here; it lives only in secrets.yaml.
    """

    READ_ERROR = "Unable to read Future Tech Portal settings"
    SAVE_ERROR = "Unable to save Future Tech Portal settings"
    TOLERATE_CORRUPT = True

    def _clean(self, payload: Any) -> dict[str, Any]:
        stored = payload if isinstance(payload, dict) else {}
        try:
            integrations = PORTAL.normalize_integrations(stored.get("integrations"))
        except ValueError:
            integrations = list(PORTAL.DEFAULT_INTEGRATIONS)
        return {"enabled": stored.get("enabled", True) is not False, "integrations": integrations}

    def save(self, enabled: Any, integrations: Any) -> dict[str, Any]:
        settings = {
            "enabled": bool(enabled),
            "integrations": PORTAL.normalize_integrations(integrations),
        }
        with self._lock:
            try:
                atomic_write_json(self._path, settings)
            except OSError as err:
                raise HomeAssistantAPIError(f"{self.SAVE_ERROR}: {err}") from err
        return settings


class FutureTechPortalManager:
    """Set up Home Assistant's push reports to the Future Tech Portal.

    The token goes only into secrets.yaml (future_tech_token); the generated
    package reads it with !secret. Nothing here logs, stores, or returns it.
    """

    RELOAD_DOMAINS = ("rest_command", "template", "script", "automation")

    def __init__(
        self,
        settings: FutureTechPortalSettings,
        config_directory: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
        option_token: str = "",
        option_url: str = "",
    ) -> None:
        self.settings = settings
        self._config_directory = config_directory
        self._publisher = publisher
        # The App's Configuration tab may hold the token and URL; the token is
        # copied into secrets.yaml on start and is never kept anywhere else here.
        self._option_token = str(option_token or "").strip()
        try:
            self.ingest_url = PORTAL.normalize_url(option_url)
            self.url_problem = ""
        except PORTAL.PortalError as err:
            self.ingest_url = PORTAL.INGEST_URL
            self.url_problem = f"{err} The default address is used."

    @property
    def token_from_options(self) -> bool:
        return bool(self._option_token)

    def apply_option_token(self) -> bool:
        """Copy the Configuration tab token into secrets.yaml; True when it changed."""
        if not self._option_token:
            return False
        try:
            value = PORTAL.normalize_token(self._option_token)
            secrets = PORTAL.read_text(self.secrets_path)
            updated = PORTAL.with_token(secrets, value)
            if updated == secrets:
                return False
            with CONFIGURATION_ACTIVATION_LOCK:
                PORTAL.write_private_text(self.secrets_path, updated)
            return True
        except PORTAL.PortalError as err:
            raise HomeAssistantAPIError(f"Future Tech Portal token from the App configuration: {err}") from None

    @property
    def secrets_path(self) -> Path:
        return self._config_directory / "secrets.yaml"

    @property
    def package_path(self) -> Path:
        return self._config_directory / "packages" / PORTAL.PACKAGE_FILENAME

    def token_saved(self) -> bool:
        return PORTAL.token_configured(PORTAL.read_text(self.secrets_path))

    def apply(self, *, reload: bool = True) -> bool:
        """Write the package while a token is saved and reports are on, else remove it."""
        settings = self.settings.read()
        with CONFIGURATION_ACTIVATION_LOCK:
            try:
                if self.token_saved() and settings["enabled"]:
                    changed = atomic_write_text(
                        self.package_path,
                        PORTAL.render_package(settings["integrations"], self.ingest_url),
                    )
                elif self.package_path.exists():
                    self.package_path.unlink()
                    changed = True
                else:
                    changed = False
            except OSError as err:
                raise HomeAssistantAPIError(
                    "Unable to write the Future Tech Portal package."
                ) from err
            if changed and reload and self._publisher:
                self._publisher.reload_domains(self.RELOAD_DOMAINS)
        return changed

    def save_token(self, raw_token: Any) -> None:
        """Store a pasted token in secrets.yaml, then install and reload the package."""
        if self.token_from_options:
            raise ValueError(
                "The token is set in the App's Configuration tab; change it there and restart the App."
            )
        try:
            value = PORTAL.normalize_token(raw_token)
            secrets = PORTAL.read_text(self.secrets_path)
            updated = PORTAL.with_token(secrets, value)
            with CONFIGURATION_ACTIVATION_LOCK:
                if updated != secrets:
                    PORTAL.write_private_text(self.secrets_path, updated)
        except PORTAL.PortalError as err:
            raise ValueError(str(err)) from None
        current = self.settings.read()
        if not current["enabled"]:
            self.settings.save(True, current["integrations"])
        # A changed token is read when rest_command reloads, even if the
        # package text itself did not change.
        if not self.apply() and self._publisher:
            self._publisher.reload_domains(("rest_command",))

    def remove_token(self) -> None:
        """Remove the package first, then the token, so the configuration stays valid."""
        if self.token_from_options:
            raise ValueError(
                "The token is set in the App's Configuration tab; clear it there and restart the App."
            )
        with CONFIGURATION_ACTIVATION_LOCK:
            if self.package_path.exists():
                try:
                    self.package_path.unlink()
                except OSError as err:
                    raise HomeAssistantAPIError(
                        "Unable to remove the Future Tech Portal package."
                    ) from err
                if self._publisher:
                    self._publisher.reload_domains(self.RELOAD_DOMAINS)
            try:
                secrets = PORTAL.read_text(self.secrets_path)
                updated = PORTAL.without_token(secrets)
                if updated != secrets:
                    PORTAL.write_private_text(self.secrets_path, updated)
            except PORTAL.PortalError as err:
                raise ValueError(str(err)) from None

    HISTORY_DAYS = 10  # Home Assistant's default recorder retention.

    def _history(self, entity_ids: list[str], start: datetime) -> list[list[dict[str, Any]]]:
        """Read state history for some entities from Home Assistant."""
        publisher = self._publisher
        if not publisher or not publisher._token:
            raise HomeAssistantAPIError("Home Assistant is unavailable.")
        base = publisher._services_url.rsplit("/services", 1)[0]
        query = "&".join(
            [
                f"filter_entity_id={quote(','.join(entity_ids), safe=',')}",
                f"end_time={quote(datetime.now(timezone.utc).isoformat())}",
                "minimal_response",
                "no_attributes",
            ]
        )
        request = Request(
            f"{base}/history/period/{quote(start.isoformat())}?{query}",
            headers={"Authorization": f"Bearer {publisher._token}", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as err:
            raise HomeAssistantAPIError("Unable to read device history from Home Assistant.") from err
        return payload if isinstance(payload, list) else []

    def backfill_last_seen(self, inventory: Any) -> int:
        """Find when devices that are offline now were last online, from history.

        Restarts reset an entity's "last changed", so the package keeps its own
        last-seen times; this fills them in for devices already offline. It
        returns how many devices were found.
        """
        if not self.package_path.exists():
            return 0
        try:
            sensor = inventory.fetch_state(PORTAL.DEVICES_SENSOR)
        except HomeAssistantAPIError:
            return 0
        attributes = sensor.get("attributes") or {}
        known = attributes.get("last_seen") or {}
        states = {
            str(entity.get("entity_id") or ""): str(entity.get("state") or "")
            for entity in inventory.fetch(include_all=True)["entities"]
        }
        missing = [
            entity_id
            for entity_id in attributes.get("monitored") or []
            if states.get(entity_id) in PORTAL.OFFLINE_STATES and entity_id not in known
        ]
        if not missing:
            return 0
        start = datetime.now(timezone.utc) - timedelta(days=self.HISTORY_DAYS)
        found: dict[str, str] = {}
        for index in range(0, len(missing), 40):
            for rows in self._history(missing[index:index + 40], start):
                if not rows or not isinstance(rows, list):
                    continue
                entity_id = str(rows[0].get("entity_id") or "")
                seen = PORTAL.last_seen_from_history(rows)
                if entity_id in missing and seen:
                    found[entity_id] = seen
        if found:
            self._publisher.fire_event("future_tech_portal_last_seen", {"last_seen": found})
        return len(found)

    def refresh_matter_networks(self) -> int:
        """Tell the package which network (Thread, Wi-Fi, Ethernet) each Matter device uses.

        Home Assistant's Matter entities don't say; the Matter integration's
        diagnostics do. Returns how many devices were matched.
        """
        publisher = self._publisher
        if not self.package_path.exists() or not publisher or not publisher._token:
            return 0
        storage = self._config_directory / ".storage"
        try:
            entries = json.loads((storage / "core.config_entries").read_text(encoding="utf-8"))
            devices = json.loads((storage / "core.device_registry").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        matter_entries = [
            str(entry.get("entry_id"))
            for entry in (entries.get("data") or {}).get("entries") or []
            if isinstance(entry, dict) and entry.get("domain") == "matter" and not entry.get("disabled_by")
        ]
        if not matter_entries:
            return 0
        base = publisher._services_url.rsplit("/services", 1)[0]
        networks: dict[str, str] = {}
        for entry_id in matter_entries:
            request = Request(
                f"{base}/diagnostics/config_entry/{quote(entry_id, safe='')}",
                headers={"Authorization": f"Bearer {publisher._token}", "Accept": "application/json"},
            )
            try:
                with urlopen(request, timeout=30) as response:
                    diagnostics = json.load(response)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as err:
                raise HomeAssistantAPIError("Unable to read Matter diagnostics from Home Assistant.") from err
            networks.update(PORTAL.matter_networks(devices, diagnostics))
        publisher.fire_event("future_tech_portal_networks", {"networks": networks})
        return len(networks)

    def refresh_system_versions(self) -> dict[str, Any]:
        """Tell the package the App, Core, Supervisor and OS versions, installed Apps and HACS items."""
        publisher = self._publisher
        if not self.package_path.exists() or not publisher or not publisher._token:
            return {}
        system = {"appVersion": os.environ.get("FHT_RUNNING_VERSION") or os.environ.get("FHT_STABLE_VERSION") or ""}
        request = Request(
            os.environ.get("SUPERVISOR_INFO_URL", "http://supervisor/info"),
            headers={"Authorization": f"Bearer {publisher._token}", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                info = (json.load(response) or {}).get("data") or {}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, AttributeError):
            info = {}
        for key, field in (("coreVersion", "homeassistant"), ("supervisorVersion", "supervisor"), ("osVersion", "hassos")):
            if info.get(field):
                system[key] = str(info[field])
        # Installed Apps (add-ons): /supervisor/info lists them with versions.
        base = os.environ.get("SUPERVISOR_INFO_URL", "http://supervisor/info").rsplit("/info", 1)[0]
        try:
            with urlopen(Request(f"{base}/supervisor/info", headers={
                "Authorization": f"Bearer {publisher._token}", "Accept": "application/json",
            }), timeout=10) as response:
                supervisor_info = (json.load(response) or {}).get("data") or {}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, AttributeError):
            supervisor_info = {}
        # One list for the portal's apps report: Apps (add-ons), then HACS items.
        apps = PORTAL.installed_apps(supervisor_info) + PORTAL.hacs_items(self._config_directory)
        if apps:
            system["apps"] = apps
        system = {key: value for key, value in system.items() if value}
        publisher.fire_event("future_tech_portal_system", {"system": system})
        return system

    def refresh_details(self, inventory: Any) -> None:
        """Fill in last-seen times, Matter networks and versions before an inventory."""
        for step, label in ((lambda: self.backfill_last_seen(inventory), "last seen"),
                            (self.refresh_matter_networks, "Matter networks"),
                            (self.refresh_system_versions, "versions")):
            try:
                step()
            except HomeAssistantAPIError as err:
                print(f"Future Tech Portal {label} not filled in: {err}", flush=True)

    def send_inventory(self, inventory: Any = None) -> None:
        """Ask Home Assistant to send the inventory now (also lifts a 401 pause)."""
        if not self._publisher:
            raise HomeAssistantAPIError("Home Assistant is unavailable.")
        if not self.package_path.exists():
            raise ValueError("Save a portal token first.")
        if inventory is not None:
            self.refresh_details(inventory)
        self._publisher._call_service(
            "script", "turn_on", {"entity_id": PORTAL.INVENTORY_SCRIPT}
        )

    def send_apps(self) -> int:
        """Send only the installed Apps and HACS versions now, whatever was sent today."""
        if not self._publisher:
            raise HomeAssistantAPIError("Home Assistant is unavailable.")
        if not self.package_path.exists():
            raise ValueError("Save a portal token first.")
        apps = self.refresh_system_versions().get("apps") or []
        if not apps:
            raise ValueError("No installed Apps or HACS items were found to send.")
        self._publisher._call_service(
            "script", "turn_on", {"entity_id": PORTAL.INVENTORY_SCRIPT, "variables": {"apps_only": True}}
        )
        return len(apps)

    def payload(self, inventory: Any) -> dict[str, Any]:
        """Describe the setup for the settings page; the token is never included."""
        settings = self.settings.read()
        token_saved = self.token_saved()
        states: dict[str, dict[str, Any] | None] = {}
        for entity_id in (PORTAL.STATUS_SENSOR, PORTAL.DEVICES_SENSOR, PORTAL.QUEUE_SENSOR):
            try:
                states[entity_id] = inventory.fetch_state(entity_id) if token_saved else None
            except HomeAssistantAPIError:
                states[entity_id] = None
        available = PORTAL.integrations_with_devices(self._config_directory)
        choices = list(dict.fromkeys([*PORTAL.DEFAULT_INTEGRATIONS, *settings["integrations"], *available]))
        return {
            "ok": True,
            "token_saved": token_saved,
            "token_source": "options" if self.token_from_options else ("page" if token_saved else ""),
            "url_problem": self.url_problem,
            "enabled": settings["enabled"],
            "integrations": settings["integrations"],
            "integration_choices": [
                {
                    "domain": domain,
                    "devices": available.get(domain, 0),
                    "default": domain in PORTAL.DEFAULT_INTEGRATIONS,
                }
                for domain in choices
            ],
            "package_installed": self.package_path.exists(),
            "endpoint": self.ingest_url,
            "include_label": PORTAL.INCLUDE_LABEL,
            "exclude_label": PORTAL.EXCLUDE_LABEL,
            "status": PORTAL.describe_status(
                states[PORTAL.STATUS_SENSOR],
                states[PORTAL.DEVICES_SENSOR],
                token_saved=token_saved,
                enabled=settings["enabled"],
                queue_state=states[PORTAL.QUEUE_SENSOR],
            ),
        }


class LightScheduleSettings(JsonSettingsStore):
    """Persist validated per-light ON and OFF schedule settings."""

    # A light group, or a single light that has no group of its own.
    LIGHT_ID = re.compile(r"light\.[a-z0-9_]+")

    EVENT_TYPES = frozenset({"sunrise", "sunset", "time"})
    COLOR_MODES = frozenset({"current", "adaptive", "kelvin", "rgb"})
    DEFAULT = {
        "enabled": False,
        "on_type": "sunset",
        "on_offset": 0,
        "on_time": "18:00",
        "off_type": "sunrise",
        "off_offset": 0,
        "off_time": "06:00",
        "brightness": 100,
        "color_mode": "current",
        "color_kelvin": 4000,
        "color_hex": "#ffffff",
    }
    READ_ERROR = "Unable to read light schedules"
    SAVE_ERROR = "Unable to save light schedule"

    @classmethod
    def normalize(cls, value: Any) -> dict[str, Any]:
        """Return one safe schedule configuration."""
        payload = value if isinstance(value, dict) else {}
        on_type = str(payload.get("on_type") or cls.DEFAULT["on_type"])
        off_type = str(payload.get("off_type") or cls.DEFAULT["off_type"])
        if on_type not in cls.EVENT_TYPES or off_type not in cls.EVENT_TYPES:
            raise ValueError("Schedule triggers must use sunrise, sunset, or time.")

        def valid_time(name: str, fallback: str) -> str:
            candidate = str(payload.get(name) or fallback)
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
                raise ValueError("Custom schedule times must use HH:MM.")
            return candidate

        try:
            on_offset = int(payload.get("on_offset", 0))
            off_offset = int(payload.get("off_offset", 0))
            brightness = int(payload.get("brightness", 100))
        except (TypeError, ValueError) as err:
            raise ValueError("Offsets and brightness must be whole numbers.") from err
        if not -360 <= on_offset <= 360 or not -360 <= off_offset <= 360:
            raise ValueError("Sun offsets must be between -360 and 360 minutes.")
        if not 1 <= brightness <= 100:
            raise ValueError("Brightness must be between 1 and 100 percent.")
        color_mode = str(payload.get("color_mode") or cls.DEFAULT["color_mode"])
        if color_mode not in cls.COLOR_MODES:
            raise ValueError("Color mode must use current, adaptive, kelvin, or rgb.")
        try:
            color_kelvin = int(payload.get("color_kelvin", cls.DEFAULT["color_kelvin"]))
        except (TypeError, ValueError) as err:
            raise ValueError("Color temperature must be a whole number.") from err
        if not 2000 <= color_kelvin <= 6500:
            raise ValueError("Color temperature must be between 2000 and 6500 kelvin.")
        color_hex = str(payload.get("color_hex") or cls.DEFAULT["color_hex"]).lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", color_hex):
            raise ValueError("Custom color must use a six-digit hex value.")
        return {
            "enabled": bool(payload.get("enabled", False)),
            "on_type": on_type,
            "on_offset": on_offset,
            "on_time": valid_time("on_time", cls.DEFAULT["on_time"]),
            "off_type": off_type,
            "off_offset": off_offset,
            "off_time": valid_time("off_time", cls.DEFAULT["off_time"]),
            "brightness": brightness,
            "color_mode": color_mode,
            "color_kelvin": color_kelvin,
            "color_hex": color_hex,
        }

    def _clean(self, payload: Any) -> dict[str, dict[str, Any]]:
        """Read every valid light schedule (light groups and single lights)."""
        if not isinstance(payload, dict):
            return {}
        schedules = {}
        for entity_id, value in payload.items():
            if not isinstance(entity_id, str) or not self.LIGHT_ID.fullmatch(entity_id):
                continue
            try:
                schedules[entity_id] = self.normalize(value)
            except ValueError:
                continue
        return schedules

    def save(self, entity_id: str, value: Any) -> dict[str, dict[str, Any]]:
        """Create or update one schedule."""
        if not self.LIGHT_ID.fullmatch(entity_id):
            raise ValueError("A light or Future Homes Tech light group is required.")
        schedule = self.normalize(value)
        with self._lock:
            payload = self._read_dict()
            payload[entity_id] = schedule
            self._write_unlocked(payload)
        return self.read()


class LightScheduleAutomationManager:
    """Generate native Home Assistant automations for light schedules."""

    def __init__(
        self,
        path: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
    ) -> None:
        self._path = path
        self._publisher = publisher

    @staticmethod
    def _trigger_lines(schedule_type: str, offset: int, custom_time: str) -> list[str]:
        if schedule_type == "time":
            return ["      - trigger: time\n", f"        at: \"{custom_time}:00\"\n"]
        lines = ["      - trigger: sun\n", f"        event: {schedule_type}\n"]
        if offset:
            sign = "-" if offset < 0 else ""
            hours, minutes = divmod(abs(offset), 60)
            lines.append(f"        offset: \"{sign}{hours:02d}:{minutes:02d}:00\"\n")
        return lines

    # Daylight tone: 2200 K before dawn, 6500 K with the sun high, scaled between.
    ADAPTIVE_ELEVATION_PREFIX = "{% set elevation = state_attr('sun.sun', 'elevation') | float(-6) %} "
    ADAPTIVE_KELVIN_EXPRESSION = (
        "2200 if elevation <= -6 else (6500 if elevation >= 45 else "
        "(2200 + ((elevation + 6) / 51 * 4300)) | round(0))"
    )

    @classmethod
    def _adaptive_kelvin_template(cls) -> str:
        return cls.ADAPTIVE_ELEVATION_PREFIX + "{{ " + cls.ADAPTIVE_KELVIN_EXPRESSION + " }}"

    @classmethod
    def _color_data_lines(cls, schedule: dict[str, Any]) -> list[str]:
        color_mode = schedule["color_mode"]
        if color_mode == "kelvin":
            return [f"                  color_temp_kelvin: {schedule['color_kelvin']}\n"]
        if color_mode == "rgb":
            color_hex = schedule["color_hex"].lstrip("#")
            rgb = [int(color_hex[index:index + 2], 16) for index in (0, 2, 4)]
            return [f"                  rgb_color: {json.dumps(rgb)}\n"]
        if color_mode == "adaptive":
            return [
                "                  color_temp_kelvin: "
                f"{json.dumps(cls._adaptive_kelvin_template())}\n"
            ]
        return []

    def sync(
        self,
        schedules: dict[str, dict[str, Any]],
        entities: list[dict[str, Any]],
        reload_automations: bool = True,
    ) -> list[dict[str, Any]]:
        """Write one managed automation per enabled light schedule."""
        names = {
            str(entity.get("entity_id") or ""): str(
                entity.get("friendly_name") or entity.get("entity_id") or ""
            )
            for entity in entities
        }
        automations = []
        lines = ["# Managed by Future Homes Tech App.\n", "automation:\n"]
        for entity_id, raw_schedule in sorted(schedules.items()):
            if entity_id not in names:
                continue
            schedule = LightScheduleSettings.normalize(raw_schedule)
            if not schedule["enabled"]:
                continue
            unique_id = LIGHT_SCHEDULE_AUTOMATION_UNIQUE_ID_PREFIX + hashlib.sha1(
                entity_id.encode("utf-8")
            ).hexdigest()[:16]
            friendly_name = names[entity_id]
            automations.append({"entity_id": entity_id, "name": friendly_name, **schedule})
            lines.extend(
                [
                    f"  - id: {unique_id}\n",
                    f"    alias: {json.dumps(f'FHT - {friendly_name} Schedule')}\n",
                    "    mode: restart\n",
                    "    triggers:\n",
                    *self._trigger_lines(schedule["on_type"], schedule["on_offset"], schedule["on_time"]),
                    "        id: turn_on\n",
                    *self._trigger_lines(schedule["off_type"], schedule["off_offset"], schedule["off_time"]),
                    "        id: turn_off\n",
                    *(
                        [
                            "      - trigger: time_pattern\n",
                            "        minutes: \"/15\"\n",
                            "        id: adaptive_refresh\n",
                        ]
                        if schedule["color_mode"] == "adaptive"
                        else []
                    ),
                    "    actions:\n",
                    "      - choose:\n",
                    "          - conditions:\n",
                    "              - condition: trigger\n",
                    "                id: turn_on\n",
                    "            sequence:\n",
                    "              - action: light.turn_on\n",
                    "                target:\n",
                    f"                  entity_id: {entity_id}\n",
                    "                data:\n",
                    f"                  brightness_pct: {schedule['brightness']}\n",
                    *self._color_data_lines(schedule),
                    *(
                        [
                            "          - conditions:\n",
                            "              - condition: trigger\n",
                            "                id: adaptive_refresh\n",
                            "              - condition: state\n",
                            f"                entity_id: {entity_id}\n",
                            "                state: \"on\"\n",
                            "            sequence:\n",
                            "              - action: light.turn_on\n",
                            "                target:\n",
                            f"                  entity_id: {entity_id}\n",
                            "                data:\n",
                            *self._color_data_lines(schedule),
                            "                  transition: 900\n",
                        ]
                        if schedule["color_mode"] == "adaptive"
                        else []
                    ),
                    "          - conditions:\n",
                    "              - condition: trigger\n",
                    "                id: turn_off\n",
                    "            sequence:\n",
                    "              - action: light.turn_off\n",
                    "                target:\n",
                    f"                  entity_id: {entity_id}\n",
                ]
            )
        content = "".join(lines)
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, content)
                if changed and reload_automations and self._publisher:
                    self._publisher.reload_automations()
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write light schedule automations: {err}"
            ) from err
        return automations


class RoomSceneSettings(JsonSettingsStore):
    """Keep each room/mode's lighting scene, including disabled-mode drafts."""

    READ_ERROR = "Unable to read room scenes"
    SAVE_ERROR = "Unable to save room scene"

    @staticmethod
    def normalize(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("A room scene must be an object.")
        brightness = value.get("brightness_pct", 100)
        if isinstance(brightness, bool) or not isinstance(brightness, int) or not 0 <= brightness <= 100:
            raise ValueError("Brightness must be a whole percentage from 0 to 100.")
        if value.get("color_mode", "current") not in {"current", "adaptive", "kelvin", "rgb"}:
            raise ValueError("Select a supported color, tone, or adaptive setting.")
        targets = value.get("targets", [])
        if not isinstance(targets, list) or len(targets) > 512 or any(
            not isinstance(target, str)
            or not re.fullmatch(r"light\.[a-z0-9_]+", target)
            for target in targets
        ):
            raise ValueError("Select valid lights or light groups for the scene.")
        return {
            **SwitchControlSettings._clean_action_setting(value),
            "targets": sorted(set(targets)),
        }

    def _clean(self, payload: Any) -> dict[str, dict[str, dict[str, Any]]]:
        if not isinstance(payload, dict):
            raise HomeAssistantAPIError("Room scenes storage is invalid.")
        try:
            for area, scenes in payload.items():
                if not isinstance(area, str) or not area.strip() or not isinstance(scenes, dict):
                    raise ValueError("Invalid room scene entry.")
                for mode, value in scenes.items():
                    if mode not in RoomModeSettings.ALLOWED_MODES:
                        raise ValueError("Invalid room scene mode.")
                    self.normalize(value)
        except ValueError as err:
            raise HomeAssistantAPIError(f"Unable to read room scenes: {err}") from err
        return payload

    def save(
        self,
        area: str,
        mode: str,
        value: Any,
        enabled_modes: dict[str, list[str]],
        valid_targets: set[str],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        if not area or mode not in enabled_modes.get(area, []):
            raise ValueError("Enable this room mode in Room Modes before configuring its scene.")
        setting = self.normalize(value)
        if not set(setting["targets"]).issubset(valid_targets):
            raise ValueError("One or more selected lights no longer exist. Refresh and select again.")
        with CONFIGURATION_ACTIVATION_LOCK:
            settings = self.read()
            settings.setdefault(area, {})[mode] = setting
            with self._lock:
                self._write_unlocked(settings)
        return settings


class RoomSceneAutomationManager:
    """Apply saved lighting scenes only when the corresponding room mode changes."""

    def __init__(
        self, path: Path, publisher: HomeAssistantHelperPublisher | None = None
    ) -> None:
        self._path = path
        self._publisher = publisher

    def sync(
        self,
        settings: dict[str, dict[str, dict[str, Any]]],
        enabled_modes: dict[str, list[str]],
        reload_automations: bool = True,
    ) -> list[dict[str, str]]:
        automations = []
        lines = []
        labels = dict(RoomModeSettings.AVAILABLE_MODES)
        for area, modes in sorted(enabled_modes.items()):
            for mode in sorted(modes):
                raw = settings.get(area, {}).get(mode)
                if mode not in labels or raw is None:
                    continue
                setting = RoomSceneSettings.normalize(raw)
                if not setting["targets"]:
                    continue
                slug = BedroomModeAutomationManager._slug(area)
                digest = hashlib.sha256(area.encode("utf-8")).hexdigest()[:8]
                automation_id = f"{ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX}{slug}_{digest}_{mode}_lights"
                label = labels[mode]
                automations.append({"id": automation_id, "area": area, "mode": mode})
                lines.extend([
                    f"  - id: {json.dumps(automation_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} - {label} Scene')}\n",
                    "    mode: restart\n",
                    "    triggers:\n",
                    "      - trigger: state\n",
                    f"        entity_id: input_select.fht_{slug}_mode\n",
                    f"        to: {json.dumps(label)}\n",
                    "    conditions:\n",
                    "      - condition: template\n",
                    '        value_template: "{{ trigger.from_state is not none and trigger.from_state.state not in [\'unknown\', \'unavailable\'] }}"\n',
                    "    actions:\n",
                    f"      - action: light.{'turn_on' if setting['brightness_pct'] else 'turn_off'}\n",
                    "        target:\n",
                    f"          entity_id: {json.dumps(setting['targets'])}\n",
                ])
                if setting["brightness_pct"]:
                    lines.extend(ControlAutomationManager._door_light_data_lines(setting, "        "))
        content = "automation:\n" + "".join(lines) if lines else "automation: []\n"
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                atomic_write_text(self._path, content)
                if reload_automations and self._publisher:
                    self._publisher.reload_automations()
        except OSError as err:
            raise HomeAssistantAPIError(f"Unable to write room scene automations: {err}") from err
        return automations


class BedroomModeAutomationManager:
    """Generate bedroom security and occupancy-simulation automations."""

    def __init__(
        self,
        path: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
        armed_away_webhook_configured: bool = False,
        armed_stay_kids_webhook_configured: bool = False,
        room_modes: RoomModeSettings | None = None,
    ) -> None:
        self._path = path
        self._publisher = publisher
        self._room_modes = room_modes
        self._house_settings_lock = threading.Lock()
        self._armed_away_webhook_configured = armed_away_webhook_configured
        self._armed_stay_kids_webhook_configured = (
            armed_stay_kids_webhook_configured
        )

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return slug or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]

    def app_color(self) -> str:
        with self._house_settings_lock:
            try:
                color = json.loads(self._path.with_suffix(".appearance.json").read_text()).get("color")
            except (OSError, ValueError, AttributeError):
                return "blue"
        return color if color in ("blue", "red", "green") else "blue"

    def save_app_color(self, color: str) -> str:
        if color not in ("blue", "red", "green"):
            raise ValueError("App Color must be blue, red, or green.")
        with self._house_settings_lock:
            atomic_write_json(self._path.with_suffix(".appearance.json"), {"color": color})
        return color

    def house_settings(self) -> dict[str, Any]:
        defaults = {
            "day_offset": 0,
            "night_offset": 0,
            "sleep_mode_sources": ["*"],
        }
        with self._house_settings_lock:
            try:
                payload = json.loads(
                    self._path.with_suffix(".house.json").read_text(
                        encoding="utf-8"
                    )
                )
            except FileNotFoundError:
                return defaults
            except (OSError, ValueError):
                return defaults
        if not isinstance(payload, dict):
            return defaults
        settings: dict[str, Any] = {}
        for key, default in defaults.items():
            value = payload.get(key, default)
            if key == "sleep_mode_sources":
                settings[key] = (
                    sorted(set(value))
                    if isinstance(value, list)
                    and all(
                        source == "*"
                        or re.fullmatch(r"input_select\.fht_[a-z0-9_]+_mode", str(source))
                        for source in value
                    )
                    else default
                )
            else:
                settings[key] = (
                    value
                    if isinstance(value, int)
                    and not isinstance(value, bool)
                    and -120 <= value <= 120
                    else default
                )
        if isinstance(payload.get("floor_sleep_modes"), dict):
            settings["floor_sleep_modes"] = self.clean_floor_sleep_modes(payload["floor_sleep_modes"])
        return settings

    @staticmethod
    def clean_floor_sleep_modes(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("Floor Sleep settings must be an object.")
        cleaned = {}
        for floor_id, setting in raw.items():
            if not isinstance(floor_id, str) or not floor_id or not isinstance(setting, dict):
                raise ValueError("Invalid floor Sleep settings.")
            sources = setting.get("sources", [])
            name = setting.get("name", "")
            if not isinstance(name, str) or not name.strip() or not isinstance(sources, list) or any(
                not isinstance(source, str) or not re.fullmatch(r"input_select\.fht_[a-z0-9_]+_mode", source)
                for source in sources
            ):
                raise ValueError("Floor Sleep sources must be bedroom-mode helpers.")
            cleaned[floor_id] = {"name": name.strip(), "sources": sorted(set(sources))}
        return cleaned

    @staticmethod
    def floor_sleep_templates(settings: dict[str, Any]) -> list[dict[str, Any]]:
        return [{
            "name": f"{setting['name']} Sleep Mode",
            "unique_id": "fht_floor_sleep_" + hashlib.sha1(floor_id.encode()).hexdigest()[:16],
            "state": "{{ expand(" + repr(setting["sources"]) + ") | selectattr('state', 'eq', 'Sleep') | list | count > 0 }}",
        } for floor_id, setting in sorted(settings.items())]

    def save_house_settings(self, payload: dict) -> dict[str, Any]:
        settings: dict[str, Any] = {}
        for key in ("day_offset", "night_offset"):
            value = payload.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or not -120 <= value <= 120:
                raise ValueError("Offsets must be whole minutes from -120 to 120.")
            settings[key] = value
        raw_sources = payload.get(
            "sleep_mode_sources",
            self.house_settings().get("sleep_mode_sources", ["*"]),
        )
        if not isinstance(raw_sources, list) or any(
            not isinstance(source, str)
            or (
                source != "*"
                and not re.fullmatch(r"input_select\.fht_[a-z0-9_]+_mode", source)
            )
            for source in raw_sources
        ):
            raise ValueError("Sleep mode sources must be room-mode helpers.")
        settings["sleep_mode_sources"] = sorted(set(raw_sources))
        floor_modes = payload.get("floor_sleep_modes", self.house_settings().get("floor_sleep_modes"))
        if floor_modes is not None:
            settings["floor_sleep_modes"] = self.clean_floor_sleep_modes(floor_modes)
        path = self._path.with_suffix(".house.json")
        with self._house_settings_lock:
            try:
                atomic_write_json(path, settings)
            except OSError as err:
                raise HomeAssistantAPIError(
                    f"Unable to save Whole Home settings: {err}"
                ) from err
        return settings

    @staticmethod
    def _solar_timestamp(value: Any) -> float | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            ).timestamp()
        except ValueError:
            return None

    def solar_day(
        self,
        sun: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> bool | None:
        """Return Day or Night from solar boundaries, or None if unknown."""
        offsets = self.house_settings()
        attributes = sun.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        now_timestamp = (now or datetime.now(timezone.utc)).timestamp()
        last_transition = self._solar_timestamp(sun.get("last_changed"))
        next_rising = self._solar_timestamp(
            attributes.get("next_rising") or sun.get("next_rising")
        )
        next_setting = self._solar_timestamp(
            attributes.get("next_setting") or sun.get("next_setting")
        )
        state = str(sun.get("state") or "").casefold()

        if state == "above_horizon" and last_transition and next_setting:
            day_start = last_transition + offsets["day_offset"] * 60
            night_start = next_setting + offsets["night_offset"] * 60
            return day_start <= now_timestamp < night_start
        if state == "below_horizon" and last_transition and next_rising:
            night_start = last_transition + offsets["night_offset"] * 60
            day_start = next_rising + offsets["day_offset"] * 60
            return now_timestamp < night_start or now_timestamp >= day_start
        if state in {"above_horizon", "below_horizon"}:
            return state == "above_horizon"
        return None

    @staticmethod
    def _solar_trigger_lines(event: str, offset: int) -> list[str]:
        lines = ["      - trigger: sun\n", f"        event: {event}\n"]
        if offset:
            sign = "-" if offset < 0 else ""
            hours, minutes = divmod(abs(offset), 60)
            lines.append(
                f'        offset: "{sign}{hours:02d}:{minutes:02d}:00"\n'
            )
        return lines

    @staticmethod
    def _area_entities(
        entities: list[dict[str, Any]],
        area: str,
        prefix: str,
    ) -> list[dict[str, Any]]:
        return [
            entity
            for entity in entities
            if str(entity.get("entity_id") or "").startswith(prefix)
            and str(entity.get("original_area") or entity.get("area") or "")
            == area
        ]

    @staticmethod
    def _hex_rgb(value: str) -> list[int]:
        """Convert one validated CSS hex color to Home Assistant RGB values."""
        return [int(value[index:index + 2], 16) for index in (1, 3, 5)]

    @staticmethod
    def _number_or_select_action_lines(
        entity_id: str,
        value: int,
        indent: str,
    ) -> list[str]:
        if not entity_id:
            return []
        if entity_id.startswith("select."):
            return [
                f"{indent}- action: select.select_option\n",
                f"{indent}  target: {{entity_id: {entity_id}}}\n",
                f"{indent}  data: {{option: {json.dumps(str(value))}}}\n",
            ]
        return [
            f"{indent}- action: number.set_value\n",
            f"{indent}  target: {{entity_id: {entity_id}}}\n",
            f"{indent}  data: {{value: {value}}}\n",
        ]

    def sync(
        self,
        settings: dict[str, dict[str, Any]],
        entities: list[dict[str, Any]],
        door_sensors: list[dict[str, Any]],
        reload_managed: bool = True,
        notify_services: set[str] | None = None,
    ) -> list[dict[str, str]]:
        """Write current bedroom mode automations into one managed package.

        ``notify_services`` lists the phones Home Assistant can notify right
        now (``None`` keeps every saved phone); see
        ``FridgeAlarmAutomationManager.sync``.
        """
        automations: list[dict[str, str]] = []
        house_offsets = self.house_settings()
        lines = [
            "# Managed by Future Homes Tech App.\n",
            "input_select:\n",
            "  fht_house_mode:\n",
            '    name: "Future Homes Tech House Mode"\n',
            "    icon: mdi:home-clock\n",
            "    options:\n",
            "      - Day\n",
            "      - Night\n",
            "      - Sleep\n",
        ]
        helper_areas = set(settings) | (set(self._room_modes.read()) if self._room_modes else set())
        for area in sorted(helper_areas):
            slug = self._slug(area)
            lines.extend([
                f"  fht_{slug}_mode:\n",
                f"    name: {json.dumps(f'Future Homes Tech {area} Mode')}\n",
                "    icon: mdi:home-shield\n",
                "    options:\n",
                *[
                    f"      - {label}\n"
                    for _mode, label in RoomModeSettings.HELPER_MODES
                ],
            ])
        toddler_areas = [
            area
            for area, setting in sorted(settings.items())
            if BedroomModeSettings.normalize(setting)["toddler_enabled"]
        ]
        if toddler_areas:
            lines.append("\ninput_boolean:\n")
            for area in toddler_areas:
                slug = self._slug(area)
                lines.extend([
                    f"  fht_{slug}_toddler_door_armed:\n",
                    f"    name: {json.dumps(f'Future Homes Tech {area} Toddler Door Armed')}\n",
                    "    icon: mdi:door-closed-lock\n",
                ])
            lines.append("\ntimer:\n")
            for area in toddler_areas:
                slug = self._slug(area)
                lines.extend([
                    f"  fht_{slug}_toddler_timeout:\n",
                    f"    name: {json.dumps(f'Future Homes Tech {area} Toddler Timeout')}\n",
                    "    restore: true\n",
                ])
        lines.append("\nautomation:\n")
        bedroom_mode_helpers = [
            f"input_select.fht_{self._slug(area)}_mode"
            for area in sorted(helper_areas)
        ]
        configured_sleep_sources = house_offsets.get("sleep_mode_sources", ["*"])
        sleep_mode_helpers = (
            bedroom_mode_helpers
            if "*" in configured_sleep_sources
            else [
                entity_id
                for entity_id in bedroom_mode_helpers
                if entity_id in configured_sleep_sources
            ]
        )
        house_automation_id = (
            f"{ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX}house_status"
        )
        automations.append(
            {
                "id": house_automation_id,
                "area": "House",
                "mode": "House Mode Status",
            }
        )
        lines.extend([
            f"  - id: {json.dumps(house_automation_id)}\n",
            '    alias: "FHT - House Mode Status"\n',
            "    mode: restart\n",
            "    triggers:\n",
            "      - trigger: sun\n",
            "        event: sunrise\n",
            f'        offset: "{self._offset_string(house_offsets["day_offset"])}"\n',
            "      - trigger: sun\n",
            "        event: sunset\n",
            f'        offset: "{self._offset_string(house_offsets["night_offset"])}"\n',
            # No minute-by-minute check: sunrise, sunset, bedroom Sleep changes
            # and start-up are every moment the house mode can change.
            *(
                [
                    "      - trigger: state\n",
                    "        entity_id:\n",
                    *[
                        f"          - {entity_id}\n"
                        for entity_id in sleep_mode_helpers
                    ],
                ]
                if sleep_mode_helpers
                else []
            ),
            "      - trigger: homeassistant\n",
            "        event: start\n",
            "    actions:\n",
            "      - choose:\n",
            "          - conditions: >-\n",
            (
                "              {{ expand("
                + json.dumps(sleep_mode_helpers)
                + ") | selectattr('state', 'eq', 'Sleep') | list | count > 0 }}\n"
                if sleep_mode_helpers
                else "              {{ false }}\n"
            ),
            "            sequence:\n",
            "              - action: input_select.select_option\n",
            f"                target: {{entity_id: {HOUSE_MODE_HELPER}}}\n",
            "                data: {option: Sleep}\n",
            "          - conditions:\n",
            "              - condition: sun\n",
            "                after: sunrise\n",
            f'                after_offset: "{self._offset_string(house_offsets["day_offset"])}"\n',
            "                before: sunset\n",
            f'                before_offset: "{self._offset_string(house_offsets["night_offset"])}"\n',
            "            sequence:\n",
            "              - action: input_select.select_option\n",
            f"                target: {{entity_id: {HOUSE_MODE_HELPER}}}\n",
            "                data: {option: Day}\n",
            "        default:\n",
            "          - action: input_select.select_option\n",
            f"            target: {{entity_id: {HOUSE_MODE_HELPER}}}\n",
            "            data: {option: Night}\n",
        ])
        for area, raw_setting in sorted(settings.items()):
            setting = BedroomModeSettings.normalize(raw_setting)
            slug = self._slug(area)
            area_doors = self._area_entities(door_sensors, area, "binary_sensor.")
            area_door_ids = [entity["entity_id"] for entity in area_doors]
            area_lights = self._area_entities(entities, area, LIGHT_GROUP_ENTITY_PREFIX)
            subgroup_lights = [
                entity["entity_id"]
                for entity in area_lights
                if " all lights" not in str(
                    entity.get("friendly_name") or ""
                ).lower()
            ]
            light_ids = subgroup_lights or [
                entity["entity_id"] for entity in area_lights
            ]

            if setting["disarmed_enabled"]:
                automation_id = (
                    f"{ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX}{slug}_status"
                )
                mode_helper = f"input_select.fht_{slug}_mode"
                automations.append({"id": automation_id, "area": area, "mode": "Bedroom Status"})
                lines.extend([
                    f"  - id: {json.dumps(automation_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} Room Mode Status')}\n",
                    "    mode: restart\n",
                    "    triggers:\n",
                    "      - trigger: state\n",
                    f"        entity_id: {PROTECT_STATUS_HELPER}\n",
                    *self._solar_trigger_lines(
                        setting["day_event"],
                        setting["day_offset"],
                    ),
                    *self._solar_trigger_lines(
                        setting["night_event"],
                        setting["night_offset"],
                    ),
                    "      - trigger: homeassistant\n",
                    "        event: start\n",
                    "    actions:\n",
                    "      - condition: template\n",
                    "        value_template: >-\n",
                    f"          {{{{ 'away' in states('{PROTECT_STATUS_HELPER}') | lower or 'stay' in states('{PROTECT_STATUS_HELPER}') | lower or states('{mode_helper}') not in ['Sleep', 'Toddler'] }}}}\n",
                    "      - choose:\n",
                    "          - conditions: >-\n",
                    f"              {{{{ 'away' in states('{PROTECT_STATUS_HELPER}') | lower }}}}\n",
                    "            sequence:\n",
                    "              - action: input_select.select_option\n",
                    f"                target: {{entity_id: {mode_helper}}}\n",
                    "                data: {option: Armed Away}\n",
                    "          - conditions: >-\n",
                    f"              {{{{ 'stay' in states('{PROTECT_STATUS_HELPER}') | lower }}}}\n",
                    "            sequence:\n",
                    "              - action: input_select.select_option\n",
                    f"                target: {{entity_id: {mode_helper}}}\n",
                    f"                data: {{option: {'Armed Stay Kids' if setting['armed_stay_kids_enabled'] else 'Armed Stay Adult'}}}\n",
                    "          - conditions:\n",
                    "              - condition: sun\n",
                    f"                after: {setting['day_event']}\n",
                    f"                after_offset: {json.dumps(self._offset_string(setting['day_offset']))}\n",
                    f"                before: {setting['night_event']}\n",
                    f"                before_offset: {json.dumps(self._offset_string(setting['night_offset']))}\n",
                    "            sequence:\n",
                    "              - action: input_select.select_option\n",
                    f"                target: {{entity_id: {mode_helper}}}\n",
                    "                data: {option: Day}\n",
                    "        default:\n",
                    "          - action: input_select.select_option\n",
                    f"            target: {{entity_id: {mode_helper}}}\n",
                    "            data: {option: Night}\n",
                ])

            toddler_door = setting["toddler_door_sensor"]
            if setting["toddler_enabled"] and not toddler_door and area_door_ids:
                toddler_door = area_door_ids[0]
            toddler_lights = setting["toddler_light_entities"]
            if setting["toddler_enabled"] and toddler_door and toddler_lights:
                automation_id = f"{ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX}{slug}_toddler"
                mode_helper = f"input_select.fht_{slug}_mode"
                armed_helper = f"input_boolean.fht_{slug}_toddler_door_armed"
                timeout_helper = f"timer.fht_{slug}_toddler_timeout"
                rgb = self._hex_rgb(setting["toddler_color"])
                automations.append({"id": automation_id, "area": area, "mode": "Toddler"})
                lines.extend([
                    f"  - id: {json.dumps(automation_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} Toddler Mode')}\n",
                    "    mode: queued\n",
                    "    max: 10\n",
                    "    triggers:\n",
                    "      - trigger: state\n",
                    f"        entity_id: {mode_helper}\n",
                    "        to: Toddler\n",
                    "        id: mode_on\n",
                    "      - trigger: state\n",
                    f"        entity_id: {mode_helper}\n",
                    "        from: Toddler\n",
                    "        id: mode_off\n",
                    "      - trigger: state\n",
                    f"        entity_id: {toddler_door}\n",
                    '        to: "off"\n',
                    "        id: door_closed\n",
                    "      - trigger: state\n",
                    f"        entity_id: {toddler_door}\n",
                    '        to: "on"\n',
                    "        id: door_opened\n",
                    "      - trigger: event\n",
                    "        event_type: timer.finished\n",
                    "        event_data:\n",
                    f"          entity_id: {timeout_helper}\n",
                    "        id: timeout\n",
                    "    actions:\n",
                    "      - choose:\n",
                    "          - conditions:\n",
                    "              - condition: trigger\n",
                    "                id: mode_on\n",
                    "            sequence:\n",
                    "              - action: light.turn_on\n",
                    f"                target: {{entity_id: {json.dumps(toddler_lights)}}}\n",
                    "                data:\n",
                    f"                  brightness_pct: {setting['toddler_brightness']}\n",
                    f"                  rgb_color: {json.dumps(rgb)}\n",
                    "                  transition: 1\n",
                    "              - if:\n",
                    "                  - condition: state\n",
                    f"                    entity_id: {toddler_door}\n",
                    '                    state: "off"\n',
                    "                then:\n",
                    "                  - action: light.turn_off\n",
                    f"                    target: {{entity_id: {json.dumps(toddler_lights)}}}\n",
                    "                  - action: input_boolean.turn_on\n",
                    f"                    target: {{entity_id: {armed_helper}}}\n",
                    "          - conditions:\n",
                    "              - condition: trigger\n",
                    "                id: door_closed\n",
                    "              - condition: state\n",
                    f"                entity_id: {mode_helper}\n",
                    "                state: Toddler\n",
                    "            sequence:\n",
                    "              - action: light.turn_off\n",
                    f"                target: {{entity_id: {json.dumps(toddler_lights)}}}\n",
                    "              - action: input_boolean.turn_on\n",
                    f"                target: {{entity_id: {armed_helper}}}\n",
                    "          - conditions:\n",
                    "              - condition: trigger\n",
                    "                id: door_opened\n",
                    "              - condition: state\n",
                    f"                entity_id: {mode_helper}\n",
                    "                state: Toddler\n",
                    "              - condition: state\n",
                    f"                entity_id: {armed_helper}\n",
                    '                state: "on"\n',
                    "            sequence:\n",
                    "              - action: input_boolean.turn_off\n",
                    f"                target: {{entity_id: {armed_helper}}}\n",
                    "              - action: light.turn_on\n",
                    f"                target: {{entity_id: {json.dumps(toddler_lights)}}}\n",
                    "                data:\n",
                    f"                  brightness_pct: {setting['toddler_brightness']}\n",
                    f"                  rgb_color: {json.dumps(rgb)}\n",
                    "                  transition: 1\n",
                ])
                effect_entity = setting["toddler_indicator_effect_entity"]
                effect = setting["toddler_indicator_effect"]
                if effect_entity and effect:
                    lines.extend([
                        "              - action: select.select_option\n",
                        f"                target: {{entity_id: {effect_entity}}}\n",
                        f"                data: {{option: {json.dumps(effect)}}}\n",
                    ])
                lines.extend(self._number_or_select_action_lines(
                    setting["toddler_indicator_color_entity"],
                    setting["toddler_indicator_color"],
                    "              ",
                ))
                lines.extend(self._number_or_select_action_lines(
                    setting["toddler_indicator_brightness_entity"],
                    setting["toddler_indicator_brightness"],
                    "              ",
                ))
                if setting["toddler_chime_entities"]:
                    lines.extend([
                        "              - repeat:\n",
                        f"                  count: {setting['toddler_chime_repeats']}\n",
                        "                  sequence:\n",
                        "                    - action: button.press\n",
                        f"                      target: {{entity_id: {json.dumps(setting['toddler_chime_entities'])}}}\n",
                        "                    - if:\n",
                        "                        - condition: template\n",
                        f"                          value_template: \"{{{{ repeat.index < {setting['toddler_chime_repeats']} }}}}\"\n",
                        "                      then:\n",
                        f"                        - delay: {setting['toddler_chime_interval_seconds']}\n",
                    ])
                if setting["toddler_timeout_minutes"]:
                    lines.extend([
                        "              - action: timer.start\n",
                        f"                target: {{entity_id: {timeout_helper}}}\n",
                        f"                data: {{duration: {setting['toddler_timeout_minutes'] * 60}}}\n",
                    ])
                lines.extend([
                    "          - conditions:\n",
                    "              - condition: trigger\n",
                    "                id:\n",
                    "                  - mode_off\n",
                    "                  - timeout\n",
                    "            sequence:\n",
                    "              - action: input_boolean.turn_off\n",
                    f"                target: {{entity_id: {armed_helper}}}\n",
                    "              - action: timer.cancel\n",
                    f"                target: {{entity_id: {timeout_helper}}}\n",
                ])
                if effect_entity and setting["toddler_indicator_off_effect"]:
                    lines.extend([
                        "              - action: select.select_option\n",
                        f"                target: {{entity_id: {effect_entity}}}\n",
                        f"                data: {{option: {json.dumps(setting['toddler_indicator_off_effect'])}}}\n",
                    ])
                if setting["toddler_timeout_minutes"]:
                    lines.extend([
                        "              - if:\n",
                        "                  - condition: trigger\n",
                        "                    id: timeout\n",
                        "                then:\n",
                        "                  - action: input_select.select_option\n",
                        f"                    target: {{entity_id: {mode_helper}}}\n",
                        "                    data:\n",
                        "                      option: \"{{ 'Day' if is_state('sun.sun', 'above_horizon') else 'Night' }}\"\n",
                    ])

            away_phones = [
                service
                for service in setting["armed_away_notify_targets"]
                if notify_services is None or service in notify_services
            ]
            if (
                setting["armed_away_enabled"]
                and area_door_ids
                and (self._armed_away_webhook_configured or away_phones)
            ):
                automation_id = (
                    f"{ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX}{slug}_armed_away_doors"
                )
                automations.append({"id": automation_id, "area": area, "mode": "Armed Away"})
                lines.extend([
                    f"  - id: {json.dumps(automation_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} Armed Away Door Alert')}\n",
                    "    mode: single\n",
                    "    triggers:\n",
                    *[
                        line
                        for entity_id in area_door_ids
                        for line in (
                            "      - trigger: state\n",
                            f"        entity_id: {entity_id}\n",
                            '        to: "on"\n',
                        )
                    ],
                    "    conditions:\n",
                    "      - condition: template\n",
                    "        value_template: >-\n",
                    f"          {{{{ 'away' in states('{PROTECT_STATUS_HELPER}') | lower }}}}\n",
                    "    actions:\n",
                    *(
                        ["      - action: rest_command.future_homes_tech_bedroom_armed_away\n"]
                        if self._armed_away_webhook_configured
                        else []
                    ),
                    *phone_notify_action_lines(
                        away_phones,
                        "      ",
                        "Armed Away Door Alert",
                        f"{area} door opened while Armed Away.",
                    ),
                ])

            kids_door_ids = area_door_ids
            kids_phones = [
                service
                for service in setting["armed_stay_kids_notify_targets"]
                if notify_services is None or service in notify_services
            ]
            if (
                setting["armed_stay_kids_enabled"]
                and kids_door_ids
                and (self._armed_stay_kids_webhook_configured or kids_phones)
            ):
                automation_id = (
                    f"{ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX}{slug}_armed_stay_kids"
                )
                automations.append({"id": automation_id, "area": area, "mode": "Armed Stay Kids"})
                lines.extend([
                    f"  - id: {json.dumps(automation_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} Armed Stay Kids Door Alert')}\n",
                    "    mode: single\n",
                    "    triggers:\n",
                    *[
                        line
                        for entity_id in kids_door_ids
                        for line in (
                            "      - trigger: state\n",
                            f"        entity_id: {entity_id}\n",
                            '        to: "on"\n',
                        )
                    ],
                    "    conditions:\n",
                    "      - condition: template\n",
                    "        value_template: >-\n",
                    f"          {{{{ 'stay' in states('{PROTECT_STATUS_HELPER}') | lower }}}}\n",
                    "    actions:\n",
                    *(
                        ["      - action: rest_command.future_homes_tech_bedroom_armed_stay_kids\n"]
                        if self._armed_stay_kids_webhook_configured
                        else []
                    ),
                    *phone_notify_action_lines(
                        kids_phones,
                        "      ",
                        "Armed Stay Kids Door Alert",
                        f"{area} door opened while Armed Stay Kids.",
                    ),
                ])

            if (
                setting["armed_away_enabled"]
                and setting["random_lights_enabled"]
                and light_ids
            ):
                automation_id = (
                    f"{ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX}{slug}_away_random_lights"
                )
                automations.append({"id": automation_id, "area": area, "mode": "Armed Away Random Lights"})
                lines.extend([
                    f"  - id: {json.dumps(automation_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} Armed Away Random Lights')}\n",
                    "    mode: single\n",
                    "    triggers:\n",
                    '      - trigger: time_pattern\n',
                    '        minutes: "/10"\n',
                    "    conditions:\n",
                    "      - condition: template\n",
                    "        value_template: >-\n",
                    f"          {{{{ 'away' in states('{PROTECT_STATUS_HELPER}') | lower }}}}\n",
                    "      - condition: sun\n",
                    f"        after: {setting['random_start_event']}\n",
                    f"        after_offset: {json.dumps(self._offset_string(setting['random_start_offset']))}\n",
                    f"        before: {setting['random_end_event']}\n",
                    f"        before_offset: {json.dumps(self._offset_string(setting['random_end_offset']))}\n",
                    "    actions:\n",
                    "      - variables:\n",
                    f"          fht_target: {json.dumps('{{ ' + json.dumps(light_ids) + ' | random }}')}\n",
                    "          fht_turn_on: \"{{ range(0, 2) | random == 1 }}\"\n",
                    "      - choose:\n",
                    "          - conditions: \"{{ fht_turn_on }}\"\n",
                    "            sequence:\n",
                    "              - action: light.turn_on\n",
                    "                target:\n",
                    "                  entity_id: \"{{ fht_target }}\"\n",
                    "                data:\n",
                    "                  brightness_pct: \"{{ range(35, 101) | random }}\"\n",
                    "        default:\n",
                    "          - action: light.turn_off\n",
                    "            target:\n",
                    "              entity_id: \"{{ fht_target }}\"\n",
                ])

        floor_templates = self.floor_sleep_templates(house_offsets.get("floor_sleep_modes", {}))
        if floor_templates:
            lines.append("\ntemplate: " + json.dumps([{"binary_sensor": floor_templates}]) + "\n")
        content = "".join(lines)
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, content)
                if changed and reload_managed and self._publisher:
                    self._publisher.reload_domains(
                        (
                            *(("template",) if "floor_sleep_modes" in house_offsets else ()),
                            "input_select",
                            "input_boolean",
                            "timer",
                            "automation",
                        )
                    )
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write bedroom mode automations: {err}"
            ) from err
        return automations

    def refresh_house_mode(
        self,
        settings: dict[str, dict[str, Any]],
        inventory: EntityInventory,
    ) -> str:
        """Immediately reconcile the house mode from bedrooms and the sun."""
        mode = "Night"
        snapshot = inventory.fetch(include_all=True)
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity
            for entity in snapshot["entities"]
        }
        configured_sleep_sources = self.house_settings().get(
            "sleep_mode_sources", ["*"]
        )
        helper_areas = set(settings) | (set(self._room_modes.read()) if self._room_modes else set())
        for area in sorted(helper_areas):
            bedroom_mode = f"input_select.fht_{self._slug(area)}_mode"
            if (
                "*" not in configured_sleep_sources
                and bedroom_mode not in configured_sleep_sources
            ):
                continue
            state = str(
                (entities_by_id.get(bedroom_mode) or {}).get("state") or ""
            )
            if state.casefold() == "sleep":
                mode = "Sleep"
                break
        else:
            sun = entities_by_id.get("sun.sun")
            if sun is None:
                try:
                    sun = inventory.fetch_state("sun.sun")
                except HomeAssistantAPIError:
                    sun = {}
            solar_day = self.solar_day(sun)
            if solar_day is None:
                current_mode = str(
                    (entities_by_id.get(HOUSE_MODE_HELPER) or {}).get("state")
                    or ""
                ).title()
                mode = current_mode if current_mode in {"Day", "Night"} else "Night"
            else:
                mode = "Day" if solar_day else "Night"

        if self._publisher:
            self._publisher.climate_action(
                "set_option",
                HOUSE_MODE_HELPER,
                mode,
            )
        return mode

    @staticmethod
    def _offset_string(offset: int) -> str:
        sign = "-" if offset < 0 else ""
        hours, minutes = divmod(abs(offset), 60)
        return f"{sign}{hours:02d}:{minutes:02d}:00"

class WakeRoutineAutomationManager:
    """Generate native helpers and automations for room wake routines."""

    def __init__(
        self,
        path: Path,
        publisher: HomeAssistantHelperPublisher | None = None,
    ) -> None:
        self._path = path
        self._publisher = publisher

    @staticmethod
    def _slug(area: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", area.casefold()).strip("_")

    @classmethod
    def override_button(cls, area: str) -> str:
        return f"input_button.fht_{cls._slug(area)}_wake_override"

    ROOM_MODE_OPTIONS = tuple(
        label for _mode, label in RoomModeSettings.AVAILABLE_MODES
    )

    def sync(
        self,
        settings: dict[str, dict[str, Any]],
        entities: list[dict[str, Any]],
        reload_managed: bool = True,
    ) -> list[dict[str, str]]:
        """Write wake helpers and automations and reload Home Assistant."""
        valid_entities = {
            str(entity.get("entity_id") or "")
            for entity in entities
            if isinstance(entity, dict)
        }
        normalized: dict[str, dict[str, Any]] = {}
        for area, value in settings.items():
            try:
                normalized[area] = WakeRoutineSettings.normalize(value, valid_entities)
            except ValueError:
                # Targets were checked when the routine was saved. A device that
                # was renamed, or whose integration has not loaded yet, must not
                # stop this room or any other generated package from activating.
                normalized[area] = WakeRoutineSettings.normalize(value)
                missing = sorted(
                    entity_id
                    for entity_id in (
                        *normalized[area]["target_entities"],
                        *(
                            entity_id
                            for action in normalized[area]["actions"]
                            if action["type"] == "audio"
                            for entity_id in action["entities"]
                        ),
                    )
                    if entity_id not in valid_entities
                )
                print(
                    f"[Wake Routines] WARNING {area}: kept the saved routine, but "
                    "these devices are not available right now: "
                    + ", ".join(missing),
                    flush=True,
                )
        lines = ["# Managed by Future Homes Tech App. Changes may be overwritten.\n"]
        automations: list[dict[str, str]] = []
        if not normalized:
            lines.extend([
                "input_datetime: {}\n",
                "input_boolean: {}\n",
                "input_button: {}\n",
                "input_select: {}\n",
                "automation: []\n",
            ])
        else:
            lines.append("input_datetime:\n")
            for area in sorted(normalized):
                slug = self._slug(area)
                lines.extend([
                    f"  fht_{slug}_wake_override_at:\n",
                    f"    name: {json.dumps(f'{area} Wake Override Time')}\n",
                    "    has_date: true\n",
                    "    has_time: true\n",
                ])
            lines.append("input_boolean:\n")
            for area in sorted(normalized):
                slug = self._slug(area)
                lines.extend([
                    f"  fht_{slug}_wake_override_active:\n",
                    f"    name: {json.dumps(f'{area} Wake Override Active')}\n",
                    "    icon: mdi:alarm-check\n",
                ])
            lines.append("input_button:\n")
            for area in sorted(normalized):
                slug = self._slug(area)
                lines.extend([
                    f"  fht_{slug}_wake_override:\n",
                    f"    name: {json.dumps(f'{area} Wake Override')}\n",
                    "    icon: mdi:alarm-plus\n",
                ])
            generated_mode_helpers = sorted({
                str(action.get("entity_id") or "")
                for setting in normalized.values()
                for action in setting["actions"]
                if action["type"] == "room_mode"
                and str(action.get("entity_id") or "") not in valid_entities
            })
            if generated_mode_helpers:
                lines.append("input_select:\n")
                for helper in generated_mode_helpers:
                    helper_slug = helper.removeprefix("input_select.")
                    helper_name = helper_slug.removeprefix("fht_").removesuffix(
                        "_mode"
                    ).replace("_", " ").title()
                    lines.extend([
                        f"  {helper_slug}:\n",
                        f"    name: {json.dumps(f'Future Homes Tech {helper_name} Mode')}\n",
                        "    icon: mdi:home-switch\n",
                        "    options:\n",
                        *[
                            f"      - {json.dumps(option)}\n"
                            for option in self.ROOM_MODE_OPTIONS
                        ],
                    ])
            lines.append("automation:\n")
            for area, setting in sorted(normalized.items()):
                slug = self._slug(area)
                override_at = f"input_datetime.fht_{slug}_wake_override_at"
                override_active = f"input_boolean.fht_{slug}_wake_override_active"
                override_button = self.override_button(area)
                arm_id = f"fht_wake_{slug}_arm_override"
                run_id = f"fht_wake_{slug}_run"
                automations.extend([
                    {"id": arm_id, "area": area, "type": "Wake Override"},
                    {"id": run_id, "area": area, "type": "Wake Routine"},
                ])
                override_time = setting["override_time"]
                lines.extend([
                    f"  - id: {json.dumps(arm_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} Arm Next Wake Override')}\n",
                    "    mode: restart\n",
                    "    triggers:\n",
                    "      - trigger: state\n",
                    f"        entity_id: {override_button}\n",
                    "    actions:\n",
                    "      - action: input_datetime.set_datetime\n",
                    f"        target: {{entity_id: {override_at}}}\n",
                    "        data:\n",
                    "          datetime: >-\n",
                    f"            {{{{ (today_at('{override_time}') + timedelta(days=1 if now() >= today_at('{override_time}') else 0)).strftime('%Y-%m-%d %H:%M:%S') }}}}\n",
                    "      - action: input_boolean.turn_on\n",
                    f"        target: {{entity_id: {override_active}}}\n",
                    f"  - id: {json.dumps(run_id)}\n",
                    f"    alias: {json.dumps(f'FHT - {area} Wake Routine')}\n",
                    "    mode: single\n",
                    "    triggers:\n",
                    "      - trigger: time\n",
                    f"        at: {override_at}\n",
                    "        id: override\n",
                ])
                for day in WakeRoutineSettings.DAYS:
                    wake_time = setting["times"].get(day)
                    if wake_time:
                        lines.extend([
                            "      - trigger: time\n",
                            f"        at: {json.dumps(wake_time + ':00')}\n",
                            f"        id: {day}\n",
                        ])
                lines.extend([
                    "    conditions:\n",
                    "      - condition: template\n",
                    "        value_template: >-\n",
                    "          {{ (trigger.id == 'override' and is_state("
                    f"'{override_active}', 'on')) or ({str(setting['enabled']).lower()} and trigger.id != 'override' and is_state('{override_active}', 'off') and now().strftime('%A') | lower == trigger.id) }}}}\n",
                    "    actions:\n",
                ])
                for target in setting["target_entities"]:
                    domain = target.partition(".")[0]
                    lines.extend([
                        f"      - action: {domain}.turn_on\n",
                        f"        target: {{entity_id: {target}}}\n",
                    ])
                    if domain == "light":
                        lines.extend([
                            "        data:\n",
                            f"          brightness_pct: {setting['brightness_pct']}\n",
                        ])
                for action in setting["actions"]:
                    if action["type"] == "room_mode":
                        lines.extend([
                            "      - action: input_select.select_option\n",
                            f"        target: {{entity_id: {action['entity_id']}}}\n",
                            "        data:\n",
                            f"          option: {json.dumps(action['option'])}\n",
                        ])
                    elif (
                        action["type"] == "audio"
                        and action["entities"]
                        and action["media_content_id"]
                    ):
                        lines.extend([
                            "      - action: media_player.play_media\n",
                            "        target:\n",
                            "          entity_id:\n",
                            *[
                                f"            - {entity_id}\n"
                                for entity_id in action["entities"]
                            ],
                            "        data:\n",
                            f"          media_content_id: {json.dumps(action['media_content_id'])}\n",
                            f"          media_content_type: {json.dumps(action['media_content_type'])}\n",
                        ])
                lines.extend([
                    "      - if:\n",
                    "          - condition: trigger\n",
                    "            id: override\n",
                    "        then:\n",
                    "          - action: input_boolean.turn_off\n",
                    f"            target: {{entity_id: {override_active}}}\n",
                ])
        content = "".join(lines)
        try:
            with CONFIGURATION_ACTIVATION_LOCK:
                changed = atomic_write_text(self._path, content)
                if changed and reload_managed and self._publisher:
                    self._publisher.reload_domains(
                        (
                            "input_datetime",
                            "input_boolean",
                            "input_button",
                            "input_select",
                            "automation",
                        )
                    )
        except OSError as err:
            raise HomeAssistantAPIError(
                f"Unable to write wake routine automations: {err}"
            ) from err
        return automations


def integrations_from_registry_result(
    result: Any,
) -> dict[str, str]:
    """Extract entity-to-integration mappings from registry display data."""
    if not isinstance(result, dict):
        return {}
    entries = result.get("entities")
    if not isinstance(entries, list):
        return {}

    integrations: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entity_id = _clean_value(entry.get("ei"))
        integration = _clean_value(entry.get("pl"))
        if entity_id and integration:
            integrations[entity_id] = integration
    return integrations


def fetch_entity_integrations(
    token: str,
    websocket_url: str,
) -> dict[str, str]:
    """Fetch entity integration sources from Home Assistant."""
    connection: socket.socket | None = None
    try:
        connection, buffered = _open_websocket(websocket_url)
        auth_required = _receive_websocket_json(
            connection,
            buffered,
        )
        if auth_required.get("type") != "auth_required":
            raise WebSocketProtocolError(
                "Home Assistant did not request WebSocket authentication."
            )

        _send_websocket_json(
            connection,
            {"type": "auth", "access_token": token},
        )
        auth_result = _receive_websocket_json(
            connection,
            buffered,
        )
        if auth_result.get("type") != "auth_ok":
            raise WebSocketProtocolError(
                "Home Assistant rejected WebSocket authentication."
            )

        request_id = 1
        _send_websocket_json(
            connection,
            {
                "id": request_id,
                "type": "config/entity_registry/list_for_display",
            },
        )
        while True:
            response = _receive_websocket_json(
                connection,
                buffered,
            )
            if response.get("id") != request_id:
                continue
            if (
                response.get("type") != "result"
                or response.get("success") is not True
            ):
                raise WebSocketProtocolError(
                    "Home Assistant rejected the entity registry request."
                )
            return integrations_from_registry_result(
                response.get("result")
            )
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
        WebSocketProtocolError,
    ) as err:
        raise HomeAssistantAPIError(
            "Unable to read entity integrations from Home Assistant."
        ) from err
    finally:
        if connection is not None:
            try:
                _send_websocket_frame(connection, 0x8, b"")
            except OSError:
                pass
            connection.close()


class HomeAssistantRegistryOrganizer:
    """Organize App-managed entities in Home Assistant registries."""

    def __init__(self, token: str, websocket_url: str) -> None:
        """Initialize the registry organizer."""
        self._token = token
        self._websocket_url = websocket_url

    def _commands(
        self,
        commands: list[dict[str, Any]],
    ) -> list[Any]:
        """Execute registry commands."""
        return execute_websocket_commands(
            self._token,
            self._websocket_url,
            commands,
        )

    def _helper_category_id(
        self,
        name: str,
        icon: str,
        legacy_names: tuple[str, ...] = (),
    ) -> str:
        """Create, reuse, or rename a native Helpers category."""
        categories_result = self._commands(
            [
                {
                    "type": "config/category_registry/list",
                    "scope": LIGHT_GROUP_CATEGORY_SCOPE,
                }
            ]
        )[0]
        categories = (
            categories_result
            if isinstance(categories_result, list)
            else []
        )
        legacy_category_id: str | None = None
        for category in categories:
            if not isinstance(category, dict):
                continue
            category_name = str(category.get("name") or "")
            category_id = _clean_value(category.get("category_id"))
            if category_name.casefold() == name.casefold() and category_id:
                return category_id
            if category_name.casefold() in {
                legacy_name.casefold() for legacy_name in legacy_names
            } and category_id:
                legacy_category_id = category_id

        if legacy_category_id:
            update = {
                "type": "config/category_registry/update",
                "category_id": legacy_category_id,
                "name": name,
                "icon": icon,
            }
            try:
                self._commands([update])
            except HomeAssistantAPIError:
                update.pop("icon")
                try:
                    self._commands([update])
                except HomeAssistantAPIError:
                    legacy_category_id = None
            if legacy_category_id:
                return legacy_category_id

        created = self._commands(
            [
                {
                    "type": "config/category_registry/create",
                    "scope": LIGHT_GROUP_CATEGORY_SCOPE,
                    "name": name,
                    "icon": icon,
                }
            ]
        )[0]
        if not isinstance(created, dict):
            raise HomeAssistantAPIError(
                f"Home Assistant did not create {name}."
            )
        category_id = _clean_value(created.get("category_id"))
        if not category_id:
            raise HomeAssistantAPIError(
                f"Home Assistant returned no {name} category ID."
            )
        return category_id

    def _light_group_category_id(self) -> str:
        """Create or reuse the native Light Groups Helpers category."""
        return self._helper_category_id(
            LIGHT_GROUP_CATEGORY_NAME,
            LIGHT_GROUP_CATEGORY_ICON,
            LEGACY_LIGHT_GROUP_CATEGORY_NAMES,
        )

    def _climate_category_id(self) -> str:
        """Create or reuse the native Climate Helpers category."""
        return self._helper_category_id(
            CLIMATE_CATEGORY_NAME,
            CLIMATE_CATEGORY_ICON,
        )

    def _door_timer_category_id(self) -> str:
        """Create or reuse the native Door Timers Helpers category."""
        return self._helper_category_id(
            DOOR_TIMER_CATEGORY_NAME,
            DOOR_TIMER_CATEGORY_ICON,
        )

    def _automation_category_id(
        self,
        name: str = AUTOMATION_CATEGORY_NAME,
    ) -> str:
        """Create or reuse a native Automations category."""
        categories_result = self._commands(
            [
                {
                    "type": "config/category_registry/list",
                    "scope": AUTOMATION_CATEGORY_SCOPE,
                }
            ]
        )[0]
        categories = (
            categories_result
            if isinstance(categories_result, list)
            else []
        )
        for category in categories:
            if not isinstance(category, dict):
                continue
            if (
                str(category.get("name") or "").casefold()
                == name.casefold()
            ):
                category_id = _clean_value(category.get("category_id"))
                if category_id:
                    return category_id

        created = self._commands(
            [
                {
                    "type": "config/category_registry/create",
                    "scope": AUTOMATION_CATEGORY_SCOPE,
                    "name": name,
                    "icon": AUTOMATION_CATEGORY_ICON,
                }
            ]
        )[0]
        if not isinstance(created, dict):
            raise HomeAssistantAPIError(
                f"Home Assistant did not create the {name} category."
            )
        category_id = _clean_value(created.get("category_id"))
        if not category_id:
            raise HomeAssistantAPIError(
                f"Home Assistant returned no {name} category ID."
            )
        return category_id

    def categorize_light_groups(
        self,
        attempts: int = 10,
        retry_delay: float = 2,
        expected_entity_ids: set[str] | None = None,
    ) -> int:
        """Assign generated light groups to the Helpers category."""
        category_id = self._light_group_category_id()
        if expected_entity_ids is None:
            expected_entity_ids = generated_light_group_entity_ids()
        expected_unique_ids = (
            None
            if expected_entity_ids is None
            else {entity_id.removeprefix("light.") for entity_id in expected_entity_ids}
        )
        managed_entities: list[dict[str, Any]] = []

        entities_result: Any = None
        for attempt in range(max(attempts, 1)):
            entities_result = self._commands(
                [{"type": "config/entity_registry/list"}]
            )[0]
            if isinstance(entities_result, list):
                # Match by unique ID so a renamed group is kept and an old
                # group with a different entity ID is still found.
                managed_entities = [
                    entity
                    for entity in entities_result
                    if isinstance(entity, dict)
                    and str(entity.get("entity_id") or "").startswith("light.")
                    and str(entity.get("unique_id") or "").startswith(
                        LIGHT_GROUP_UNIQUE_ID_PREFIX
                    )
                    and entity.get("platform") == "group"
                ]
            managed_unique_ids = {
                str(entity.get("unique_id") or "")
                for entity in managed_entities
            }
            registry_ready = (
                bool(managed_entities)
                if expected_unique_ids is None
                else expected_unique_ids.issubset(managed_unique_ids)
            )
            if registry_ready or attempt + 1 >= max(attempts, 1):
                break
            time.sleep(retry_delay)

        active_entities = [
            entity
            for entity in managed_entities
            if (
                expected_unique_ids is None
                or entity.get("unique_id") in expected_unique_ids
            )
        ]
        updates = [
            {
                "type": "config/entity_registry/update",
                "entity_id": entity["entity_id"],
                "categories": {
                    LIGHT_GROUP_CATEGORY_SCOPE: category_id,
                },
            }
            for entity in active_entities
            if (
                not isinstance(entity.get("categories"), dict)
                or entity["categories"].get(
                    LIGHT_GROUP_CATEGORY_SCOPE
                )
                != category_id
            )
        ]
        removals = (
            []
            if expected_entity_ids is None
            else [
                {
                    "type": "config/entity_registry/remove",
                    "entity_id": entity["entity_id"],
                }
                for entity in managed_entities
                if entity.get("unique_id") not in expected_unique_ids
            ]
        )
        presence_group_entities = [
            entity
            for entity in (entities_result if isinstance(entities_result, list) else [])
            if isinstance(entity, dict)
            and entity.get("platform") == "template"
            and str(entity.get("entity_id") or "").startswith("binary_sensor.")
            and str(entity.get("unique_id") or "").startswith("fht_presence_group_")
        ]
        updates.extend(
            {
                "type": "config/entity_registry/update",
                "entity_id": entity["entity_id"],
                "categories": {LIGHT_GROUP_CATEGORY_SCOPE: category_id},
            }
            for entity in presence_group_entities
            if not isinstance(entity.get("categories"), dict)
            or entity["categories"].get(LIGHT_GROUP_CATEGORY_SCOPE) != category_id
        )
        if updates or removals:
            self._commands(updates + removals)
        return len(active_entities) + len(presence_group_entities)

    def normalize_group_entity_ids(
        self, presence_group_ids: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Give every App group its fht_ entity ID; return old → new IDs.

        Home Assistant keeps an entity's first ID when its name changes, so
        groups created under older names can lack the fht_ prefix.
        """
        registry = self._commands([{"type": "config/entity_registry/list"}])[0]
        if not isinstance(registry, list):
            return {}
        taken = {str(entry.get("entity_id")) for entry in registry if isinstance(entry, dict)}
        renames: dict[str, str] = {}
        for entry in registry:
            if not isinstance(entry, dict) or entry.get("config_entry_id"):
                continue
            entity_id = str(entry.get("entity_id") or "")
            unique_id = str(entry.get("unique_id") or "")
            if entry.get("platform") == "group" and entity_id.startswith("light.") and unique_id.startswith(LIGHT_GROUP_UNIQUE_ID_PREFIX):
                desired = f"light.{unique_id}"
            elif entry.get("platform") == "template" and entity_id.startswith("binary_sensor.") and unique_id in (presence_group_ids or {}):
                desired = presence_group_ids[unique_id]
            else:
                continue
            if desired == entity_id or desired in taken or not re.fullmatch(r"[a-z_]+\.fht_[a-z0-9_]+", desired):
                continue
            renames[entity_id] = desired
            taken.add(desired)
        if renames:
            self._commands([
                {"type": "config/entity_registry/update", "entity_id": old, "new_entity_id": new}
                for old, new in renames.items()
            ])
        return renames

    def cleanup_retired_managed_entities(
        self, entities: list[dict[str, Any]], config_directory: Path,
        approved: set[str] | None = None,
    ) -> list[str]:
        """Remove retired App entities; only ``approved`` ones when given."""
        retired = [
            str(entry["entity_id"])
            for entry in self.find_retired_managed_entities(entities, config_directory)
            if approved is None or entry["entity_id"] in approved
        ]
        if retired:
            self._commands([
                {"type": "config/entity_registry/remove", "entity_id": entity_id}
                for entity_id in retired
            ])
        return retired

    def find_retired_managed_entities(
        self, entities: list[dict[str, Any]], config_directory: Path,
    ) -> list[dict[str, Any]]:
        """Return App-generated registry entries no configuration provides anymore.

        Only YAML entities with an App unique ID (fht_...) are considered, and
        only when Home Assistant reports them unavailable and no configuration
        file still contains their unique ID.
        """
        registry = self._commands([{"type": "config/entity_registry/list"}])[0]
        if not isinstance(registry, list):
            return []
        config_files = sorted(config_directory.glob("*.yaml"))
        config_files.extend(sorted((config_directory / "packages").glob("**/*.yaml")))
        try:
            # Comments do not provide entities (the light-group package lists
            # replaced groups in comments).
            configuration = "\n".join(
                line
                for path in config_files if path.is_file()
                for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            )
        except OSError:
            return []
        if not configuration.strip():
            return []
        states = {str(entity.get("entity_id")): entity.get("state") for entity in entities}
        return [
            entry
            for entry in registry
            if isinstance(entry, dict)
            and entry.get("entity_id")
            and (
                str(entry.get("unique_id") or "").startswith("fht_")
                # Early releases used the plain room group ID as unique ID.
                or (
                    entry.get("platform") == "group"
                    and re.fullmatch(r"light\.[a-z0-9_]+_lights?", str(entry["entity_id"]))
                    and str(entry.get("unique_id") or "") == str(entry["entity_id"]).removeprefix("light.")
                )
            )
            and entry.get("platform") in {"automation", "group", "template"}
            and not entry.get("config_entry_id")
            and states.get(str(entry["entity_id"])) in {None, "unavailable", "unknown"}
            and not re.search(
                r"(?<![A-Za-z0-9_])" + re.escape(str(entry["unique_id"])) + r"(?![A-Za-z0-9_])",
                configuration,
            )
        ]

    def cleanup_retired_fan_groups(
        self, expected_groups: set[str], entities: list[dict[str, Any]], config_directory: Path,
        settings_directory: Path,
    ) -> int:
        registry = self._commands([{"type": "config/entity_registry/list"}])[0]
        if not isinstance(registry, list):
            return 0
        by_id = {str(entry.get("entity_id")): entry for entry in registry if isinstance(entry, dict)}
        states = {str(entity.get("entity_id")): entity.get("state") for entity in entities}
        config_files = [config_directory / "configuration.yaml", config_directory / "automations.yaml"]
        config_files.extend((config_directory / "packages").glob("*.yaml"))
        config_files.extend(settings_directory.glob("*.json"))
        count = 0
        for preferred in sorted(expected_groups):
            if not preferred.startswith(LIGHT_GROUP_ENTITY_PREFIX) or not preferred.endswith("_fan_lights"):
                continue
            preferred_entry = by_id.get(preferred, {})
            if (preferred_entry.get("platform") != "group"
                    or preferred_entry.get("unique_id") != preferred.removeprefix("light.")
                    or states.get(preferred) in {None, "unavailable", "unknown"}):
                continue
            area = preferred.removeprefix(LIGHT_GROUP_ENTITY_PREFIX).removesuffix("_fan_lights")
            retired = f"light.{area}_fan_lights"
            entry = by_id.get(retired, {})
            if (entry.get("platform") != "group" or entry.get("unique_id") != retired.removeprefix("light.")
                    or entry.get("config_entry_id") or states.get(retired) not in {None, "unavailable", "unknown"}):
                continue
            try:
                if any(path.is_file() and retired in path.read_text(encoding="utf-8") for path in config_files):
                    continue
            except OSError:
                continue
            self._commands([{"type": "config/entity_registry/remove", "entity_id": retired}])
            count += 1
        return count

    @staticmethod
    def _is_climate_helper_entity_id(entity_id: str) -> bool:
        """Return whether an entity ID belongs to the managed Climate set."""
        domain, separator, object_id = entity_id.partition(".")
        if not separator or domain not in {
            "input_boolean",
            "input_datetime",
            "input_number",
            "input_select",
            "input_text",
        }:
            return False
        if not object_id.startswith("fht_"):
            return False

        if domain == "input_boolean":
            return object_id in {
                "fht_occupancy_mode",
                "fht_super_cool",
                "fht_super_cool_time_reduced_this_cycle",
                "fht_vacation_mode",
            } or object_id.startswith("fht_holiday_")
        if domain == "input_number":
            return (
                object_id.startswith("fht_delta_")
                or object_id.startswith("fht_super_cool_")
                or object_id.endswith("_target_cool")
                or object_id.endswith("_target_heat")
            )
        if domain in {"input_datetime", "input_select"}:
            return object_id.startswith("fht_on_peak_") or object_id.startswith(
                "fht_super_off_peak_"
            )
        return object_id == "fht_weather_entity"

    def categorize_climate_helpers(
        self,
        attempts: int = 10,
        retry_delay: float = 2,
    ) -> int:
        """Assign App-managed Climate helpers to their native category."""
        category_id = self._climate_category_id()
        managed_entities: list[dict[str, Any]] = []

        for attempt in range(max(attempts, 1)):
            entities_result = self._commands(
                [{"type": "config/entity_registry/list"}]
            )[0]
            if isinstance(entities_result, list):
                managed_entities = [
                    entity
                    for entity in entities_result
                    if isinstance(entity, dict)
                    and self._is_climate_helper_entity_id(
                        str(entity.get("entity_id") or "")
                    )
                ]
            if managed_entities or attempt + 1 >= max(attempts, 1):
                break
            time.sleep(retry_delay)

        updates = [
            {
                "type": "config/entity_registry/update",
                "entity_id": entity["entity_id"],
                "categories": {CLIMATE_CATEGORY_SCOPE: category_id},
            }
            for entity in managed_entities
            if (
                not isinstance(entity.get("categories"), dict)
                or entity["categories"].get(CLIMATE_CATEGORY_SCOPE)
                != category_id
            )
        ]
        if updates:
            self._commands(updates)
        return len(managed_entities)

    @staticmethod
    def _is_door_timer_helper_entity_id(entity_id: str) -> bool:
        """Return whether an entity is one of the managed door-time helpers."""
        domain, separator, object_id = entity_id.partition(".")
        return (
            bool(separator)
            and domain == "input_text"
            and object_id.endswith("_door_time")
        )

    def categorize_door_timer_helpers(
        self,
        attempts: int = 10,
        retry_delay: float = 2,
    ) -> int:
        """Assign door-time input-text helpers to their native category."""
        category_id = self._door_timer_category_id()
        managed_entities: list[dict[str, Any]] = []

        for attempt in range(max(attempts, 1)):
            entities_result = self._commands(
                [{"type": "config/entity_registry/list"}]
            )[0]
            if isinstance(entities_result, list):
                managed_entities = [
                    entity
                    for entity in entities_result
                    if isinstance(entity, dict)
                    and self._is_door_timer_helper_entity_id(
                        str(entity.get("entity_id") or "")
                    )
                ]
            if managed_entities or attempt + 1 >= max(attempts, 1):
                break
            time.sleep(retry_delay)

        updates = [
            {
                "type": "config/entity_registry/update",
                "entity_id": entity["entity_id"],
                "categories": {LIGHT_GROUP_CATEGORY_SCOPE: category_id},
            }
            for entity in managed_entities
            if (
                not isinstance(entity.get("categories"), dict)
                or entity["categories"].get(LIGHT_GROUP_CATEGORY_SCOPE)
                != category_id
            )
        ]
        if updates:
            self._commands(updates)
        return len(managed_entities)

    @staticmethod
    def _is_fht_ungrouped_helper(entity_id: str) -> bool:
        """Return whether an entity is an App-managed helper outside known groups."""
        domain, separator, object_id = entity_id.partition(".")
        if not separator or domain not in {
            "input_boolean",
            "input_datetime",
            "input_number",
            "input_select",
            "input_text",
            "timer",
        }:
            return False
        return object_id.startswith("fht_") or object_id.startswith(
            "future_homes_tech_"
        )

    def categorize_ungrouped_helpers(
        self,
        attempts: int = 10,
        retry_delay: float = 2,
    ) -> int:
        """Assign remaining App-managed helpers to the Ungrouped category."""
        category_id = self._helper_category_id(
            UNGROUPED_HELPER_CATEGORY_NAME,
            "mdi:help-circle-outline",
        )
        light_group_ids = generated_light_group_entity_ids() or set()
        managed_entities: list[dict[str, Any]] = []
        for attempt in range(max(attempts, 1)):
            entities_result = self._commands(
                [{"type": "config/entity_registry/list"}]
            )[0]
            if isinstance(entities_result, list):
                managed_entities = [
                    entity
                    for entity in entities_result
                    if isinstance(entity, dict)
                    and str(entity.get("entity_id") or "") not in light_group_ids
                    and self._is_fht_ungrouped_helper(
                        str(entity.get("entity_id") or "")
                    )
                    and not self._is_climate_helper_entity_id(
                        str(entity.get("entity_id") or "")
                    )
                    and not self._is_door_timer_helper_entity_id(
                        str(entity.get("entity_id") or "")
                    )
                ]
            if managed_entities or attempt + 1 >= max(attempts, 1):
                break
            time.sleep(retry_delay)
        updates = [
            {
                "type": "config/entity_registry/update",
                "entity_id": entity["entity_id"],
                "categories": {LIGHT_GROUP_CATEGORY_SCOPE: category_id},
            }
            for entity in managed_entities
            if (
                not isinstance(entity.get("categories"), dict)
                or entity["categories"].get(LIGHT_GROUP_CATEGORY_SCOPE)
                != category_id
            )
        ]
        if updates:
            self._commands(updates)
        return len(managed_entities)

    def categorize_automations(
        self,
        attempts: int = 10,
        retry_delay: float = 2,
    ) -> int:
        """Assign every App-managed automation to its native category."""
        managed_entities: list[dict[str, Any]] = []

        for attempt in range(max(attempts, 1)):
            entities_result = self._commands(
                [{"type": "config/entity_registry/list"}]
            )[0]
            if isinstance(entities_result, list):
                managed_entities = [
                    entity
                    for entity in entities_result
                    if isinstance(entity, dict)
                    and str(entity.get("entity_id") or "").startswith(
                        "automation."
                    )
                    and (
                        str(entity.get("unique_id") or "").startswith(
                            CONTROL_AUTOMATION_UNIQUE_ID_PREFIX
                        )
                        or str(entity.get("unique_id") or "").startswith(
                            DOOR_AUTOMATION_UNIQUE_ID_PREFIX
                        )
                        or str(entity.get("unique_id") or "").startswith(
                            PRESENCE_AUTOMATION_UNIQUE_ID_PREFIX
                        )
                        or str(entity.get("unique_id") or "").startswith(
                            LIGHT_SCHEDULE_AUTOMATION_UNIQUE_ID_PREFIX
                        )
                        or str(entity.get("unique_id") or "").startswith(
                            FRIDGE_ALARM_AUTOMATION_UNIQUE_ID_PREFIX
                        )
                        or str(entity.get("unique_id") or "").startswith(
                            ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX
                        )
                        or str(entity.get("unique_id") or "").startswith(
                            CLIMATE_AUTOMATION_UNIQUE_ID_PREFIXES
                        )
                        or str(entity.get("unique_id") or "")
                        == ENTRY_DELAY_AUTOMATION_UNIQUE_ID
                    )
                ]
            if managed_entities or attempt + 1 >= max(attempts, 1):
                break
            time.sleep(retry_delay)

        category_names = {
            "door": DOOR_AUTOMATION_CATEGORY_NAME,
            "switch": SWITCH_AUTOMATION_CATEGORY_NAME,
            "switch_activation": SWITCH_ACTIVATION_CATEGORY_NAME,
            "light_sync": LIGHT_SYNC_CATEGORY_NAME,
            "climate": CLIMATE_AUTOMATION_CATEGORY_NAME,
            "presence": PRESENCE_AUTOMATION_CATEGORY_NAME,
            "motion": MOTION_AUTOMATION_CATEGORY_NAME,
            "scene": SCENE_AUTOMATION_CATEGORY_NAME,
            "device_alarm": DEVICE_ALARM_AUTOMATION_CATEGORY_NAME,
        }
        category_ids = {
            key: self._automation_category_id(name)
            for key, name in category_names.items()
        }

        def automation_category(unique_id: str) -> str | None:
            if unique_id.startswith(DOOR_OPEN_ALERT_AUTOMATION_UNIQUE_ID_PREFIX):
                return "device_alarm"
            if unique_id == ENTRY_DELAY_AUTOMATION_UNIQUE_ID or unique_id.startswith(DOOR_AUTOMATION_UNIQUE_ID_PREFIX):
                return "door"
            if unique_id.startswith(PRESENCE_AUTOMATION_UNIQUE_ID_PREFIX):
                return "presence"
            if unique_id.startswith("fht_motion_"):
                return "motion"
            if unique_id.startswith(LIGHT_SCHEDULE_AUTOMATION_UNIQUE_ID_PREFIX):
                return "scene"
            if unique_id.startswith(FRIDGE_ALARM_AUTOMATION_UNIQUE_ID_PREFIX):
                return "device_alarm"
            if unique_id.startswith(ROOM_MODE_AUTOMATION_UNIQUE_ID_PREFIX):
                return "scene"
            if unique_id.startswith(CLIMATE_AUTOMATION_UNIQUE_ID_PREFIXES):
                return "climate"
            if unique_id.startswith("fht_control_sync_"):
                return "light_sync"
            if unique_id.startswith(CONTROL_AUTOMATION_UNIQUE_ID_PREFIX):
                return "switch_activation"
            return None

        updates = []
        for entity in managed_entities:
            category_key = automation_category(
                str(entity.get("unique_id") or "")
            )
            if category_key is None:
                continue
            category_id = category_ids[category_key]
            if (
                not isinstance(entity.get("categories"), dict)
                or entity["categories"].get(AUTOMATION_CATEGORY_SCOPE)
                != category_id
            ):
                updates.append(
                    {
                        "type": "config/entity_registry/update",
                        "entity_id": entity["entity_id"],
                        "categories": {
                            AUTOMATION_CATEGORY_SCOPE: category_id,
                        },
                    }
                )
        if updates:
            self._commands(updates)
        return len(managed_entities)


def generated_light_group_entity_ids(
    package_path: Path = GENERATED_LIGHT_GROUP_PACKAGE,
) -> set[str] | None:
    """Read expected managed entity IDs from the generated package."""
    try:
        content = package_path.read_text(encoding="utf-8")
    except OSError:
        return None
    unique_ids = re.findall(
        r"^\s+unique_id:\s+(fht_[a-z0-9_]+)\s*$",
        content,
        flags=re.MULTILINE,
    )
    return {f"light.{unique_id}" for unique_id in unique_ids}


def generated_light_group_replacements(
    package_path: Path = GENERATED_LIGHT_GROUP_PACKAGE,
) -> dict[str, list[str]]:
    """Read groups the generator dropped in favor of a room's only group.

    Each retired group maps to that group first, then any room lights
    outside it, so saved actions keep controlling the same lights.
    """
    try:
        content = package_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {
        retired: [target.strip() for target in targets.split(",") if target.strip()]
        for retired, targets in re.findall(
            r"^# fht_replaced_group: (light\.fht_[a-z0-9_]+) -> ([a-z0-9_., ]+)$",
            content,
            flags=re.MULTILINE,
        )
    }


def lighting_entity_ids(
    package_path: Path = GENERATED_LIGHT_GROUP_PACKAGE,
) -> set[str] | None:
    """Return the generated groups and standalone lights Lighting shows.

    None when there is no generated package, so every App group shows.
    """
    try:
        content = package_path.read_text(encoding="utf-8")
    except OSError:
        return None
    unique_ids = re.findall(r"^\s+unique_id:\s+(fht_[a-z0-9_]+)\s*$", content, flags=re.MULTILINE)
    standalone = re.findall(r"^# fht_standalone_light: (light\.[a-z0-9_]+)$", content, flags=re.MULTILINE)
    return {f"light.{unique_id}" for unique_id in unique_ids} | set(standalone)


def replace_entity_ids_in_settings(settings_directory: Path, replacements: dict[str, list[str]]) -> int:
    """Swap retired entity IDs in saved App settings; return files changed.

    In lists, a retired ID expands to all of its replacements; a single value
    takes the first one. Action values like "light_group:<id>" keep their
    prefix.
    """
    if not replacements:
        return 0

    def expand(value: Any) -> list[Any]:
        if not isinstance(value, str):
            return [value]
        prefix, separator, entity_id = value.rpartition(":")
        key = entity_id if separator else value
        if key not in replacements:
            return [value]
        return [f"{prefix}{separator}{target}" for target in replacements[key]]

    def walk(value: Any) -> Any:
        if isinstance(value, list):
            if all(isinstance(item, str) for item in value):
                return list(dict.fromkeys(target for item in value for target in expand(item)))
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return expand(value)[0]

    changed = 0
    for path in sorted(settings_directory.glob("**/*.json")):
        if "beta" in path.relative_to(settings_directory).parts:
            continue
        try:
            original = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        updated = walk(original)
        if updated == original:
            continue
        try:
            atomic_write_json(path, updated)
        except OSError as err:
            print(f"[Groups] WARNING Unable to update {path.name}: {err}", flush=True)
            continue
        changed += 1
    return changed


def _clean_value(value: Any) -> str | None:
    """Normalize optional entity metadata for display."""
    if value is None:
        return None
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def normalize_entities(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a stable, compact inventory from Home Assistant state objects."""
    entities: list[dict[str, Any]] = []

    for state_object in states:
        entity_id = _clean_value(state_object.get("entity_id"))
        if not entity_id:
            continue

        attributes = state_object.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        entities.append(
            {
                "entity_id": entity_id,
                "friendly_name": _clean_value(
                    attributes.get("friendly_name")
                ),
                "domain": entity_id.partition(".")[0],
                "state": _clean_value(state_object.get("state")),
                "device_class": _clean_value(
                    attributes.get("device_class")
                ),
                "unit_of_measurement": _clean_value(
                    attributes.get("unit_of_measurement")
                ),
                "area": _clean_value(attributes.get("fht_area")),
                "members": sorted(
                    member
                    for member in attributes.get("entity_id", [])
                    if isinstance(member, str)
                )
                if isinstance(attributes.get("entity_id"), list)
                else [],
                "event_types": sorted(
                    event_type
                    for event_type in attributes.get("event_types", [])
                    if isinstance(event_type, str)
                )
                if isinstance(attributes.get("event_types"), list)
                else [],
                "last_changed": _clean_value(
                    state_object.get("last_changed")
                ),
                "last_updated": _clean_value(
                    state_object.get("last_updated")
                ),
                "restored": attributes.get("restored") is True,
                "installed_version": _clean_value(attributes.get("installed_version")),
                "latest_version": _clean_value(attributes.get("latest_version")),
                "in_progress": attributes.get("in_progress", False),
                "update_percentage": attributes.get("update_percentage"),
                "last_triggered": _clean_value(attributes.get("last_triggered")),
                "event_type": _clean_value(attributes.get("event_type")),
                "current_temperature": attributes.get("current_temperature"),
                "temperature": attributes.get("temperature"),
                "brightness": attributes.get("brightness"),
                "supported_color_modes": attributes.get("supported_color_modes", []),
                "hvac_modes": attributes.get("hvac_modes", []),
                "options": attributes.get("options", []),
                "minimum": attributes.get("min"),
                "maximum": attributes.get("max"),
                "step": attributes.get("step"),
                "next_rising": _clean_value(attributes.get("next_rising")),
                "next_setting": _clean_value(attributes.get("next_setting")),
            }
        )

    return sorted(entities, key=lambda entity: entity["entity_id"])


def is_door_sensor_entity(entity: dict[str, Any]) -> bool:
    """Return whether an entity is an actual door/window contact sensor."""
    if str(entity.get("domain") or "").casefold() != "binary_sensor":
        return False
    device_class = str(entity.get("device_class") or "").casefold()
    searchable_name = " ".join(
        str(entity.get(key) or "")
        for key in ("friendly_name", "entity_id")
    ).replace("_", " ").casefold()
    if device_class in {"battery", "moisture", "problem", "tamper"}:
        return False
    if any(
        word in searchable_name
        for word in ("battery", "detected", "detection", "doorbell", "moisture", "tamper")
    ):
        return False
    return (
        device_class in {"door", "garage_door", "opening", "window"}
        or "door sensor" in searchable_name
        or "window sensor" in searchable_name
    )


def fridge_alarm_sensor_kind(entity: dict[str, Any]) -> str:
    """Return the supported refrigerator alarm sensor type."""
    domain = str(entity.get("domain") or "").casefold()
    device_class = str(entity.get("device_class") or "").casefold()
    unit = str(entity.get("unit_of_measurement") or "").strip().casefold()
    if domain == "sensor" and (
        device_class == "temperature"
        or unit in {"°c", "°f", "c", "f"}
    ):
        return "temperature"
    if domain == "binary_sensor" and is_door_sensor_entity(entity):
        return "door"
    return ""


def is_refrigerator_entity(entity: dict[str, Any]) -> bool:
    """Return whether an entity belongs to a fridge or freezer by name or room."""
    searchable = " ".join(
        str(entity.get(key) or "")
        for key in ("area", "device_name", "friendly_name", "entity_id")
    ).replace("_", " ").casefold()
    return any(label in searchable for label in ("fridge", "refrigerator", "freezer"))


def door_open_alert_display_name(entity: dict[str, Any]) -> str:
    """Return a door or window name without trailing sensor words."""
    entity_id = str(entity.get("entity_id") or "").strip()
    friendly_name = re.sub(
        r"^FHT\s*-\s*", "", str(entity.get("friendly_name") or "").strip(), flags=re.IGNORECASE
    )
    fallback = entity_id.partition(".")[2].replace("_", " ").strip().title()
    trimmed = re.sub(
        r"(?:\s+(?:contact|sensor|opening|open))+\s*$",
        "",
        friendly_name,
        flags=re.IGNORECASE,
    ).strip()
    return trimmed or friendly_name or fallback or entity_id


def is_device_alarm_room_name(name: Any) -> bool:
    """Return whether a room name is a supported Device Alarms alias."""
    return str(name or "").strip().casefold() in DEVICE_ALARM_ROOM_NAMES


def fridge_alarm_output_kind(entity: dict[str, Any]) -> str:
    """Return the supported audible alarm output type."""
    entity_id = str(entity.get("entity_id") or "").strip()
    searchable = " ".join(
        str(entity.get(key) or "")
        for key in ("friendly_name", "entity_id")
    ).replace("_", " ").casefold()
    if entity_id.startswith("siren."):
        return "siren"
    if entity_id.startswith("button.") and re.search(
        r"\bplay\s+(?:the\s+)?(?:siren|buzzer|chime)\b",
        searchable,
    ):
        return "button"
    return ""


def fridge_alarm_output_catalog(
    entities: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Return friendly siren and chime targets for Device Alarms."""
    outputs: dict[str, list[dict[str, str]]] = {"sirens": [], "chimes": []}
    seen: set[str] = set()
    for entity in entities:
        entity_id = str(entity.get("entity_id") or "").strip()
        kind = fridge_alarm_output_kind(entity)
        if not entity_id or not kind or entity_id in seen:
            continue
        seen.add(entity_id)
        action_name = " ".join(
            str(entity.get(key) or "")
            for key in ("friendly_name", "entity_id")
        ).replace("_", " ").casefold()
        if kind == "button" and not re.search(r"\bplay\s+(?:the\s+)?(?:buzzer|siren)\b", action_name):
            continue
        group = (
            "sirens"
            if kind == "siren" or re.search(r"\bplay\s+(?:the\s+)?siren\b", action_name)
            else "chimes"
        )
        outputs[group].append(
            {
                "entity_id": entity_id,
                "name": re.sub(r"\s+play\s+(?:the\s+)?(?:buzzer|siren|chime)\s*$", "", str(
                    entity.get("friendly_name")
                    or entity.get("device_name")
                    or entity_id
                ).strip(), flags=re.IGNORECASE),
            }
        )
    for items in outputs.values():
        items.sort(key=lambda item: item["name"].casefold())
    return outputs


def device_alarm_buzzer_settings(settings: dict[str, dict[str, Any]], entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id = {entity.get("entity_id"): entity for entity in entities}
    result = {}
    for sensor_id, setting in settings.items():
        targets = []
        for target in setting.get("alert_targets", [setting["alert_target"]] if setting.get("alert_target") else []):
            replacement = re.sub(r"_play_chime$", "_play_buzzer", target)
            if replacement != target and replacement in by_id and fridge_alarm_output_kind(by_id[replacement]) == "button":
                target = replacement
            if target not in targets:
                targets.append(target)
        result[sensor_id] = {**setting, "alert_targets": targets}
    return result


def phone_notify_service_id(value: Any) -> str:
    """Return one Companion app notify service id, or an empty string."""
    candidate = str(value or "").strip().casefold()
    if re.fullmatch(r"notify\.mobile_app_[a-z0-9_]+", candidate):
        return candidate
    return ""


def phone_notify_targets(raw: Any) -> list[str]:
    """Return the validated, de-duplicated phones from one saved setting."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("Phone alerts must be a list of phones.")
    targets: list[str] = []
    for item in raw:
        service = phone_notify_service_id(item)
        if not service:
            raise ValueError(
                "Phone alerts must use phones signed in to the Home Assistant Companion app."
            )
        if service not in targets:
            targets.append(service)
    return targets


def phone_notify_slug(name: Any) -> str:
    """Return the service suffix Home Assistant derives from a phone's device name."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"['’]", "", text).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def phone_notify_catalog(
    services: list[str],
    entities: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return the phones that accept push notifications, named after their device."""
    device_names: dict[str, str] = {}
    for entity in entities:
        if str(entity.get("integration") or "") != "mobile_app":
            continue
        device_name = str(entity.get("device_name") or "").strip()
        if device_name:
            device_names.setdefault(phone_notify_slug(device_name), device_name)
    targets: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in services:
        service = phone_notify_service_id(raw)
        if not service or service in seen:
            continue
        seen.add(service)
        slug = service[len(PHONE_NOTIFY_SERVICE_PREFIX):]
        name = device_names.get(slug) or slug.replace("_", " ").strip().title()
        targets.append({"service": service, "name": name})
    targets.sort(key=lambda item: (item["name"].casefold(), item["service"]))
    return targets


def phone_notify_action_lines(
    targets: list[str],
    indent: str,
    title: str = "",
    message: str = "",
    tag: str = "",
    clear: bool = False,
) -> list[str]:
    """Return YAML actions that push (or clear) one notification per phone."""
    lines: list[str] = []
    for service in targets:
        lines.extend(
            [
                f"{indent}- action: {service}\n",
                f"{indent}  continue_on_error: true\n",
                f"{indent}  data:\n",
            ]
        )
        if clear:
            lines.append(f"{indent}    message: clear_notification\n")
        else:
            lines.extend(
                [
                    f"{indent}    title: {json.dumps(title)}\n",
                    f"{indent}    message: {json.dumps(message)}\n",
                ]
            )
        if tag:
            lines.extend(
                [
                    f"{indent}    data:\n",
                    f"{indent}      tag: {tag}\n",
                ]
            )
    return lines


class PhoneNotifyServices:
    """List the Companion app phones Home Assistant can push notifications to."""

    def __init__(
        self,
        token: str,
        services_url: str,
        cache_ttl: float = PHONE_NOTIFY_CACHE_TTL_SECONDS,
    ) -> None:
        self._token = token
        self._services_url = services_url.rstrip("/")
        self._cache_ttl = max(0.0, float(cache_ttl))
        self._cache_lock = threading.Lock()
        self._cache: list[str] | None = None
        self._cache_at = 0.0

    def fetch(self, force: bool = False) -> list[str]:
        """Return the notify.mobile_app_* services Home Assistant offers now."""
        if not self._token:
            raise HomeAssistantAPIError(
                "The Home Assistant API token is unavailable."
            )
        with self._cache_lock:
            if (
                not force
                and self._cache is not None
                and time.monotonic() - self._cache_at < self._cache_ttl
            ):
                return list(self._cache)
            request = Request(
                self._services_url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as err:
                raise HomeAssistantAPIError(
                    f"Home Assistant returned HTTP {err.code}."
                ) from err
            except (URLError, OSError, ValueError) as err:
                raise HomeAssistantAPIError(
                    "Unable to list phones from Home Assistant."
                ) from err
            services: list[str] = []
            for domain in payload if isinstance(payload, list) else []:
                if not isinstance(domain, dict) or domain.get("domain") != "notify":
                    continue
                names = domain.get("services")
                for name in names if isinstance(names, dict) else []:
                    service = phone_notify_service_id(f"notify.{name}")
                    if service and service not in services:
                        services.append(service)
            self._cache = sorted(services)
            self._cache_at = time.monotonic()
            return list(self._cache)

    def known(self) -> set[str] | None:
        """Return the current phone services, or None when Home Assistant cannot say."""
        try:
            return set(self.fetch())
        except HomeAssistantAPIError:
            return None

    def send(self, service: str, title: str, message: str) -> None:
        """Push one notification to a phone."""
        service = phone_notify_service_id(service)
        if not service:
            raise ValueError("A Companion app phone is required.")
        if not self._token:
            raise HomeAssistantAPIError(
                "The Home Assistant API token is unavailable."
            )
        request = Request(
            f"{self._services_url}/notify/{service.split('.', 1)[1]}",
            data=json.dumps({"title": title, "message": message}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10):
                pass
        except HTTPError as err:
            raise HomeAssistantAPIError(
                f"Home Assistant returned HTTP {err.code}."
            ) from err
        except (URLError, OSError) as err:
            raise HomeAssistantAPIError(
                "Unable to reach Home Assistant to send the notification."
            ) from err


def fridge_alarm_catalog(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group refrigerator temperature and door sensors by device."""
    devices: dict[str, dict[str, Any]] = {}
    for entity in entities:
        kind = fridge_alarm_sensor_kind(entity)
        if not kind:
            continue
        entity_id = str(entity.get("entity_id") or "").strip()
        friendly_name = str(entity.get("friendly_name") or entity_id).strip()
        device_name = str(entity.get("device_name") or "").strip()
        fallback_name = re.sub(
            r"\s+(?:door(?:\s+(?:contact\s+)?sensor)?(?:\s+opening)?|temperature(?:\s+sensor)?)\s*$",
            "",
            friendly_name,
            flags=re.IGNORECASE,
        ).strip()
        display_name = device_name or fallback_name or friendly_name or "Refrigerator"
        device_key = str(entity.get("device_id") or "").strip() or re.sub(
            r"[^a-z0-9]+",
            "_",
            display_name.casefold(),
        ).strip("_") or entity_id
        device = devices.setdefault(
            device_key,
            {
                "device_id": device_key,
                "name": display_name,
                "temperature_sensors": [],
                "door_sensors": [],
            },
        )
        sensor = {
            "entity_id": entity_id,
            "friendly_name": friendly_name,
            "state": entity.get("state"),
            "unit": entity.get("unit_of_measurement"),
        }
        device[f"{kind}_sensors"].append(sensor)
    for device in devices.values():
        device["temperature_sensors"].sort(
            key=lambda sensor: str(sensor["friendly_name"]).casefold()
        )
        device["door_sensors"].sort(
            key=lambda sensor: str(sensor["friendly_name"]).casefold()
        )
    return sorted(
        devices.values(),
        key=lambda device: str(device["name"]).casefold(),
    )


def entity_areas_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> dict[str, str]:
    """Map entity IDs to Area names using Home Assistant registries."""
    storage_directory = config_directory / ".storage"

    def load_values(filename: str, key: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(
                storage_directory.joinpath(filename).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError):
            return []
        values = payload.get("data", {}).get(key, [])
        return values if isinstance(values, list) else []

    areas = load_values("core.area_registry", "areas")
    devices = load_values("core.device_registry", "devices")
    entities = load_values("core.entity_registry", "entities")
    area_names = {
        str(area.get("area_id") or area.get("id")): str(area["name"])
        for area in areas
        if (area.get("area_id") or area.get("id")) and area.get("name")
    }
    device_areas = {
        str(device["id"]): str(device["area_id"])
        for device in devices
        if device.get("id") and device.get("area_id")
    }
    entity_areas: dict[str, str] = {}
    for entity in entities:
        entity_id = _clean_value(entity.get("entity_id"))
        if not entity_id:
            continue
        # An entity area overrides its device area, but an override that
        # points at a deleted area falls back to the device's area.
        area_name = area_names.get(str(entity.get("area_id") or "")) or area_names.get(
            device_areas.get(str(entity.get("device_id") or ""), "")
        )
        if area_name:
            entity_areas[entity_id] = area_name
    return entity_areas


def entity_floors_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> dict[str, str]:
    """Map entity IDs to their Home Assistant Floor names."""
    storage_directory = config_directory / ".storage"

    def load_values(filename: str, key: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(
                storage_directory.joinpath(filename).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError):
            return []
        values = payload.get("data", {}).get(key, [])
        return values if isinstance(values, list) else []

    floors = load_values("core.floor_registry", "floors")
    areas = load_values("core.area_registry", "areas")
    devices = load_values("core.device_registry", "devices")
    entities = load_values("core.entity_registry", "entities")
    floor_names = {
        str(floor.get("floor_id") or floor.get("id")): str(floor["name"])
        for floor in floors
        if (floor.get("floor_id") or floor.get("id")) and floor.get("name")
    }
    area_floors = {
        str(area.get("area_id") or area.get("id")): str(area["floor_id"])
        for area in areas
        if (area.get("area_id") or area.get("id")) and area.get("floor_id")
    }
    device_areas = {
        str(device["id"]): str(device["area_id"])
        for device in devices
        if device.get("id") and device.get("area_id")
    }
    entity_floors: dict[str, str] = {}
    for entity in entities:
        entity_id = _clean_value(entity.get("entity_id"))
        if not entity_id:
            continue
        area_id = entity.get("area_id") or device_areas.get(
            str(entity.get("device_id") or "")
        )
        floor_name = floor_names.get(area_floors.get(str(area_id or ""), ""))
        if floor_name:
            entity_floors[entity_id] = floor_name
    return entity_floors


def home_configurator_floor_sort_key(
    floor: dict[str, Any],
) -> tuple[bool, bool, bool, int, str]:
    """Keep Whole Home first, physical floors ordered, and Unassigned last."""
    name = str(floor.get("name") or "")
    level = floor.get("level")
    return (
        name.casefold() != "whole home",
        name.casefold() == "unassigned",
        level is None,
        level if isinstance(level, int) else 0,
        name.casefold(),
    )


def home_structure_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> dict[str, Any]:
    """Return every registered Floor and Area, including empty ones."""
    storage_directory = config_directory / ".storage"

    def load_values(filename: str, key: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(
                storage_directory.joinpath(filename).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError):
            return []
        values = payload.get("data", {}).get(key, [])
        if not isinstance(values, list):
            return []
        return [value for value in values if isinstance(value, dict)]

    floors = load_values("core.floor_registry", "floors")
    areas = load_values("core.area_registry", "areas")
    floor_entries: dict[str, dict[str, Any]] = {}
    for floor in floors:
        floor_id = str(floor.get("floor_id") or floor.get("id") or "")
        name = str(floor.get("name") or "").strip()
        if not floor_id or not name:
            continue
        floor_entries[floor_id] = {
            "floor_id": floor_id,
            "name": name,
            "level": floor.get("level"),
            "areas": [],
        }

    unassigned_areas: list[dict[str, str]] = []
    for area in areas:
        area_id = str(area.get("area_id") or area.get("id") or "")
        name = str(area.get("name") or "").strip()
        if not area_id or not name:
            continue
        area_entry = {"area_id": area_id, "name": name}
        floor_id = str(area.get("floor_id") or "")
        if floor_id in floor_entries:
            floor_entries[floor_id]["areas"].append(area_entry)
        else:
            unassigned_areas.append(area_entry)

    result = list(floor_entries.values())
    if unassigned_areas:
        result.append(
            {
                "floor_id": "",
                "name": "Unassigned",
                "level": None,
                "areas": unassigned_areas,
            }
        )
    for floor in result:
        floor["areas"].sort(key=lambda area: area["name"].casefold())
    result.sort(key=home_configurator_floor_sort_key)
    return {
        "floors": result,
        "floor_count": len(result),
        "area_count": sum(len(floor["areas"]) for floor in result),
    }


def entity_devices_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> dict[str, str]:
    """Map entity IDs to their Home Assistant device display names."""
    storage_directory = config_directory / ".storage"
    try:
        entity_payload = json.loads(
            storage_directory.joinpath("core.entity_registry").read_text(
                encoding="utf-8"
            )
        )
        device_payload = json.loads(
            storage_directory.joinpath("core.device_registry").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return {}
    devices = device_payload.get("data", {}).get("devices", [])
    entities = entity_payload.get("data", {}).get("entities", [])
    device_names = {
        str(device.get("id")): str(
            device.get("name_by_user") or device.get("name") or ""
        )
        for device in devices
        if isinstance(device, dict) and device.get("id")
    }
    return {
        str(entity.get("entity_id")): device_names.get(
            str(entity.get("device_id") or ""),
            "",
        )
        for entity in entities
        if isinstance(entity, dict) and entity.get("entity_id")
    }


def entity_control_metadata_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> dict[str, dict[str, Any]]:
    """Return stable registry metadata used to identify renamed channels."""
    try:
        payload = json.loads(
            config_directory.joinpath(".storage/core.entity_registry").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return {}
    entities = payload.get("data", {}).get("entities", [])
    metadata = {
        str(entity.get("entity_id")): {
            "device_id": str(entity.get("device_id") or ""),
            "original_name": str(entity.get("original_name") or ""),
        }
        for entity in entities
        if isinstance(entity, dict) and entity.get("entity_id")
    }
    try:
        devices = json.loads(config_directory.joinpath(".storage/core.device_registry").read_text(encoding="utf-8")).get("data", {}).get("devices", [])
        manufacturers = {device.get("id"): device.get("manufacturer", "") for device in devices}
        for entity_metadata in metadata.values():
            entity_metadata["manufacturer"] = manufacturers.get(entity_metadata["device_id"], "")
    except (OSError, ValueError):
        pass
    try:
        entries = json.loads(config_directory.joinpath(".storage/core.config_entries").read_text(encoding="utf-8")).get("data", {}).get("entries", [])
    except (OSError, ValueError):
        return metadata
    by_id = {str(entity.get("entity_id")): entity for entity in entities if isinstance(entity, dict)}
    by_uuid = {str(entity.get("id")): str(entity.get("entity_id")) for entity in entities if isinstance(entity, dict) and entity.get("id")}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("domain") != "switch_as_x" or entry.get("disabled_by") or not entry.get("entry_id"):
            continue
        options = entry.get("options") or {}
        if not isinstance(options, dict):
            continue
        source = str(options.get("entity_id") or "")
        source = by_uuid.get(source, source)
        if not source.startswith("switch.") or source not in by_id or by_id[source].get("disabled_by"):
            continue
        wrappers = sorted(entity_id for entity_id, entity in by_id.items()
                          if entity.get("platform") == "switch_as_x"
                          and entity.get("config_entry_id") == entry.get("entry_id")
                          and entity_id.startswith(("light.", "fan.")) and not entity.get("disabled_by"))
        if wrappers:
            metadata[source].setdefault("wired_load_ids", []).extend(wrappers)
            metadata[source]["wired_load_names"] = {
                entity_id: by_id[entity_id].get("name") or by_id[entity_id].get("original_name") or entity_id.split(".", 1)[-1].replace("_", " ").title()
                for entity_id in wrappers
            }
    return metadata


def entity_integrations_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> dict[str, str]:
    """Map entity IDs to registry platforms without a WebSocket request."""
    try:
        payload = json.loads(
            config_directory.joinpath(".storage/core.entity_registry").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return {}
    entities = payload.get("data", {}).get("entities", [])
    return {
        str(entity.get("entity_id")): str(entity.get("platform") or "")
        for entity in entities
        if isinstance(entity, dict) and entity.get("entity_id")
    }


def button_devices_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> list[dict[str, Any]]:
    """Return named physical button devices and their event entities."""
    storage_directory = config_directory / ".storage"
    try:
        device_payload = json.loads(
            storage_directory.joinpath("core.device_registry").read_text(
                encoding="utf-8"
            )
        )
        area_payload = json.loads(
            storage_directory.joinpath("core.area_registry").read_text(
                encoding="utf-8"
            )
        )
        entity_payload = json.loads(
            storage_directory.joinpath("core.entity_registry").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return []

    areas = area_payload.get("data", {}).get("areas", [])
    devices = device_payload.get("data", {}).get("devices", [])
    entities = entity_payload.get("data", {}).get("entities", [])
    area_names = {
        str(area.get("area_id") or area.get("id")): str(area["name"])
        for area in areas
        if isinstance(area, dict)
        and (area.get("area_id") or area.get("id"))
        and area.get("name")
    }
    event_entities_by_device: dict[str, list[str]] = {}
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("disabled_by"):
            continue
        entity_id = _clean_value(entity.get("entity_id"))
        device_id = _clean_value(entity.get("device_id"))
        if not entity_id or not device_id or not entity_id.startswith("event."):
            continue
        event_entities_by_device.setdefault(device_id, []).append(entity_id)

    buttons = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        name = _clean_value(device.get("name_by_user") or device.get("name"))
        searchable_name = (name or "").casefold()
        identifiers = device.get("identifiers")
        is_zha = isinstance(identifiers, list) and any(
            isinstance(identifier, list) and identifier[:1] == ["zha"]
            for identifier in identifiers
        )
        device_id = _clean_value(device.get("id"))
        event_entity_ids = sorted(
            event_entities_by_device.get(device_id or "", [])
        )
        if (
            not name
            or not device_id
            or "button" not in searchable_name
            or "switch" in searchable_name
            or (not is_zha and not event_entity_ids)
        ):
            continue
        buttons.append(
            {
                "device_id": device_id,
                "friendly_name": name,
                "area": area_names.get(
                    str(device.get("area_id") or ""), "Other"
                ),
                "native_zha_triggers": is_zha,
                "event_entity_ids": event_entity_ids,
            }
        )
    return sorted(buttons, key=lambda button: button["friendly_name"])


def fetch_button_devices(
    token: str,
    websocket_url: str,
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> list[dict[str, Any]]:
    """Return named buttons with native ZHA and Matter event metadata."""
    buttons = button_devices_from_storage(config_directory)
    if not buttons:
        return []
    zha_buttons = [
        button for button in buttons if button["native_zha_triggers"]
    ]
    commands = [
        {"type": "device_automation/trigger/list", "device_id": button["device_id"]}
        for button in zha_buttons
    ]
    results = []
    if commands:
        try:
            results = execute_websocket_commands(token, websocket_url, commands)
        except HomeAssistantAPIError:
            results = [[] for _button in zha_buttons]
    native_results = {
        button["device_id"]: result
        for button, result in zip(zha_buttons, results, strict=False)
    }
    for button in buttons:
        result = native_results.get(button["device_id"], [])
        triggers = result if isinstance(result, list) else []
        button["triggers"] = [
            {
                "domain": _clean_value(trigger.get("domain")),
                "type": _clean_value(trigger.get("type")),
                "subtype": _clean_value(trigger.get("subtype")),
            }
            for trigger in triggers
            if isinstance(trigger, dict)
            and _clean_value(trigger.get("domain")) == "zha"
            and _clean_value(trigger.get("type")).startswith("remote_button_")
        ]
        button["triggers"] = list(
            {
                (
                    trigger["domain"],
                    trigger["type"],
                    trigger["subtype"],
                ): trigger
                for trigger in button["triggers"]
            }.values()
        )
        button.pop("native_zha_triggers", None)
    return buttons


class ButtonDeviceInventory:
    """Cache relatively stable physical-button registry metadata."""

    def __init__(
        self,
        token: str,
        websocket_url: str,
        config_directory: Path,
        cache_ttl: float = PROTECT_RESOURCE_CACHE_TTL_SECONDS,
    ) -> None:
        self._token = token
        self._websocket_url = websocket_url
        self._config_directory = config_directory
        self._cache_ttl = max(0.0, float(cache_ttl))
        self._lock = threading.Lock()
        self._cache: list[dict[str, Any]] | None = None
        self._cache_at = 0.0
        self._discovery_lock = threading.Lock()
        self._warming = False
        self._retry_at = 0.0

    def peek(self) -> dict[str, Any]:
        """Return cached discovery immediately and warm it independently."""
        self.warm()
        with self._lock:
            return {"buttons": copy.deepcopy(self._cache or []), "pending": self._cache is None or self._warming}

    def warm(self) -> None:
        with self._lock:
            if self._warming or time.monotonic() < self._retry_at:
                return
            if self._cache is not None and time.monotonic() - self._cache_at < self._cache_ttl:
                return
            self._warming = True

        def discover() -> None:
            try:
                self.fetch()
            except Exception:
                with self._lock:
                    self._retry_at = time.monotonic() + 30
            finally:
                with self._lock:
                    self._warming = False

        threading.Thread(target=discover, name="button-discovery-warmup", daemon=True).start()

    def fetch(self, force: bool = False) -> list[dict[str, Any]]:
        """Return physical buttons without reopening the registry socket."""
        with self._discovery_lock:
            if (
                not force
                and self._cache is not None
                and time.monotonic() - self._cache_at < self._cache_ttl
            ):
                return copy.deepcopy(self._cache)
            buttons = fetch_button_devices(
                self._token,
                self._websocket_url,
                self._config_directory,
            )
            with self._lock:
                self._cache = copy.deepcopy(buttons)
                self._cache_at = time.monotonic()
            return buttons


def protect_device_links_from_storage(
    config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
) -> dict[str, dict[str, Any]]:
    """Map Protect hardware identifiers to Home Assistant device details."""
    storage_directory = config_directory / ".storage"

    def load_values(filename: str, key: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(
                storage_directory.joinpath(filename).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError):
            return []
        values = payload.get("data", {}).get(key, [])
        return values if isinstance(values, list) else []

    areas = load_values("core.area_registry", "areas")
    devices = load_values("core.device_registry", "devices")
    entities = load_values("core.entity_registry", "entities")
    area_names = {
        str(area.get("area_id") or area.get("id")): str(area["name"])
        for area in areas
        if (area.get("area_id") or area.get("id")) and area.get("name")
    }
    entities_by_device: dict[str, list[dict[str, str]]] = {}
    for entity in entities:
        if entity.get("platform") != "unifiprotect":
            continue
        device_id = _clean_value(entity.get("device_id"))
        entity_id = _clean_value(entity.get("entity_id"))
        if device_id and entity_id:
            entities_by_device.setdefault(device_id, []).append(
                {
                    "entity_id": entity_id,
                    "category": _clean_value(
                        entity.get("entity_category")
                    ) or "",
                }
            )

    links: dict[str, dict[str, Any]] = {}
    for device in devices:
        device_id = _clean_value(device.get("id"))
        if not device_id:
            continue
        identifiers: list[str] = []
        for connection in device.get("connections") or []:
            if isinstance(connection, list) and len(connection) > 1:
                identifiers.append(str(connection[1]))
        for identifier in device.get("identifiers") or []:
            if (
                isinstance(identifier, list)
                and len(identifier) > 1
                and identifier[0] == "unifiprotect"
            ):
                identifiers.append(str(identifier[1]))
        if not identifiers:
            continue
        linked_entities = sorted(
            entities_by_device.get(device_id, []),
            key=lambda entity: entity["entity_id"],
        )
        has_protect_identifier = any(
            isinstance(identifier, list)
            and identifier
            and identifier[0] == "unifiprotect"
            for identifier in device.get("identifiers") or []
        )
        if not linked_entities and not has_protect_identifier:
            continue
        display_name = _clean_value(device.get("name_by_user")) or _clean_value(
            device.get("name")
        )
        link = {
            "name": display_name or "Unifi Protect Device",
            "area": area_names.get(str(device.get("area_id") or ""), ""),
            "entity_count": len(linked_entities),
            "entities": linked_entities,
        }
        for identifier in identifiers:
            normalized = re.sub(r"[^a-z0-9]", "", identifier.casefold())
            if normalized:
                links[normalized] = link
    return links


def _entity_words(entity: dict[str, Any]) -> set[str]:
    """Return normalized words from an entity ID and friendly name."""
    values = (
        entity.get("entity_id"),
        entity.get("friendly_name"),
    )
    return {
        word
        for value in values
        for word in re.split(r"[^a-z0-9]+", str(value or "").casefold())
        if word
    }


def should_include_entity(entity: dict[str, Any]) -> bool:
    """Return whether an entity belongs in the Future Homes Tech list."""
    domain = str(entity.get("domain") or "").casefold()
    if domain in EXCLUDED_DOMAINS:
        return False
    if domain.startswith(EXCLUDED_DOMAIN_PREFIXES):
        return False
    if (
        domain == "button"
        and _entity_words(entity) & EXCLUDED_BUTTON_WORDS
    ):
        return False
    return True


def filter_entities(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply the configured entity-list exclusions."""
    return [
        entity
        for entity in entities
        if should_include_entity(entity)
    ]


def action_catalog_from_entities(
    entities: list[dict[str, Any]],
    bedroom_areas: list[str] | None = None,
    wake_areas: list[str] | None = None,
    saved_actions: dict[str, list[str]] | None = None,
    enabled_room_modes: dict[str, list[str]] | None = None,
    generated_group_ids: set[str] | None = None,
    group_replacements: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Build one stable capability catalog for every action editor."""
    catalog = CATALOG.light_target_catalog(
        entities,
        saved_actions=saved_actions,
        generated_group_ids=generated_group_ids,
        group_replacements=group_replacements,
        retired_unavailable_lights=CATALOG_RETIRED_UNAVAILABLE_LIGHTS,
        indicator_light_pattern=CATALOG_INDICATOR_LIGHT_PATTERN,
    )
    return {
        "light_groups": catalog["light_groups"],
        "entity_targets": catalog["entity_targets"],
        "individual_lights": catalog["individual_lights"],
        "room_modes": [
            {
                "area": area,
                "entity_id": (
                    f"input_select.fht_{BedroomModeAutomationManager._slug(area)}_mode"
                ),
                "options": [label for mode, label in RoomModeSettings.AVAILABLE_MODES
                            if mode in enabled_room_modes.get(area, [])]
                           if enabled_room_modes is not None else ["Sleep", "Toddler"],
            }
            for area in sorted(set(bedroom_areas or []), key=str.casefold)
            if enabled_room_modes is None or enabled_room_modes.get(area)
        ],
        "wake_overrides": [
            {
                "area": area,
                "entity_id": WakeRoutineAutomationManager.override_button(area),
            }
            for area in sorted(set(wake_areas or []), key=str.casefold)
        ],
        "unavailable_targets": catalog["unavailable_targets"],
    }


def protect_api_url(webhook_url: str, endpoint: str) -> str:
    """Derive a Protect API endpoint from the configured webhook."""
    parsed = urlsplit(webhook_url)
    marker = "/integration/v1/"
    marker_index = parsed.path.find(marker)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.fragment)
        or marker_index < 0
    ):
        raise HomeAssistantAPIError(
            "The configured Protect webhook URL cannot provide arm status."
        )

    api_path = parsed.path[: marker_index + len(marker)]
    api_path += endpoint.lstrip("/")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            api_path,
            "",
            "",
        )
    )


def arm_profiles_from_payload(
    payload: Any,
) -> dict[str, dict[str, Any]]:
    """Index Protect arm profiles by ID."""
    if not isinstance(payload, list):
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    for profile in payload:
        if not isinstance(profile, dict):
            continue
        profile_id = _clean_value(profile.get("id"))
        if not profile_id:
            continue
        profiles[profile_id] = {
            "id": profile_id,
            "name": _clean_value(profile.get("name")),
            "activation_delay": profile.get("activationDelay"),
        }
    return profiles


def arm_modes_from_nvr_payload(
    payload: Any,
) -> list[dict[str, Any]]:
    """Extract arm-mode details from Protect NVR responses."""
    if isinstance(payload, dict):
        nvrs = [payload]
    elif isinstance(payload, list):
        nvrs = payload
    else:
        return []

    arm_modes: list[dict[str, Any]] = []
    for nvr in nvrs:
        if not isinstance(nvr, dict):
            continue
        arm_mode = nvr.get("armMode")
        if not isinstance(arm_mode, dict):
            continue
        status = _clean_value(arm_mode.get("status"))
        if not status:
            continue

        nvr_name = nvr.get("name")
        if isinstance(nvr_name, dict):
            nvr_name = (
                nvr_name.get("name")
                or nvr_name.get("text")
            )

        arm_modes.append(
            {
                "status": status,
                "arm_profile_id": _clean_value(
                    arm_mode.get("armProfileId")
                ),
                "armed_at": arm_mode.get("armedAt"),
                "will_be_armed_at": arm_mode.get("willBeArmedAt"),
                "breach_detected_at": arm_mode.get(
                    "breachDetectedAt"
                ),
                "breach_event_count": arm_mode.get(
                    "breachEventCount",
                    0,
                ),
                "nvr_id": _clean_value(nvr.get("id")),
                "nvr_name": _clean_value(nvr_name),
            }
        )
    return arm_modes


class ProtectAPI:
    """Read Protect alarm status using the configured module credentials."""

    _MINIMUM_REQUEST_INTERVAL = 1.0

    def __init__(
        self,
        api_key: str,
        webhook_url: str,
        verify_ssl: bool = True,
        ca_certificate: str = "",
    ) -> None:
        """Initialize the Protect API client."""
        self._api_key = api_key
        self._webhook_url = webhook_url
        self._verify_ssl = verify_ssl
        self._ca_certificate = ca_certificate.strip()
        self._arm_profiles: dict[str, dict[str, Any]] = {}
        self._arm_profiles_loaded = False
        self._request_lock = threading.Lock()
        self._last_request_at = 0.0
        self._resource_inventory_lock = threading.Lock()
        self._resource_inventory: dict[str, Any] | None = None
        self._resource_inventory_at = 0.0
        self._status_cache_lock = threading.Lock()
        self._arm_mode_cache: dict[str, Any] | None = None
        self._arm_mode_cache_at = 0.0
        self._nvr_cache: dict[str, Any] | None = None
        self._nvr_cache_at = 0.0

    def _fetch_json(self, endpoint: str) -> Any:
        """Fetch one Protect API JSON response."""
        if not self._api_key:
            raise HomeAssistantAPIError(
                "The Protect API key is unavailable."
            )

        request = Request(
            protect_api_url(self._webhook_url, endpoint),
            headers={
                "X-API-KEY": self._api_key,
                "Accept": "application/json",
            },
        )
        if self._verify_ssl:
            try:
                tls_context = ssl.create_default_context(
                    cafile=self._ca_certificate or None
                )
            except (OSError, ssl.SSLError) as err:
                raise HomeAssistantAPIError(
                    "Unable to load the configured Protect CA certificate."
                ) from err
        else:
            tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE

        with self._request_lock:
            remaining_delay = (
                self._MINIMUM_REQUEST_INTERVAL
                - (time.monotonic() - self._last_request_at)
            )
            if remaining_delay > 0:
                time.sleep(remaining_delay)
            try:
                with urlopen(
                    request,
                    timeout=10,
                    context=tls_context,
                ) as response:
                    payload = json.load(response)
            except HTTPError as err:
                raise HomeAssistantAPIError(
                    f"Protect returned HTTP {err.code}."
                ) from err
            except URLError as err:
                reason = err.reason
                if isinstance(reason, ssl.SSLCertVerificationError):
                    message = "Protect TLS certificate verification failed. Check the console hostname and trusted CA certificate."
                elif isinstance(reason, socket.gaierror):
                    message = "Protect console hostname could not be resolved. Check local DNS."
                elif isinstance(reason, (TimeoutError, socket.timeout)):
                    message = "Protect console connection timed out."
                elif isinstance(reason, ConnectionRefusedError):
                    message = "Protect console refused the connection."
                else:
                    message = "Unable to connect to the Protect console."
                raise HomeAssistantAPIError(message) from err
            except TimeoutError as err:
                raise HomeAssistantAPIError("Protect console connection timed out.") from err
            except json.JSONDecodeError as err:
                raise HomeAssistantAPIError(
                    "Protect returned an invalid JSON response."
                ) from err
            finally:
                self._last_request_at = time.monotonic()
        return payload

    def refresh_arm_profiles(self) -> list[dict[str, Any]]:
        """Load and cache configured Protect arm profiles."""
        self._arm_profiles = arm_profiles_from_payload(
            self._fetch_json("arm-profiles")
        )
        self._arm_profiles_loaded = True
        return list(self._arm_profiles.values())

    def fetch_arm_mode(self, force: bool = False) -> dict[str, Any]:
        """Fetch current Protect arm-mode status using cached profiles."""
        with self._status_cache_lock:
            if (
                not force
                and self._arm_mode_cache is not None
                and time.monotonic() - self._arm_mode_cache_at
                < PROTECT_ARM_CACHE_TTL_SECONDS
            ):
                return copy.deepcopy(self._arm_mode_cache)
            try:
                payload = self._fetch_json("nvrs")
            except HomeAssistantAPIError as err:
                if self._arm_mode_cache is None:
                    raise
                stale = copy.deepcopy(self._arm_mode_cache)
                stale.update({"stale": True, "error": str(err)})
                return stale

            arm_modes = arm_modes_from_nvr_payload(payload)
            if not arm_modes:
                raise HomeAssistantAPIError(
                    "Protect returned no arm-mode status."
                )

            profile_error = None
            if not self._arm_profiles_loaded:
                try:
                    self.refresh_arm_profiles()
                except HomeAssistantAPIError as err:
                    profile_error = str(err)

            for arm_mode in arm_modes:
                raw_status = str(arm_mode.get("status") or "")
                arm_mode["raw_status"] = raw_status
                if raw_status.casefold() == "disabled":
                    arm_mode["status"] = "disarmed"
                profile = self._arm_profiles.get(
                    str(arm_mode.get("arm_profile_id") or "")
                )
                arm_mode["arm_profile_name"] = (
                    profile.get("name")
                    if profile
                    else None
                )

            queried_at = datetime.now(timezone.utc).isoformat()
            self._arm_mode_cache = {
                **arm_modes[0],
                "arm_modes": arm_modes,
                "arm_profiles": list(self._arm_profiles.values()),
                "profile_error": profile_error,
                "queried_at": queried_at,
                "last_success_at": queried_at,
                "stale": False,
                "error": None,
            }
            self._arm_mode_cache_at = time.monotonic()
            return copy.deepcopy(self._arm_mode_cache)

    def fetch_nvr_object(self, force: bool = False) -> dict[str, Any]:
        """Return the current raw NVR object and extracted arm mode."""
        with self._status_cache_lock:
            if (
                not force
                and self._nvr_cache is not None
                and time.monotonic() - self._nvr_cache_at
                < PROTECT_NVR_CACHE_TTL_SECONDS
            ):
                return copy.deepcopy(self._nvr_cache)
            try:
                payload = self._fetch_json("nvrs")
            except HomeAssistantAPIError as err:
                if self._nvr_cache is None:
                    raise
                stale = copy.deepcopy(self._nvr_cache)
                stale.update({"stale": True, "error": str(err)})
                return stale
            arm_modes = arm_modes_from_nvr_payload(payload)
            queried_at = datetime.now(timezone.utc).isoformat()
            self._nvr_cache = {
                "nvr_object": payload,
                "arm_mode": arm_modes[0] if arm_modes else None,
                "queried_at": queried_at,
                "last_success_at": queried_at,
                "stale": False,
                "error": None,
            }
            self._nvr_cache_at = time.monotonic()
            return copy.deepcopy(self._nvr_cache)

    def fetch_resource_inventory(self, force: bool = False) -> dict[str, Any]:
        """Return raw responses for the supported Protect inventory endpoints."""
        resources = (
            "fobs",
            "sirens",
            "sensors",
            "cameras",
            "chimes",
            "users",
            "identity-users",
            "arm-profiles",
            "relays",
            "speakers",
            "bridges",
            "link-stations",
            "alarm-hubs",
            "nvrs",
            "device-assets",
        )
        with self._resource_inventory_lock:
            if (
                not force
                and self._resource_inventory is not None
                and time.monotonic() - self._resource_inventory_at
                < PROTECT_RESOURCE_CACHE_TTL_SECONDS
            ):
                return copy.deepcopy(self._resource_inventory)
            results: dict[str, Any] = {}
            for resource in resources:
                try:
                    results[resource] = self._fetch_json(resource)
                except HomeAssistantAPIError as err:
                    results[resource] = {"error": str(err)}
            self._resource_inventory = results
            self._resource_inventory_at = time.monotonic()
            return copy.deepcopy(results)


def arm_mode_state_value(arm_mode: dict[str, Any]) -> str:
    """Format the current Protect mode for the Home Assistant sensor."""
    status = str(arm_mode.get("status") or "unknown")
    if status.casefold() not in {"disarmed", "arming"}:
        profile_name = _clean_value(arm_mode.get("arm_profile_name"))
        if profile_name:
            return profile_name
    return status.replace("_", " ").title()


class HomeAssistantHelperPublisher:
    """Publish Protect status to the managed Home Assistant helper."""

    def __init__(self, token: str, services_url: str) -> None:
        """Initialize the Home Assistant service client."""
        self._token = token
        self._services_url = services_url.rstrip("/")

    def _call_service(
        self,
        domain: str,
        service: str,
        payload: dict[str, Any],
    ) -> None:
        """Call one Home Assistant service."""
        if not self._token:
            raise HomeAssistantAPIError(
                "The Home Assistant API token is unavailable."
            )
        request = Request(
            f"{self._services_url}/{domain}/{service}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10):
                pass
        except HTTPError as err:
            raise HomeAssistantAPIError(
                f"Home Assistant returned HTTP {err.code}."
            ) from err
        except (URLError, TimeoutError) as err:
            raise HomeAssistantAPIError(
                "Unable to update the Protect arm-mode helper."
            ) from err

    def reload_managed_entities(self) -> None:
        """Reload every managed YAML domain after configuration changes."""
        self.reload_domains(
            (
                "input_boolean",
                "input_button",
                "input_datetime",
                "input_number",
                "input_select",
                "input_text",
                "template",
                "rest_command",
                "timer",
                "automation",
            )
        )

    def reload_domains(self, domains: tuple[str, ...]) -> None:
        """Serialize and deduplicate managed-domain reload calls."""
        failures = []
        ordered_domains = tuple(dict.fromkeys(domains))
        with CONFIGURATION_ACTIVATION_LOCK:
            for domain in ordered_domains:
                try:
                    self._call_service(domain, "reload", {})
                except HomeAssistantAPIError as err:
                    failures.append(f"{domain}: {err}")
        if failures:
            raise HomeAssistantAPIError(
                "Managed configuration reload failed for "
                + "; ".join(failures)
            )

    def reload_all(self) -> None:
        """Reload all reloadable YAML after generated output changes."""
        with CONFIGURATION_ACTIVATION_LOCK:
            self._call_service("homeassistant", "reload_all", {})

    def reload_automations(self) -> None:
        """Reload native automations after Control assignments change."""
        self.reload_domains(("automation",))

    def fire_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire one Home Assistant event for managed automations."""
        if not self._token:
            raise HomeAssistantAPIError(
                "The Home Assistant API token is unavailable."
            )
        base = self._services_url.rsplit("/services", 1)[0]
        request = Request(
            f"{base}/events/{event_type}",
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10):
                pass
        except (HTTPError, URLError, TimeoutError, OSError) as err:
            raise HomeAssistantAPIError(
                f"Unable to fire Home Assistant event {event_type}: {err}"
            ) from err

    def toggle_control(self, entity_id: str) -> None:
        """Toggle one supported control entity from the App interface."""
        if not is_direct_control_entity_id(entity_id):
            raise ValueError("A valid switch, light, or fan is required.")
        domain = entity_id.partition(".")[0]
        self._call_service(
            domain,
            "toggle",
            {"entity_id": entity_id},
        )

    def light_action(
        self,
        action: str,
        entity_ids: list[str],
        brightness_pct: Any = None,
    ) -> None:
        """Run one validated Future Homes Tech light-group action."""

        standalone = lighting_entity_ids() or set()
        valid_entity_ids = sorted(
            {
                entity_id
                for entity_id in entity_ids
                if entity_id.startswith("light.fht_") or entity_id in standalone
            }
        )
        if not valid_entity_ids or len(valid_entity_ids) != len(set(entity_ids)):
            raise ValueError("Valid Future Homes Tech light groups are required.")
        service_data: dict[str, Any] = {"entity_id": valid_entity_ids}
        if action == "toggle" and len(valid_entity_ids) == 1:
            self._call_service("light", "toggle", service_data)
            return
        if action == "turn_off":
            self._call_service("light", "turn_off", service_data)
            return
        if action == "set_brightness" and len(valid_entity_ids) == 1:
            brightness = max(1, min(100, int(float(brightness_pct))))
            service_data["brightness_pct"] = brightness
            self._call_service("light", "turn_on", service_data)
            return
        raise ValueError("Unsupported Lighting action.")

    def climate_action(self, action: str, entity_id: str, value: Any = None) -> None:
        """Run one validated Climate Settings action."""
        if action == "toggle" and entity_id.startswith("input_boolean."):
            self._call_service("input_boolean", "toggle", {"entity_id": entity_id})
            return
        if action == "set_number" and entity_id.startswith("input_number."):
            self._call_service(
                "input_number", "set_value", {"entity_id": entity_id, "value": float(value)}
            )
            return
        if action == "set_option" and entity_id.startswith("input_select."):
            self._call_service(
                "input_select", "select_option", {"entity_id": entity_id, "option": str(value)}
            )
            return
        if action == "set_time" and entity_id.startswith("input_datetime."):
            self._call_service(
                "input_datetime", "set_datetime", {"entity_id": entity_id, "time": str(value)}
            )
            return
        if action == "set_temperature" and entity_id.startswith("climate."):
            self._call_service(
                "climate", "set_temperature", {"entity_id": entity_id, "temperature": float(value)}
            )
            return
        if action == "push_rate_targets" and entity_id == "automation.fht_climate_set_targets_on_rate_mode_change":
            self._call_service(
                "automation", "trigger", {"entity_id": entity_id, "skip_condition": True}
            )
            return
        raise ValueError("Unsupported Climate Settings action.")

    def publish(self, value: str) -> None:
        """Set the managed Protect arm-mode helper value."""
        self._call_service(
            "input_text",
            "set_value",
            {
                "entity_id": PROTECT_STATUS_HELPER,
                "value": value,
            },
        )


def publish_protect_status_forever(
    protect_api: ProtectAPI,
    publisher: HomeAssistantHelperPublisher,
    registry_organizer: HomeAssistantRegistryOrganizer,
    poll_interval: int = PROTECT_STATUS_POLL_INTERVAL,
) -> None:
    """Continuously publish Protect arm mode to Home Assistant."""
    try:
        protect_api.refresh_arm_profiles()
    except HomeAssistantAPIError:
        pass
    try:
        climate_count = registry_organizer.categorize_climate_helpers()
        print(
            (
                "[Climate] Organized "
                f"{climate_count} helpers under {CLIMATE_CATEGORY_NAME}."
            ),
            flush=True,
        )
    except HomeAssistantAPIError as err:
        print(f"[Climate] ERROR {err}", flush=True)
    try:
        door_timer_count = registry_organizer.categorize_door_timer_helpers()
        print(
            (
                "[Door Timers] Organized "
                f"{door_timer_count} helpers under {DOOR_TIMER_CATEGORY_NAME}."
            ),
            flush=True,
        )
    except HomeAssistantAPIError as err:
        print(f"[Door Timers] ERROR {err}", flush=True)
    try:
        ungrouped_count = registry_organizer.categorize_ungrouped_helpers()
        print(
            (
                "[Helpers] Organized "
                f"{ungrouped_count} helpers under {UNGROUPED_HELPER_CATEGORY_NAME}."
            ),
            flush=True,
        )
    except HomeAssistantAPIError as err:
        print(f"[Helpers] ERROR {err}", flush=True)

    while True:
        try:
            arm_mode = protect_api.fetch_arm_mode(force=True)
            publisher.publish(
                "Unavailable"
                if arm_mode.get("stale")
                else arm_mode_state_value(arm_mode)
            )
        except HomeAssistantAPIError as err:
            try:
                publisher.publish("Unavailable")
            except HomeAssistantAPIError:
                pass
            print(f"[Protect Status] ERROR {err}", flush=True)
        time.sleep(poll_interval)


def organize_light_groups_on_startup(
    registry_organizer: HomeAssistantRegistryOrganizer,
    attempts: int = 6,
    retry_delay: float = 10,
) -> None:
    """Wait for Home Assistant before assigning the Light Groups category."""
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            group_count = registry_organizer.categorize_light_groups(
                attempts=2,
                retry_delay=3,
            )
            print(
                (
                    "[Light Groups] Organized "
                    f"{group_count} helpers under {LIGHT_GROUP_CATEGORY_NAME}."
                ),
                flush=True,
            )
            return
        except HomeAssistantAPIError as err:
            if attempt >= max(attempts, 1):
                print(f"[Light Groups] ERROR {err}", flush=True)
                return
            print(
                (
                    "[Light Groups] Waiting for Home Assistant "
                    f"({attempt}/{attempts}): {err}"
                ),
                flush=True,
            )
            time.sleep(retry_delay)


class RetiredEntityApprovals:
    """Retired App entities wait for the installer's approval before deletion."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._lock = threading.Lock()

    @property
    def _settings_path(self) -> Path:
        return self._directory / "cleanup_settings.json"

    @property
    def _pending_path(self) -> Path:
        return self._directory / "cleanup_pending.json"

    def auto_remove(self) -> bool:
        try:
            return bool(json.loads(self._settings_path.read_text(encoding="utf-8")).get("auto_remove"))
        except (OSError, ValueError, AttributeError):
            return False

    def set_auto_remove(self, enabled: bool) -> None:
        with self._lock:
            atomic_write_json(self._settings_path, {"auto_remove": bool(enabled)})

    @staticmethod
    def describe(entries: list[dict[str, Any]], entities: list[dict[str, Any]]) -> list[dict[str, str]]:
        names = {str(entity.get("entity_id")): entity.get("friendly_name") for entity in entities}
        return [
            {
                "entity_id": str(entry["entity_id"]),
                "name": str(entry.get("name") or entry.get("original_name") or names.get(str(entry["entity_id"])) or entry["entity_id"])[:180],
                "platform": str(entry.get("platform") or ""),
            }
            for entry in entries
        ]

    def save_pending(self, items: list[dict[str, str]]) -> None:
        with self._lock:
            atomic_write_json(self._pending_path, {"found_at": datetime.now(timezone.utc).isoformat(), "items": items})

    def pending(self) -> list[dict[str, str]]:
        try:
            items = json.loads(self._pending_path.read_text(encoding="utf-8")).get("items", [])
        except (OSError, ValueError, AttributeError):
            return []
        return items if isinstance(items, list) else []

    def journal(self, entries: list[dict[str, Any]]) -> None:
        """Keep the full registry entries of deleted entities for reference."""
        if not entries:
            return
        directory = self._directory / "maintenance" / "removed"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        atomic_write_json(directory / f"{stamp}.json", {"removed_at": stamp, "entries": entries})


def rename_entity_ids_in_settings(settings_directory: Path, renames: dict[str, str]) -> int:
    """Replace renamed entity IDs in saved App settings; return files changed."""
    if not renames:
        return 0
    pattern = re.compile(
        r"(?<![A-Za-z0-9_.])(" + "|".join(re.escape(old) for old in sorted(renames, key=len, reverse=True)) + r")(?![A-Za-z0-9_])"
    )
    changed = 0
    for path in sorted(settings_directory.glob("**/*.json")):
        if "beta" in path.relative_to(settings_directory).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        updated = pattern.sub(lambda match: renames[match.group(1)], text)
        if updated == text:
            continue
        try:
            json.loads(updated)
            atomic_write_text(path, updated)
        except (OSError, ValueError) as err:
            print(f"[Groups] WARNING Unable to update {path.name}: {err}", flush=True)
            continue
        changed += 1
    return changed


def sync_generated_configuration_on_startup(
    handler: type[FutureHomesTechRequestHandler],
    publisher: HomeAssistantHelperPublisher,
    registry_organizer: HomeAssistantRegistryOrganizer,
    attempts: int = 6,
    retry_delay: float = 10,
    raise_errors: bool = False,
) -> None:
    """Build every generated package, then activate one coherent revision.

    Settings undo re-runs this with ``raise_errors`` so the person is told
    when the restored settings could not be activated.
    """
    for attempt in range(1, max(1, attempts) + 1):
        try:
            renames = registry_organizer.normalize_group_entity_ids({
                str(group["unique_id"]): str(group["entity_id"])
                for group in handler.presence_groups.discover()
            })
            if renames:
                migrated = rename_entity_ids_in_settings(
                    handler.switch_control_settings._path.parent, renames
                )
                print(
                    f"[Groups] Renamed {len(renames)} groups to fht_ IDs and updated "
                    f"{migrated} settings files: "
                    + ", ".join(f"{old} → {new}" for old, new in sorted(renames.items())),
                    flush=True,
                )
            inventory = handler.inventory.fetch(include_all=True, force=bool(renames))
            entities = inventory["entities"]
            legacy_switch_assignments = handler.switch_assignments.read()
            legacy_door_assignments = handler.door_assignments.read()
            handler.switch_control_settings.reconcile_actual_load_names(
                entities
            )
            control_settings = handler.switch_control_settings.migrate_legacy(
                legacy_switch_assignments,
                legacy_door_assignments,
            )
            expected_groups = generated_light_group_entity_ids()
            group_replacements = {
                retired: targets
                for retired, targets in generated_light_group_replacements().items()
                if expected_groups is not None and retired not in expected_groups
                and targets and (targets[0] in expected_groups or not targets[0].startswith(LIGHT_GROUP_ENTITY_PREFIX))
            }
            if group_replacements:
                migrated = replace_entity_ids_in_settings(
                    handler.switch_control_settings._path.parent, group_replacements
                )
                if migrated:
                    print(
                        f"[Groups] Moved saved actions in {migrated} settings files: "
                        + ", ".join(f"{old} → {' + '.join(new)}" for old, new in sorted(group_replacements.items())),
                        flush=True,
                    )
            control_settings = handler.switch_control_settings.reconcile_retired_fan_light_groups(entities, expected_groups)
            handler.presence_groups.sync()
            handler.control_automations.sync(
                legacy_switch_assignments,
                entities,
                handler.button_inventory.fetch(),
                control_settings["mode_assignments"],
                control_settings["load_target_assignments"],
                control_settings["actual_loads"],
                control_settings["action_assignments"],
                control_settings["action_settings"],
                exhaust_timers=control_settings.get("exhaust_timers", {}),
                exhaust_humidity=control_settings.get("exhaust_humidity", {}),
                exhaust_presence=control_settings.get("exhaust_presence", {}),
                reload_automations=False,
            )
            handler.door_automations.sync(
                {},
                entities,
                reload_automations=False,
            )
            handler.presence_automations.sync(
                handler.presence_assignments.read(),
                entities,
                handler.presence_timings.read(),
                handler.presence_mode_settings.read(),
                reload_automations=False,
                room_modes=handler.room_modes.read(),
            )
            handler.light_schedule_automations.sync(
                handler.light_schedules.read(),
                entities,
                reload_automations=False,
            )
            handler.fridge_alarm_automations.sync(
                handler.fridge_alarm_settings.read(), entities,
                reload_automations=False,
            )
            handler.door_open_alert_automations.sync(
                handler.door_open_alert_settings.read(), entities,
                reload_automations=False,
            )
            portal = handler.future_tech_portal
            if portal.url_problem:
                print(f"Future Tech Portal URL: {portal.url_problem}", flush=True)
            try:
                portal.apply_option_token()
            except HomeAssistantAPIError as err:
                # The message never contains the token.
                print(str(err), flush=True)
            try:
                portal_changed = portal.apply(reload=False)
            except HomeAssistantAPIError as err:
                portal_changed = False
                print(f"Future Tech Portal package not refreshed: {err}", flush=True)
            bedroom_settings = handler.bedroom_modes.read()
            handler.bedroom_mode_automations.sync(
                bedroom_settings,
                entities,
                [entity for entity in entities if is_door_sensor_entity(entity)],
                reload_managed=False,
            )
            handler.wake_routine_automations.sync(
                handler.wake_routines.read(),
                entities,
                reload_managed=False,
            )
            handler.room_scene_automations.sync(
                handler.room_scenes.read(),
                handler.room_modes.read(),
                reload_automations=False,
            )
            homekit_changed = False
            if expected_groups is not None:
                names = {str(entity["entity_id"]): str(entity.get("friendly_name") or entity["entity_id"])
                         for entity in entities if entity.get("entity_id")}
                homekit_changed = handler.homekit_light_groups.reconcile_generated_groups(expected_groups, names)
            if os.environ.get("LIGHT_GROUPS_CHANGED") == "1" or homekit_changed:
                publisher.reload_all()
            else:
                publisher.reload_domains(
                    (
                        "template",
                        "input_select",
                        "input_boolean",
                        "timer",
                        "input_datetime",
                        "input_button",
                        "rest_command",
                        "automation",
                        *(("script",) if portal_changed else ()),
                    )
                )
            if portal.package_path.exists():
                try:
                    if portal_changed:
                        # A package installed while Home Assistant is running
                        # misses its start trigger, so send the first inventory now.
                        portal.send_inventory(handler.inventory)
                    else:
                        portal.refresh_details(handler.inventory)
                except (HomeAssistantAPIError, ValueError) as err:
                    print(f"Future Tech Portal start-up report not sent: {err}", flush=True)
            handler.bedroom_mode_automations.refresh_house_mode(
                bedroom_settings,
                handler.inventory,
            )
            if expected_groups is not None:
                registry_organizer.cleanup_retired_fan_groups(
                    expected_groups,
                    handler.inventory.fetch(include_all=True, force=True)["entities"],
                    GENERATED_LIGHT_GROUP_PACKAGE.parent.parent,
                    handler.switch_control_settings._path.parent,
                )
            live_entities = handler.inventory.fetch(include_all=True, force=True)["entities"]
            retired_entries = registry_organizer.find_retired_managed_entities(
                live_entities, GENERATED_LIGHT_GROUP_PACKAGE.parent.parent,
            )
            approvals = handler.retired_approvals
            if retired_entries and approvals.auto_remove():
                approvals.journal(retired_entries)
                removed = registry_organizer.cleanup_retired_managed_entities(
                    live_entities, GENERATED_LIGHT_GROUP_PACKAGE.parent.parent,
                    approved={str(entry["entity_id"]) for entry in retired_entries},
                )
                approvals.save_pending([])
                print(f"[Cleanup] Removed {len(removed)} retired entities: " + ", ".join(removed), flush=True)
            else:
                approvals.save_pending(RetiredEntityApprovals.describe(retired_entries, live_entities))
                if retired_entries:
                    print(
                        f"[Cleanup] {len(retired_entries)} retired entities are waiting for approval "
                        "in Settings → Safe Cleanup: "
                        + ", ".join(str(entry["entity_id"]) for entry in retired_entries),
                        flush=True,
                    )
            automation_count = registry_organizer.categorize_automations()
            print(
                "[Managed Configuration] Activated one coordinated revision "
                f"with {automation_count} categorized automations.",
                flush=True,
            )
            return
        except (HomeAssistantAPIError, OSError, ValueError) as err:
            if attempt >= max(1, attempts):
                if raise_errors:
                    raise
                print(
                    f"[Managed Configuration] ERROR {err}",
                    flush=True,
                )
                return
            print(
                "[Managed Configuration] Startup reconciliation "
                f"{attempt}/{attempts} failed: {err}",
                flush=True,
            )
            time.sleep(retry_delay)


ENTITY_CATALOG_FIELDS = (
    "entity_id", "friendly_name", "domain", "device_class", "area", "floor",
    "device_name", "device_id", "original_name", "integration", "members",
    "event_types", "hvac_modes", "options", "minimum", "maximum", "step",
    "unit_of_measurement", "wired_load_ids", "wired_load_names", "manufacturer", "supported_color_modes",
)


class EntityInventory:
    """Read Home Assistant entity inventories for the App interface."""

    def __init__(
        self,
        token: str,
        states_url: str,
        websocket_url: str,
        config_directory: Path = DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
        room_aliases: RoomAliases | None = None,
    ) -> None:
        """Initialize the entity inventory service."""
        self._token = token
        self._states_url = states_url
        self._websocket_url = websocket_url
        self._config_directory = config_directory
        self._room_aliases = room_aliases
        self._cache_lock = threading.RLock()
        self._cache_condition = threading.Condition(self._cache_lock)
        self._refresh_lock = threading.Lock()
        self._cached_entities: dict[str, dict[str, Any]] | None = None
        self._cached_generated_at = ""
        self._cached_complete_at_monotonic = 0.0
        self._cache_revision = 0
        self._metadata_revision = 0
        self._live_connected = False
        self._last_event_at = ""
        self._last_error = ""
        self._event_history: deque[dict[str, Any]] = deque(
            maxlen=ENTITY_EVENT_HISTORY_LIMIT
        )
        self._live_thread: threading.Thread | None = None
        self._background_refresh_thread: threading.Thread | None = None
        self._next_background_refresh_at = 0.0
        self._live_stop = threading.Event()
        self._registry_refresh_pending = False
        self._events_during_refresh: dict[str, Any] | None = None

    def _schedule_registry_refresh(self) -> None:
        """Batch registry bursts without blocking the state-event reader."""
        with self._cache_lock:
            if self._registry_refresh_pending or self._live_stop.is_set():
                return
            self._registry_refresh_pending = True

        def refresh() -> None:
            try:
                if self._live_stop.wait(0.5):
                    with self._cache_lock:
                        self._registry_refresh_pending = False
                    return
                with self._refresh_lock:
                    with self._cache_lock:
                        self._registry_refresh_pending = False
                    if not self._live_stop.is_set():
                        self._fetch_full_inventory()
            except (HomeAssistantAPIError, OSError, ValueError) as error:
                self._set_live_connection(False, str(error))

        threading.Thread(target=refresh, name="registry-burst-refresh", daemon=True).start()

    @staticmethod
    def _event_channels(entity: dict[str, Any] | None) -> list[str]:
        """Return compact browser projections affected by one state change."""
        if not entity:
            return ["inventory"]
        domain = str(entity.get("domain") or "").casefold()
        device_class = str(entity.get("device_class") or "").casefold()
        entity_id = str(entity.get("entity_id") or "")
        searchable_name = " ".join(
            str(entity.get(key) or "")
            for key in ("friendly_name", "entity_id")
        ).replace("_", " ").casefold()
        channels = {"inventory"}
        if domain == "light":
            channels.add("lighting")
        if domain == "binary_sensor" and (
            device_class in {"door", "garage_door", "opening", "window"}
            or "door sensor" in searchable_name
            or "window sensor" in searchable_name
        ):
            channels.add("security")
        if entity_id == DEFAULT_WEATHER_ENTITY:
            channels.add("weather")
        return sorted(channels)

    def _record_revision_locked(
        self,
        entity: dict[str, Any] | None = None,
        *,
        resync: bool = False,
    ) -> None:
        """Advance the cache revision and wake waiting browser clients."""
        self._cache_revision += 1
        self._event_history.append(
            {
                "revision": self._cache_revision,
                "entity_id": str((entity or {}).get("entity_id") or ""),
                "area": str((entity or {}).get("area") or ""),
                "channels": self._event_channels(entity),
                "resync": resync,
            }
        )
        self._cache_condition.notify_all()

    def wait_for_revision(
        self,
        after_revision: int,
        timeout: float = 25.0,
    ) -> dict[str, Any]:
        """Wait for a live cache revision without polling Home Assistant."""
        after_revision = max(0, int(after_revision))
        timeout = max(0.0, min(float(timeout), 30.0))
        with self._cache_condition:
            self._cache_condition.wait_for(
                lambda: self._cache_revision != after_revision,
                timeout=timeout,
            )
            revision = self._cache_revision
            history = list(self._event_history)
            oldest_revision = (
                int(history[0]["revision"])
                if history
                else revision
            )
            resync = bool(
                after_revision > revision
                or (after_revision == 0 and revision > 0)
                or (after_revision and history and after_revision < oldest_revision - 1)
            )
            events = [
                copy.deepcopy(event)
                for event in history
                if int(event.get("revision") or 0) > after_revision
            ]
            if any(event.get("resync") for event in events):
                resync = True
            channels = sorted(
                {
                    str(channel)
                    for event in events
                    for channel in event.get("channels", [])
                    if channel
                }
            )
            return {
                "revision": revision,
                "changed": revision != after_revision,
                "resync": resync,
                "channels": channels,
                "entity_ids": sorted(
                    {
                        str(event.get("entity_id") or "")
                        for event in events
                        if event.get("entity_id")
                    }
                ),
                "areas": sorted(
                    {
                        str(event.get("area") or "")
                        for event in events
                        if event.get("area")
                    },
                    key=str.casefold,
                ),
                **self._freshness_payload(),
            }

    def start_live_updates(self) -> None:
        """Start one shared Home Assistant state-change subscription."""
        with self._cache_lock:
            if self._live_thread and self._live_thread.is_alive():
                return
            self._live_stop.clear()
            self._live_thread = threading.Thread(
                target=self._run_live_updates,
                name="home-assistant-state-cache",
                daemon=True,
            )
            self._live_thread.start()

    def stop_live_updates(self) -> None:
        """Ask the live cache worker to stop after its current read."""
        self._live_stop.set()

    def _set_live_connection(
        self,
        connected: bool,
        error: str = "",
    ) -> None:
        with self._cache_condition:
            changed = self._live_connected != connected
            self._live_connected = connected
            self._last_error = error
            if changed:
                self._record_revision_locked(resync=True)

    def _apply_state_changed(
        self,
        entity_id: str,
        new_state: dict[str, Any] | None,
    ) -> None:
        """Merge one Home Assistant state event into the shared snapshot."""
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            return
        with self._cache_condition:
            if self._events_during_refresh is not None:
                self._events_during_refresh[entity_id] = copy.deepcopy(new_state)
            if self._cached_entities is None:
                return
            existing_by_id = self._cached_entities
            previous = existing_by_id.get(entity_id)
            if new_state is None:
                existing_by_id.pop(entity_id, None)
                changed_entity = previous or {
                    "entity_id": entity_id,
                    "domain": entity_id.partition(".")[0],
                }
            else:
                normalized = normalize_entities([new_state])
                if not normalized:
                    return
                changed_entity = normalized[0]
                if previous:
                    for key in (
                        "area",
                        "device_name",
                        "floor",
                        "device_id",
                        "original_name",
                        "integration",
                        "wired_load_ids",
                        "wired_load_names",
                        "manufacturer",
                    ):
                        if not changed_entity.get(key) and previous.get(key):
                            changed_entity[key] = previous[key]
                existing_by_id[entity_id] = changed_entity
            if (new_state is None and previous is not None) or (new_state is not None and (
                previous is None or any(previous.get(key) != changed_entity.get(key) for key in ENTITY_CATALOG_FIELDS)
            )):
                self._metadata_revision += 1
            self._cached_generated_at = datetime.now(timezone.utc).isoformat()
            self._last_event_at = self._cached_generated_at
            self._last_error = ""
            self._record_revision_locked(changed_entity)

    def _run_live_updates(self) -> None:
        """Maintain the state subscription with bounded reconnect backoff."""
        backoff = 1.0
        while not self._live_stop.is_set():
            connection: socket.socket | None = None
            try:
                connection, buffered = _open_websocket(self._websocket_url)
                auth_required = _receive_websocket_json(connection, buffered)
                if auth_required.get("type") != "auth_required":
                    raise WebSocketProtocolError(
                        "Home Assistant did not request WebSocket authentication."
                    )
                _send_websocket_json(
                    connection,
                    {"type": "auth", "access_token": self._token},
                )
                auth_result = _receive_websocket_json(connection, buffered)
                if auth_result.get("type") != "auth_ok":
                    raise WebSocketProtocolError(
                        "Home Assistant rejected WebSocket authentication."
                    )
                _send_websocket_json(
                    connection,
                    {
                        "id": 1,
                        "type": "subscribe_events",
                        "event_type": "state_changed",
                    },
                )
                registry_events = (
                    "entity_registry_updated",
                    "device_registry_updated",
                    "area_registry_updated",
                    "floor_registry_updated",
                )
                for subscription_id, event_type in enumerate(
                    registry_events,
                    start=2,
                ):
                    _send_websocket_json(
                        connection,
                        {
                            "id": subscription_id,
                            "type": "subscribe_events",
                            "event_type": event_type,
                        },
                    )
                pending_subscriptions = set(range(1, len(registry_events) + 2))
                pending_events: deque[dict[str, Any]] = deque()
                while pending_subscriptions:
                    subscription = _receive_websocket_json(
                        connection,
                        buffered,
                    )
                    if subscription.get("type") == "event":
                        if subscription.get("id") == 1:
                            pending_events.append(subscription)
                        continue
                    if subscription.get("type") != "result" or subscription.get("success") is not True or subscription.get("id") not in pending_subscriptions:
                        raise WebSocketProtocolError(
                            "Home Assistant rejected a live cache subscription."
                        )
                    pending_subscriptions.remove(subscription["id"])
                with self._refresh_lock:
                    self._fetch_full_inventory()
                self._set_live_connection(True)
                backoff = 1.0
                connection.settimeout(None)
                while not self._live_stop.is_set():
                    message = pending_events.popleft() if pending_events else _receive_websocket_json(connection, buffered)
                    if message.get("type") != "event":
                        continue
                    if message.get("id") != 1:
                        self._schedule_registry_refresh()
                        continue
                    event = message.get("event")
                    event_data = (
                        event.get("data")
                        if isinstance(event, dict)
                        else None
                    )
                    if not isinstance(event_data, dict):
                        continue
                    self._apply_state_changed(
                        str(event_data.get("entity_id") or ""),
                        event_data.get("new_state")
                        if isinstance(event_data.get("new_state"), dict)
                        else None,
                    )
            except (
                HomeAssistantAPIError,
                OSError,
                UnicodeDecodeError,
                ValueError,
                json.JSONDecodeError,
                WebSocketProtocolError,
            ) as err:
                self._set_live_connection(
                    False,
                    f"Live state connection unavailable ({type(err).__name__}).",
                )
                if self._cached_entities is None:
                    try:
                        self.fetch(force=True, include_all=True)
                    except HomeAssistantAPIError:
                        pass
            finally:
                if connection is not None:
                    try:
                        _send_websocket_frame(connection, 0x8, b"")
                    except OSError:
                        pass
                    connection.close()
            if self._live_stop.wait(backoff):
                break
            backoff = min(
                backoff * 2,
                float(ENTITY_LIVE_RECONNECT_MAX_SECONDS),
            )

    def _freshness_payload(self) -> dict[str, Any]:
        """Describe whether projections are current or fallback-cached."""
        with self._cache_lock:
            age = (
                max(0.0, time.monotonic() - self._cached_complete_at_monotonic)
                if self._cached_complete_at_monotonic
                else None
            )
            connected = self._live_connected
            return {
                "revision": self._cache_revision,
                "metadata_revision": self._metadata_revision,
                "live_connected": connected,
                "last_event_at": self._last_event_at or None,
                "cache_age_seconds": round(age, 3) if age is not None else None,
                "stale": bool(
                    age is None
                    or (
                        not connected
                        and age > ENTITY_CACHE_FALLBACK_TTL_SECONDS
                    )
                ),
                "last_error": self._last_error or None,
            }

    def _needs_full_refresh(self) -> bool:
        with self._cache_lock:
            if self._cached_entities is None:
                return True
            if self._live_connected:
                return False
            return (
                time.monotonic() - self._cached_complete_at_monotonic
                > ENTITY_CACHE_FALLBACK_TTL_SECONDS
            )

    def fetch(
        self,
        include_all: bool = False,
        force: bool = False,
        *,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
        fields: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Fetch all current Home Assistant entities."""
        self._ensure_snapshot(force)
        return self._project_snapshot(include_all, predicate, fields)

    def _ensure_snapshot(self, force: bool = False) -> None:
        """Share cold refreshes and recover stale snapshots in the background."""
        if not self._token:
            raise HomeAssistantAPIError(
                "The Home Assistant API token is unavailable."
            )

        refresh_requested_at = time.monotonic()
        needs_refresh = self._needs_full_refresh()
        with self._cache_lock:
            has_snapshot = self._cached_entities is not None
        if needs_refresh and has_snapshot and not force:
            self._schedule_background_refresh()
        elif force or needs_refresh:
            with self._refresh_lock:
                with self._cache_lock:
                    refreshed_while_waiting = (
                        self._cached_entities is not None
                        and self._cached_complete_at_monotonic
                        >= refresh_requested_at
                    )
                if not refreshed_while_waiting and (
                    force or self._needs_full_refresh()
                ):
                    self._fetch_full_inventory()
        with self._cache_lock:
            if self._cached_entities is None:
                raise HomeAssistantAPIError(
                    "The Home Assistant entity cache is unavailable."
                )

    def _schedule_background_refresh(self) -> None:
        """Keep existing screens responsive while a stale snapshot recovers."""
        with self._cache_lock:
            if (self._background_refresh_thread and self._background_refresh_thread.is_alive()) or time.monotonic() < self._next_background_refresh_at:
                return

            def refresh() -> None:
                try:
                    with self._refresh_lock:
                        if self._needs_full_refresh():
                            self._fetch_full_inventory()
                except HomeAssistantAPIError as error:
                    with self._cache_lock:
                        self._last_error = str(error)
                finally:
                    with self._cache_lock:
                        self._next_background_refresh_at = time.monotonic() + 5

            self._background_refresh_thread = threading.Thread(
                target=refresh, name="entity-cache-recovery", daemon=True,
            )
            self._background_refresh_thread.start()

    def peek(
        self, include_all: bool = False, *,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
        fields: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Return the current snapshot without starting a network refresh."""
        return self._project_snapshot(include_all, predicate, fields)

    def _project_snapshot(
        self, include_all: bool,
        predicate: Callable[[dict[str, Any]], bool] | None,
        fields: tuple[str, ...] | None,
    ) -> dict[str, Any]:
        """Copy selected immutable records outside the live-event cache lock."""
        with self._cache_lock:
            cached_entities = tuple((self._cached_entities or {}).values())
            generated_at = self._cached_generated_at
            freshness = self._freshness_payload()
        entities = [
            copy.deepcopy(entity if fields is None else {key: entity.get(key) for key in fields})
            for entity in cached_entities
            if (include_all or should_include_entity(entity))
            and (predicate is None or predicate(entity))
        ]
        entities.sort(key=lambda entity: str(entity.get("entity_id") or ""))
        aliases = self._room_aliases.read() if self._room_aliases else {}
        apply_room_aliases(entities, aliases)
        if not cached_entities:
            freshness = {
                **freshness,
                "stale": True,
                "last_error": freshness.get("last_error")
                or "Entity inventory is warming up.",
            }
        return {
            "generated_at": generated_at or None,
            "count": len(entities),
            "entities": entities,
            **freshness,
        }

    def cached_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Return one normalized entity from the shared live snapshot."""
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            return None
        with self._cache_lock:
            if self._cached_entities is not None:
                return copy.deepcopy(self._cached_entities.get(entity_id))
        return next(
            (
                entity
                for entity in self.fetch(include_all=True)["entities"]
                if entity.get("entity_id") == entity_id
            ),
            None,
        )

    def _fetch_full_inventory(
        self,
    ) -> tuple[list[dict[str, Any]], str]:
        """Preserve events received while the full snapshot is in flight."""
        with self._cache_lock:
            self._events_during_refresh = {}
        try:
            return self._fetch_full_inventory_snapshot()
        finally:
            with self._cache_lock:
                pending = self._events_during_refresh or {}
                self._events_during_refresh = None
                for entity_id, state in pending.items():
                    self._apply_state_changed(entity_id, state)

    def _fetch_full_inventory_snapshot(self) -> tuple[list[dict[str, Any]], str]:
        """Fetch and cache one complete enriched Home Assistant inventory."""

        request = Request(
            self._states_url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as err:
            raise HomeAssistantAPIError(
                f"Home Assistant returned HTTP {err.code}."
            ) from err
        except (URLError, TimeoutError, json.JSONDecodeError) as err:
            raise HomeAssistantAPIError(
                "Unable to read entities from Home Assistant."
            ) from err

        if not isinstance(payload, list):
            raise HomeAssistantAPIError(
                "Home Assistant returned an unexpected entity response."
            )

        entities = normalize_entities(payload)
        registry_areas = entity_areas_from_storage(
            self._config_directory
        )
        registry_devices = entity_devices_from_storage(
            self._config_directory
        )
        registry_floors = entity_floors_from_storage(
            self._config_directory
        )
        registry_control_metadata = entity_control_metadata_from_storage(
            self._config_directory
        )
        live_names = {entity["entity_id"]: entity.get("friendly_name") for entity in entities}
        for entity in entities:
            metadata = registry_control_metadata.get(entity["entity_id"], {})
            entity["area"] = registry_areas.get(
                entity["entity_id"],
                entity.get("area"),
            )
            entity["device_name"] = registry_devices.get(
                entity["entity_id"],
                "",
            )
            entity["floor"] = registry_floors.get(entity["entity_id"], "")
            entity["device_id"] = metadata.get("device_id", "")
            entity["original_name"] = metadata.get("original_name", "")
            entity["manufacturer"] = metadata.get("manufacturer", "")
            entity["wired_load_ids"] = metadata.get("wired_load_ids", [])
            entity["wired_load_names"] = {
                entity_id: live_names.get(entity_id) or name
                for entity_id, name in metadata.get("wired_load_names", {}).items()
            }
        registry_integrations = entity_integrations_from_storage(self._config_directory)
        try:
            integrations = fetch_entity_integrations(
                self._token,
                self._websocket_url,
            )
        except HomeAssistantAPIError:
            integrations = {}
        for entity in entities:
            entity["integration"] = integrations.get(
                entity["entity_id"]
            ) or registry_integrations.get(
                entity["entity_id"]
            )
        generated_at = datetime.now(timezone.utc).isoformat()
        with self._cache_lock:
            updated = {entity["entity_id"]: entity for entity in entities}
            previous = self._cached_entities or {}
            if previous.keys() != updated.keys() or any(
                any(previous[entity_id].get(key) != entity.get(key) for key in ENTITY_CATALOG_FIELDS)
                for entity_id, entity in updated.items()
            ):
                self._metadata_revision += 1
            self._cached_entities = updated
            self._cached_generated_at = generated_at
            self._cached_complete_at_monotonic = time.monotonic()
            self._last_error = ""
            self._record_revision_locked(resync=True)
        return copy.deepcopy(entities), generated_at

    def refresh_room(self, room: str) -> dict[str, Any]:
        """Return one room from the shared live entity snapshot."""
        room = room.strip()
        if not room:
            raise ValueError("A valid room is required.")
        inventory = self.fetch(include_all=True, predicate=lambda entity: str(entity.get("area") or "") == room)
        room_entities = inventory["entities"]
        return {
            "generated_at": inventory["generated_at"],
            "room": room,
            "count": len(room_entities),
            "entities": room_entities,
            **{
                key: inventory.get(key)
                for key in (
                    "revision",
                    "live_connected",
                    "last_event_at",
                    "cache_age_seconds",
                    "stale",
                    "last_error",
                )
            },
        }

    def fetch_state(self, entity_id: str) -> dict[str, Any]:
        """Fetch one current Home Assistant entity state."""
        if not self._token:
            raise HomeAssistantAPIError(
                "The Home Assistant API token is unavailable."
            )
        state_url = f"{self._states_url.rstrip('/')}/{quote(entity_id, safe='')}"
        request = Request(
            state_url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except HTTPError as err:
            raise HomeAssistantAPIError(
                f"Home Assistant returned HTTP {err.code}."
            ) from err
        except (URLError, TimeoutError, json.JSONDecodeError) as err:
            raise HomeAssistantAPIError(
                f"Unable to read {entity_id} from Home Assistant."
            ) from err
        if not isinstance(payload, dict):
            raise HomeAssistantAPIError(
                "Home Assistant returned an unexpected entity response."
            )
        return payload

    def fetch_lighting(self, package_path: Path = GENERATED_LIGHT_GROUP_PACKAGE) -> dict[str, Any]:
        """Return only lighting controls; security has its own live projection.

        Groups the generator no longer writes (an old All Lights that Home
        Assistant still remembers) stay hidden; lights in no group but the
        whole room's (Porch Light) show on their own.
        """
        shown = lighting_entity_ids(package_path)
        return self.fetch(
            include_all=True,
            predicate=(
                (lambda entity: str(entity.get("entity_id") or "").startswith("light.fht_"))
                if shown is None
                else (lambda entity: entity.get("entity_id") in shown)
            ),
        )

    def fetch_security(self) -> dict[str, Any]:
        """Return current door and opening states from the shared snapshot."""
        inventory = self.fetch(include_all=True, predicate=lambda entity: entity.get("domain") == "binary_sensor")
        entities = []
        for entity in inventory["entities"]:
            if entity.get("domain") != "binary_sensor":
                continue
            device_class = str(entity.get("device_class") or "").lower()
            searchable_name = " ".join(
                str(entity.get(key) or "")
                for key in ("friendly_name", "entity_id")
            ).replace("_", " ").lower()
            explicit_door_sensor = "door sensor" in searchable_name
            detection_entity = any(
                term in searchable_name
                for term in ("detected", "detection", "doorbell")
            )
            diagnostic_entity = (
                device_class in {"battery", "moisture", "problem"}
                or any(
                    term in searchable_name
                    for term in ("battery", "moisture", "tamper")
                )
            )
            if detection_entity or diagnostic_entity or (
                device_class not in {"door", "opening", "garage_door"}
                and not explicit_door_sensor
            ):
                continue
            entities.append(entity)
        return {
            "generated_at": inventory["generated_at"],
            "count": len(entities),
            "entities": entities,
            **{
                key: inventory.get(key)
                for key in (
                    "revision",
                    "live_connected",
                    "last_event_at",
                    "cache_age_seconds",
                    "stale",
                    "last_error",
                )
            },
        }


@lru_cache(maxsize=4)
def interface_bundle(web_root: str, modified_ns: int, size: int) -> dict[str, Any]:
    """Build independently cacheable assets from the maintained UI source."""
    source = Path(web_root, "index.html").read_text(encoding="utf-8")
    assets = {}
    for tag, pattern, content_type in (
        ("css", r'<style nonce="__FHT_CSP_NONCE__">(.*?)</style>', "text/css; charset=utf-8"),
        ("js", r'<script type="module" nonce="__FHT_CSP_NONCE__">(.*?)</script>', "text/javascript; charset=utf-8"),
    ):
        match = re.search(pattern, source, re.DOTALL)
        if not match:
            raise ValueError(f"The interface {tag} source is missing.")
        asset_source = match.group(1)
        if tag == "js":
            asset_source = "if (!window.fhtKioskRedirecting) {\n" + asset_source + "\n}"
        content = asset_source.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        filename = f"interface-{digest[:16]}.{tag}"
        assets[f"/{filename}"] = {
            "content": content,
            "gzip": gzip.compress(content, compresslevel=6),
            "content_type": content_type,
            "etag": f'"{digest}"',
        }
        replacement = (
            f'<link rel="stylesheet" href="{filename}">'
            if tag == "css"
            else f'<script type="module" src="{filename}"></script>'
        )
        source = source[:match.start()] + replacement + source[match.end():]
    return {"html": source, "assets": assets}


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server with a strict concurrent-request ceiling."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler: type[BaseHTTPRequestHandler],
        max_workers: int = HTTP_MAX_WORKERS,
    ) -> None:
        self._worker_slots = threading.BoundedSemaphore(max(1, max_workers))
        self.live_waiter_slots = threading.BoundedSemaphore(
            max(1, min(HTTP_MAX_LIVE_WAITERS, max_workers - 2))
        )
        super().__init__(server_address, request_handler)

    def process_request(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
    ) -> None:
        request.settimeout(HTTP_REQUEST_TIMEOUT_SECONDS)
        if not self._worker_slots.acquire(blocking=False):
            try:
                body = b'{"ok":false,"error":"Server request limit reached."}'
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Cache-Control: no-store\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                    + body
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._worker_slots.release()
            raise

    def process_request_thread(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()


class FutureHomesTechRequestHandler(BaseHTTPRequestHandler):
    """Serve the Ingress interface and entity inventory API."""

    inventory: EntityInventory
    access_store: ACCESS.AccessStore
    access_admin: ACCESS.AccessAdmin

    def _handle_maintenance(self, path, query, *, write=False):
        try:
            actor = self.access_admin.authenticate(self.client_address[0], self.ingress_proxy_ip, self.headers, fresh=write)
            service = self.maintenance
            if path == "/api/maintenance/retired":
                result = self._retired_entities(
                    self._read_json_object() if write else None,
                    actor if write else None,
                )
                self._send_json(HTTPStatus.OK, {"ok": True, **result})
                return
            if write:
                self.access_admin.check_csrf(actor, self.headers)
                payload = self._read_json_object()
                if path == "/api/maintenance/archive":
                    result = service.archive(payload, actor)
                elif path == "/api/maintenance/restore":
                    result = service.restore(payload)
                else:
                    raise MAINTENANCE.MaintenanceError("Unknown maintenance action.", 404)
            elif path == "/api/maintenance/review":
                result = service.review()
            elif path == "/api/maintenance/archives":
                result = service.archives()
            else:
                raise MAINTENANCE.MaintenanceError("Unknown maintenance page.", 404)
            self._send_json(HTTPStatus.OK, {"ok": True, **result})
        except (ACCESS.AccessError, MAINTENANCE.MaintenanceError) as error:
            self._send_json(HTTPStatus(error.status), {"ok": False, "error": str(error)})
        except RequestBodyTooLarge as error:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": str(error)})
        except (ValueError, TypeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid maintenance data. Reload and review before retrying."})
        except Exception as error:
            # Messages can contain credentials, so log only where it failed.
            frame = traceback.extract_tb(error.__traceback__)[-1] if error.__traceback__ else None
            where = f" at {Path(frame.filename).name}:{frame.lineno} in {frame.name}" if frame else ""
            print(f"[Maintenance] ERROR {path}: {error.__class__.__name__}{where}", flush=True)
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": f"Maintenance is unavailable ({error.__class__.__name__}). Details are in the App log. Check the connection or private recovery history before retrying a change."})

    ROOM_DEVICES_HIDDEN = re.compile(
        r"(?:^|\s)(?:firmware|identify|lqi|rssi|battery type|battery voltage|off transition time|on level"
        r"|on transition time|on off transition time|power on level)$"
        # Power-on behavior settings are hidden wherever the phrase appears.
        r"|(?:^|\s)power on behaviou?r(?:\s|$)"
    )

    def _room_devices(self) -> list[dict[str, Any]]:
        """Every entity grouped by room, for a quick per-room check."""
        entities = self.inventory.fetch(
            include_all=True,
            fields=("entity_id", "friendly_name", "area", "original_area", "state", "unit_of_measurement"),
        )["entities"]
        aliases = self.room_aliases.read()
        rooms: dict[str, list[dict[str, str]]] = {}
        for entity in entities:
            entity_id = str(entity.get("entity_id") or "")
            if not entity_id:
                continue
            # Zigbee/Z-Wave diagnostic and configuration entities are noise here.
            if any(
                self.ROOM_DEVICES_HIDDEN.search(re.sub(r"[\W_]+", " ", text).strip().casefold())
                for text in (str(entity.get("friendly_name") or ""), entity_id.partition(".")[2])
            ):
                continue
            area = str(entity.get("original_area") or entity.get("area") or "")
            # The Bridges room holds hubs and bridges, not room devices.
            if "bridges" in {area.strip().casefold(), str(aliases.get(area) or "").strip().casefold()}:
                continue
            rooms.setdefault(area, []).append({
                "entity_id": entity_id,
                "friendly_name": str(entity.get("friendly_name") or ""),
                "state": str(entity.get("state") or ""),
                "unit": str(entity.get("unit_of_measurement") or ""),
            })
        return sorted(
            (
                {
                    "area": area,
                    "name": aliases.get(area) or area or "Unassigned",
                    "entities": sorted(items, key=lambda item: (item["friendly_name"].casefold() or item["entity_id"], item["entity_id"])),
                }
                for area, items in rooms.items()
            ),
            key=lambda room: (not room["area"], room["name"].casefold()),
        )

    def _retired_entities(self, payload: dict[str, Any] | None, actor: Any) -> dict[str, Any]:
        """List retired App entities, or delete the approved ones."""
        config_directory = GENERATED_LIGHT_GROUP_PACKAGE.parent.parent
        entities = self.inventory.fetch(include_all=True, force=True)["entities"]
        try:
            found = self.registry_organizer.find_retired_managed_entities(entities, config_directory)
        except HomeAssistantAPIError as err:
            raise MAINTENANCE.MaintenanceError(str(err), 503) from err
        approvals = self.retired_approvals
        removed: list[str] = []
        if payload is not None:
            self.access_admin.check_csrf(actor, self.headers)
            requested = payload.get("entities", [])
            if not isinstance(requested, list) or not all(isinstance(item, str) for item in requested):
                raise MAINTENANCE.MaintenanceError("Choose the retired entities to delete.")
            # Only entities that still qualify right now are deleted.
            approved = [entry for entry in found if entry["entity_id"] in set(requested)]
            approvals.journal(approved)
            removed = self.registry_organizer.cleanup_retired_managed_entities(
                entities, config_directory, approved={entry["entity_id"] for entry in approved},
            )
            if "auto_remove" in payload:
                approvals.set_auto_remove(bool(payload["auto_remove"]))
            found = [entry for entry in found if entry["entity_id"] not in set(removed)]
            if removed:
                print(f"[Cleanup] Removed {len(removed)} approved retired entities: " + ", ".join(removed), flush=True)
        items = RetiredEntityApprovals.describe(found, entities)
        approvals.save_pending(items)
        return {"items": items, "removed": removed, "auto_remove": approvals.auto_remove()}

    load_ha_persons: Callable[[], Any] | None = None
    _ha_persons_lock = threading.Lock()
    _ha_persons_cache: tuple[float, list[dict[str, str]]] | None = None

    def _ha_persons(self) -> list[dict[str, str]] | None:
        """Return Home Assistant people for profile links, cached for a minute."""
        loader = type(self).load_ha_persons
        if loader is None:
            return None
        with self._ha_persons_lock:
            cached = type(self)._ha_persons_cache
            if cached and time.monotonic() - cached[0] < 60:
                return cached[1]
            try:
                result = loader()
            except Exception:
                return None
            people = [*result.get("storage", []), *result.get("config", [])] if isinstance(result, dict) else []
            persons = sorted(
                ({"id": str(item["id"]), "name": str(item.get("name") or item["id"])}
                 for item in people if isinstance(item, dict) and item.get("id")),
                key=lambda item: item["name"].casefold(),
            )
            type(self)._ha_persons_cache = (time.monotonic(), persons)
            return persons

    def _access_catalog(self) -> dict[str, Any]:
        structure = home_structure_from_storage(self.inventory._config_directory)
        aliases = self.room_aliases.read()
        rooms = [
            {"id": area["area_id"], "name": aliases.get(area["name"], area["name"]), "floor": floor["name"]}
            for floor in structure["floors"] for area in floor["areas"]
        ]
        with self.inventory._cache_lock:
            entities = list((self.inventory._cached_entities or {}).values())
        resources = [
            {"id": entity["entity_id"], "name": entity.get("friendly_name") or entity["entity_id"],
             "kind": "lock" if entity["entity_id"].startswith("lock.") else "door_sensor"}
            for entity in entities
            if entity["entity_id"].startswith("lock.") or is_door_sensor_entity(entity)
        ]
        persons = self._ha_persons()
        return {"rooms": sorted(rooms, key=lambda room: room["name"].casefold()),
                "resources": sorted(resources, key=lambda resource: resource["name"].casefold()),
                "ha_persons": persons or [], "ha_persons_available": persons is not None,
                "roles": ACCESS.ROLES, "role_defaults": ACCESS.ROLE_DEFAULTS,
                "capabilities": ACCESS.CAPABILITIES, "timezone": SITE_PROFILE.timezone,
                "physical_access_enabled": False, "panel_access_enabled": False}

    def _handle_access(self, path: str, query: dict[str, list[str]], *, write: bool = False) -> None:
        try:
            actor = self.access_admin.authenticate(self.client_address[0], self.ingress_proxy_ip, self.headers, fresh=write)
            if write:
                self.access_admin.check_csrf(actor, self.headers)
                payload = self._read_json_object()
                if path == "/api/access/pin/issue":
                    result = self.access_store.issue_pin(payload, actor)
                elif path == "/api/access/pin/revoke":
                    self.access_store.revoke_pin(payload, actor)
                    result = {}
                elif path == "/api/access/pin/test":
                    result = self.access_store.verify_pin(payload, actor)
                elif path == "/api/access/extension":
                    result = self.access_store.extension(payload, actor)
                elif path == "/api/access/reservations/move":
                    result = {"record": self.access_store.move_rooms(payload, actor, self._access_catalog())}
                elif path == "/api/access/review":
                    result = {"review": self.access_store.finish_review(payload, actor)}
                elif re.fullmatch(r"/api/access/(people|groups|reservations|panels)/(save|remove)", path):
                    collection, action = path.split("/")[-2:]
                    if action == "save":
                        result = {"record": self.access_store.save(collection, payload, actor, self._access_catalog())}
                    else:
                        self.access_store.remove(collection, payload, actor)
                        result = {}
                else:
                    raise ACCESS.AccessError("Unknown Users action.", 404)
            elif path == "/api/access/session":
                result = {"actor": actor, "csrf": self.access_admin.csrf(actor)}
            elif path == "/api/access/catalog":
                result = {**self._access_catalog(), "restore_review": self.access_store.review_status()}
            else:
                collection = path.removeprefix("/api/access/")
                if collection not in ACCESS.COLLECTIONS | {"activity"}:
                    raise ACCESS.AccessError("Unknown Users page.", 404)
                identifier = query.get("id", [""])[0]
                if identifier:
                    result = {"record": self.access_store.detail(collection, identifier)}
                else:
                    result = self.access_store.list_records(collection, query.get("search", [""])[0], query.get("offset", [0])[0], query.get("state", [""])[0])
            self._send_json(HTTPStatus.OK, {"ok": True, **result})
        except ACCESS.AccessError as error:
            self._send_json(HTTPStatus(error.status), {"ok": False, "error": str(error)})
        except RequestBodyTooLarge as error:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": str(error)})
        except (ValueError, TypeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid Users request. Reload and review the fields."})
        except Exception:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "Users data is unavailable. Check private storage and retry. No device action was sent."})
    _catalog_lock = threading.Lock()
    _catalog_cached_key = None
    _catalog_cached_payload = None

    def _catalog_revision(self) -> str:
        dependencies = [
            id(self.inventory),
            self.inventory._freshness_payload().get("metadata_revision", 0),
            self.bedroom_modes.read(), self.wake_routines.read(),
            self.switch_control_settings.read(), self.room_aliases.read(), self.room_modes.read(),
        ]
        return hashlib.sha256(json.dumps(dependencies, sort_keys=True).encode()).hexdigest()

    def _phone_notify_payload(self, entities: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the phones alerts can go to, and why the list is empty if it is."""
        try:
            services = self.phone_notify_services.fetch()
        except HomeAssistantAPIError as err:
            return {"phone_targets": [], "phone_targets_error": str(err)}
        return {
            "phone_targets": phone_notify_catalog(services, entities),
            "phone_targets_error": None,
        }

    @staticmethod
    def _require_known_phones(raw: Any, known: set[str] | None) -> list[str]:
        """Validate chosen phones against the phones Home Assistant offers now."""
        targets = phone_notify_targets(raw)
        if known is not None and any(service not in known for service in targets):
            raise ValueError(
                "A phone signed in to the Home Assistant Companion app is required."
            )
        return targets

    def _shared_editor_catalog(self) -> dict[str, Any]:
        owner = type(self)
        with owner._catalog_lock:
            self.inventory._ensure_snapshot()
            revision = self._catalog_revision()
            key = (id(self.inventory), revision)
            if owner._catalog_cached_key != key:
                entities = self.inventory.fetch(include_all=True, fields=ENTITY_CATALOG_FIELDS)["entities"]
                owner._catalog_cached_payload = {
                    "revision": revision,
                    "action_catalog": self._shared_action_catalog(entities),
                    "wake_catalog": self._wake_routine_catalog(entities, self.wake_routines.read()),
                    "toddler_entities": self._toddler_entity_catalog(entities),
                    "alarm_targets": fridge_alarm_output_catalog(entities),
                }
                owner._catalog_cached_key = key
            return owner._catalog_cached_payload
    button_inventory: ButtonDeviceInventory
    protect_api: ProtectAPI
    app_info: SupervisorAppInfo
    beta_channel: Any
    retired_approvals: "RetiredEntityApprovals"
    switch_assignments: SwitchLightGroupAssignments
    switch_control_settings: SwitchControlSettings
    fridge_alarm_settings: FridgeAlarmSettings
    fridge_alarm_automations: FridgeAlarmAutomationManager
    door_open_alert_settings: DoorOpenAlertSettings
    door_open_alert_automations: DoorOpenAlertAutomationManager
    future_tech_portal: FutureTechPortalManager
    phone_notify_services: PhoneNotifyServices
    presence_assignments: PresenceLightGroupAssignments
    presence_groups: PresenceGroupManager
    presence_timings: PresenceTimingSettings
    presence_mode_settings: PresenceModeSettings
    presence_automations: PresenceAutomationManager
    light_schedules: LightScheduleSettings
    light_schedule_automations: LightScheduleAutomationManager
    room_modes: RoomModeSettings
    bedroom_modes: BedroomModeSettings
    room_scenes: RoomSceneSettings
    room_scene_automations: RoomSceneAutomationManager
    bedroom_mode_automations: BedroomModeAutomationManager
    wake_routines: WakeRoutineSettings
    wake_routine_automations: WakeRoutineAutomationManager
    homekit_light_groups: HomeKitLightGroupSelection
    room_aliases: RoomAliases
    control_automations: ControlAutomationManager
    door_assignments: DoorLightGroupAssignments
    door_automations: DoorAutomationManager
    configuration_publisher: HomeAssistantHelperPublisher
    registry_organizer: HomeAssistantRegistryOrganizer
    web_root: Path
    ingress_proxy_ip: str
    allow_non_ingress: bool

    @staticmethod
    def _normalized_helper_state(
        entities_by_id: dict[str, dict[str, Any]],
        entity_id: str,
        fallback: str,
    ) -> str:
        state = str(
            (entities_by_id.get(entity_id) or {}).get("state") or fallback
        ).strip()
        return fallback if state.casefold() in {"", "none", "unknown", "unavailable"} else state

    @staticmethod
    def _room_mode_type(area: str) -> str:
        name = str(area or "").casefold()
        for room_type in RoomModeSettings.CATALOG:
            if room_type in name:
                return room_type
        return ""

    @staticmethod
    def _visible_room_mode(
        mode_type: str,
        current_mode: str,
        enabled_modes: list[str],
    ) -> str:
        """Expose an active bedroom mode only when the homeowner enabled it."""
        if mode_type != "bedroom":
            return ""
        labels = {
            mode: label
            for mode, label in RoomModeSettings.AVAILABLE_MODES
        }
        enabled_labels = {
            labels[mode].casefold()
            for mode in enabled_modes
            if mode in labels
        }
        return current_mode if current_mode.casefold() in enabled_labels else ""

    def _shared_action_catalog(
        self,
        entities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return one action catalog for every editor in the interface."""
        all_entities = entities if entities is not None else self.inventory.fetch(include_all=True)["entities"]
        bedroom_settings = self.bedroom_modes.read()
        wake_settings = self.wake_routines.read()
        control_settings = self.switch_control_settings.read()
        return action_catalog_from_entities(
            all_entities,
            bedroom_areas=sorted(set(bedroom_settings) | set(self.room_modes.read())),
            wake_areas=list(wake_settings),
            saved_actions=control_settings.get("action_assignments", {}),
            enabled_room_modes=self.room_modes.read(),
            generated_group_ids=generated_light_group_entity_ids(),
            group_replacements=generated_light_group_replacements(),
        )

    @staticmethod
    def _toddler_entity_catalog(
        entities: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Return capability targets used by bedroom Toddler Mode."""

        def searchable(entity: dict[str, Any]) -> str:
            return " ".join(
                filter(
                    None,
                    (
                        str(entity.get("friendly_name") or ""),
                        str(entity.get("device_name") or ""),
                        str(entity.get("entity_id") or "").replace("_", " "),
                    ),
                )
            )

        return {
            "lights": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith("light.")
            ],
            "chimes": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith("button.")
                and re.search(
                    r"\b(chime|ring|play|sound|siren)\b",
                    searchable(entity),
                    flags=re.IGNORECASE,
                )
            ],
            "indicator_effects": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith("select.")
                and re.search(
                    r"\b(inovelli|led|indicator|effect|notification)\b",
                    searchable(entity),
                    flags=re.IGNORECASE,
                )
            ],
            "indicator_colors": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith(
                    ("number.", "select.")
                )
                and re.search(
                    r"\b(inovelli|led|indicator|notification)\b.*\bcolor\b|"
                    r"\bcolor\b.*\b(inovelli|led|indicator|notification)\b",
                    searchable(entity),
                    flags=re.IGNORECASE,
                )
            ],
            "indicator_brightness": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith("number.")
                and re.search(
                    r"\b(inovelli|led|indicator|notification)\b.*"
                    r"\b(brightness|level)\b|\b(brightness|level)\b.*"
                    r"\b(inovelli|led|indicator|notification)\b",
                    searchable(entity),
                    flags=re.IGNORECASE,
                )
            ],
        }

    def _wake_routine_catalog(
        self,
        entities: list[dict[str, Any]],
        settings: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Return shared wake-routine targets without another API request."""
        return {
            "days": list(WakeRoutineSettings.DAYS),
            "lights": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith("light.")
                and not str(entity.get("entity_id") or "").startswith(
                    LIGHT_GROUP_ENTITY_PREFIX
                )
            ],
            "light_groups": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith(
                    LIGHT_GROUP_ENTITY_PREFIX
                )
            ],
            "media_players": [
                entity
                for entity in entities
                if str(entity.get("entity_id") or "").startswith(
                    "media_player."
                )
            ],
            "room_mode_catalog": self.room_modes.catalog(),
            "room_mode_settings": self.room_modes.read(),
            "override_targets": {
                area: WakeRoutineAutomationManager.override_button(area)
                for area in settings
            },
        }

    def _door_open_alert_payload(self) -> dict[str, Any]:
        """Return door and window sensors grouped by room with their reminders."""
        settings = self.door_open_alert_settings.read()
        inventory = self.inventory.fetch(include_all=True)
        entities = inventory["entities"]
        stale = bool(inventory.get("stale"))
        aliases = self.room_aliases.read()
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity for entity in entities
        }
        sensors: dict[str, dict[str, Any]] = {}
        for entity in entities:
            if not is_door_sensor_entity(entity) or is_refrigerator_entity(entity):
                continue
            entity_id = str(entity.get("entity_id") or "").strip()
            if entity_id:
                sensors[entity_id] = entity
        for entity_id, setting in settings.items():
            if setting["enabled"] and entity_id not in sensors:
                sensors[entity_id] = {"entity_id": entity_id, "missing": True}
        rooms: dict[str, dict[str, Any]] = {}
        for entity_id, sensor in sensors.items():
            area = str(sensor.get("area") or "").strip()
            room = rooms.setdefault(
                area,
                {
                    "area": area,
                    "display_name": aliases.get(area) or area or "Unassigned",
                    "sensors": [],
                },
            )
            room["sensors"].append(
                {
                    "entity_id": entity_id,
                    "display_name": door_open_alert_display_name(sensor),
                    "friendly_name": str(sensor.get("friendly_name") or entity_id),
                    "state": "unavailable" if stale else sensor.get("state", "unavailable"),
                    "missing": bool(sensor.get("missing")),
                }
            )
        for room in rooms.values():
            room["sensors"].sort(key=lambda sensor: sensor["display_name"].casefold())
        return {
            "ok": True,
            "door_open_alerts": {
                "rooms": sorted(
                    rooms.values(),
                    key=lambda room: (not room["area"], room["display_name"].casefold()),
                ),
                "settings": device_alarm_buzzer_settings(settings, entities),
                "alarm_targets": fridge_alarm_output_catalog(entities),
                "webhook_configured": device_alarm_webhook_configured(),
                "house_mode": self._normalized_helper_state(
                    entities_by_id, HOUSE_MODE_HELPER, "Day"
                ),
                "stale": stale,
            },
        }

    def _room_modes_payload(self) -> dict[str, Any]:
        settings = self.room_modes.read()
        index = self._home_configurator_index()
        rooms = [
            room
            for floor in index["floors"]
            for room in floor["rooms"]
            if room.get("mode_type") == "bedroom" or settings.get(room["name"])
        ]
        rooms.sort(key=lambda room: room["display_name"].casefold())
        return {
            "ok": True,
            "rooms": rooms,
            "catalog": self.room_modes.catalog(),
            "settings": settings,
            "current_modes": {room["name"]: room["current_mode"] for room in rooms},
            "house_settings": index["house_settings"],
        }

    def _room_scenes_payload(self) -> dict[str, Any]:
        modes = self._room_modes_payload()
        settings = self.room_scenes.read()
        labels = dict(RoomModeSettings.AVAILABLE_MODES)
        return {
            "ok": True,
            "catalog_revision": self._catalog_revision(),
            "scenes": [
                {
                    "area": room["name"],
                    "display_name": room["display_name"],
                    "mode": mode,
                    "label": labels[mode],
                    "settings": RoomSceneSettings.normalize(settings.get(room["name"], {}).get(mode, {})),
                    "configured": bool(settings.get(room["name"], {}).get(mode, {}).get("targets")),
                }
                for room in modes["rooms"]
                for mode in modes["settings"].get(room["name"], [])
                if mode in labels
            ],
        }

    def _home_configurator_index(self) -> dict[str, Any]:
        """Return a small registry-driven Floor and Area index."""
        structure = home_structure_from_storage(
            self.inventory._config_directory
        )
        aliases = self.room_aliases.read()
        inventory = self.inventory.peek(include_all=True, fields=("entity_id", "domain", "area", "floor", "state"))
        entities = inventory["entities"]
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity
            for entity in entities
        }
        entity_counts: dict[str, int] = {}
        entity_floor_by_area: dict[str, str] = {}
        for entity in entities:
            area = str(entity.get("original_area") or entity.get("area") or "").strip()
            if not area:
                continue
            entity_counts[area] = entity_counts.get(area, 0) + 1
            if entity.get("floor") and area not in entity_floor_by_area:
                entity_floor_by_area[area] = str(entity["floor"])

        excluded = HIDDEN_SETUP_AREAS
        indexed_areas: set[str] = set()
        floors: list[dict[str, Any]] = []
        bedroom_settings = self.bedroom_modes.read()
        room_mode_settings = self.room_modes.read()
        for floor in structure["floors"]:
            rooms = []
            for area in floor.get("areas", []):
                room = str(area.get("name") or "").strip()
                if not room or room.casefold() in excluded:
                    continue
                indexed_areas.add(room)
                helper = (
                    f"input_select.fht_{BedroomModeAutomationManager._slug(room)}_mode"
                )
                mode_type = self._room_mode_type(
                    f"{room} {aliases.get(room, '')}"
                )
                current_mode = self._visible_room_mode(
                    mode_type,
                    self._normalized_helper_state(
                        entities_by_id,
                        helper,
                        "",
                    ),
                    room_mode_settings.get(room, []),
                )
                rooms.append(
                    {
                        "area_id": str(area.get("area_id") or ""),
                        "name": room,
                        "display_name": aliases.get(room) or room,
                        "entity_count": entity_counts.get(room, 0),
                        "current_mode": current_mode,
                        "mode_type": mode_type,
                        "configured": (
                            room in bedroom_settings
                            or room in room_mode_settings
                        ),
                    }
                )
            rooms.sort(key=lambda room: room["display_name"].casefold())
            floors.append(
                {
                    "floor_id": str(floor.get("floor_id") or ""),
                    "name": str(floor.get("name") or "Unassigned"),
                    "level": floor.get("level"),
                    "rooms": rooms,
                }
            )

        for room in sorted(set(entity_counts) - indexed_areas, key=str.casefold):
            if room.casefold() in excluded:
                continue
            floor_name = entity_floor_by_area.get(room, "Unassigned")
            floor = next(
                (item for item in floors if item["name"] == floor_name),
                None,
            )
            if floor is None:
                floor = {
                    "floor_id": "",
                    "name": floor_name,
                    "level": None,
                    "rooms": [],
                }
                floors.append(floor)
            mode_type = self._room_mode_type(
                f"{room} {aliases.get(room, '')}"
            )
            floor["rooms"].append(
                {
                    "area_id": "",
                    "name": room,
                    "display_name": aliases.get(room) or room,
                    "entity_count": entity_counts.get(room, 0),
                    "current_mode": self._visible_room_mode(
                        mode_type,
                        self._normalized_helper_state(
                            entities_by_id,
                            f"input_select.fht_{BedroomModeAutomationManager._slug(room)}_mode",
                            "",
                        ),
                        room_mode_settings.get(room, []),
                    ),
                    "mode_type": mode_type,
                    "configured": (
                        room in bedroom_settings or room in room_mode_settings
                    ),
                }
            )

        for floor in floors:
            floor["rooms"].sort(
                key=lambda room: room["display_name"].casefold()
            )
        floors.sort(key=home_configurator_floor_sort_key)

        house_mode = self._normalized_helper_state(
            entities_by_id,
            HOUSE_MODE_HELPER,
            "Unknown",
        ).title()
        protect_mode = self._normalized_helper_state(
            entities_by_id,
            PROTECT_STATUS_HELPER,
            "Unknown",
        )
        if protect_mode.casefold() in {"disabled", "disarmed"}:
            security_mode = "Disarmed"
        elif protect_mode == "Unknown":
            security_mode = "Unknown"
        else:
            security_mode = "Armed"
        return {
            "floors": floors,
            "floor_count": len(floors),
            "room_count": sum(len(floor["rooms"]) for floor in floors),
            "house_mode": house_mode,
            "security_mode": security_mode,
            "house_settings": self.bedroom_mode_automations.house_settings(),
            "sleep_mode_options": [
                {
                    "entity_id": (
                        f"input_select.fht_{BedroomModeAutomationManager._slug(area)}_mode"
                    ),
                    "label": aliases.get(area) or area,
                    "floor_id": next((floor.get("floor_id", "") for floor in floors if any(room["name"] == area for room in floor["rooms"])), ""),
                }
                for area in sorted(
                    (
                        area
                        for area in {room["name"] for floor in floors for room in floor["rooms"]}
                        if "sleep" in room_mode_settings.get(area, [])
                        and self._room_mode_type(f"{area} {aliases.get(area, '')}") == "bedroom"
                        and not any(
                            word in f"{area} {aliases.get(area, '')}".casefold()
                            for word in SLEEP_SOURCE_EXCLUDED_WORDS
                        )
                    ),
                    key=lambda area: (aliases.get(area) or area).casefold(),
                )
            ],
            **{
                key: inventory.get(key)
                for key in (
                    "revision",
                    "live_connected",
                    "last_event_at",
                    "cache_age_seconds",
                    "stale",
                    "last_error",
                )
            },
        }

    def _door_mode_options(self, room: str) -> list[dict[str, str]]:
        return self._door_mode_options_by_room([room])[room]

    def _door_mode_options_by_room(self, rooms: list[str]) -> dict[str, list[dict[str, str]]]:
        """Door mode choices per room, reading the registries and room modes once."""
        structure = home_structure_from_storage(self.inventory._config_directory)
        floors = [floor for floor in structure.get("floors", []) if floor.get("floor_id")]
        room_modes = self.room_modes.read()
        options_by_room: dict[str, list[dict[str, str]]] = {}
        for room in rooms:
            options = [{"id": "day", "label": "Day"}, {"id": "night", "label": "Night"}, {"id": "sleep", "label": "Whole Home Sleep"}]
            for floor in floors:
                if any(area.get("name") == room for area in floor.get("areas", [])):
                    options.append({"id": "floor:" + floor["floor_id"], "label": floor["name"] + " Sleep"})
            slug = BedroomModeAutomationManager._slug(room)
            for mode in room_modes.get(room, []):
                options.append({"id": f"room:{slug}:{mode}", "label": mode.replace("_", " ").title() + " Mode"})
            options_by_room[room] = options
        return options_by_room

    def _room_controls(self, kind: str, room: str | None = None) -> dict[str, Any]:
        if kind not in {"doors", "switches", "presence"}:
            raise ValueError("Choose Doors or Switches.")

        def includes(entity: dict[str, Any]) -> bool:
            if room is not None and str(entity.get("area") or "") != room:
                return False
            if kind == "doors":
                return is_door_sensor_entity(entity)
            if kind == "presence":
                return entity.get("domain") == "binary_sensor"
            return entity.get("domain") in {"switch", "event"}

        fields = (
            "entity_id", "domain", "area", "original_area", "device_id", "device_name",
            "friendly_name", "original_name", "state", "device_class", "members",
        ) if room is None and kind != "switches" else None
        inventory = self.inventory.fetch(include_all=True, predicate=includes, fields=fields)
        if kind == "presence":
            # Camera motion is too unreliable for presence, so cameras are left out.
            camera_devices = camera_device_ids(self.inventory.fetch(
                include_all=True, predicate=lambda entity: str(entity.get("entity_id") or "").startswith("camera."),
                fields=("entity_id", "device_id"),
            )["entities"])
            inventory = {**inventory, "entities": [
                entity for entity in inventory["entities"] if not is_camera_entity(entity, camera_devices)
            ]}
        aliases = self.room_aliases.read()
        settings = {"assignments": self.switch_assignments.read(), **self.switch_control_settings.read()}
        presence = {
            "assignments": self.presence_assignments.read(),
            "timings": self.presence_timings.read(),
            "mode_settings": self.presence_mode_settings.read(),
        } if kind == "presence" else {}
        if room is None:
            # One snapshot carries every room, so the page renders each card
            # without a request per room.
            payload = {**inventory, "aliases": aliases, "rooms_ready": True,
                       "catalog_revision": self._catalog_revision(), "control_settings": settings}
            if kind == "switches":
                payload["humidity_sensors"] = self._room_humidity_sensors()
                payload["presence_sensors"] = self._room_presence_sensors()
                return payload
            # Keyed by the Home Assistant area name, which is what the page groups by;
            # "area" already carries the display name once aliases are applied.
            rooms = sorted({str(entity.get("original_area") or entity.get("area") or "") for entity in inventory["entities"]})
            room_modes = self.room_modes.read()
            payload["presence"] = presence
            payload["enabled_room_modes_by_room"] = {name: room_modes.get(name, []) for name in rooms}
            if kind == "doors":
                payload["door_mode_options_by_room"] = self._door_mode_options_by_room(rooms)
            return payload
        entity_ids = {str(entity.get("entity_id") or "") for entity in inventory["entities"]}
        return {
            **inventory,
            "presence": presence,
            "enabled_room_modes": self.room_modes.read().get(room, []) if kind in {"presence", "doors"} else [],
            "door_mode_options": self._door_mode_options(room) if kind == "doors" else [],
            "room": room,
            "display_name": aliases.get(room) or room or "Unassigned",
            "catalog_revision": self._catalog_revision(),
            "door_sensors": inventory["entities"] if kind == "doors" else [],
            "humidity_sensors": self._room_humidity_sensors(room) if kind == "switches" else [],
            "presence_sensors": self._room_presence_sensors(room) if kind == "switches" else [],
            "control_settings": {
                field: {
                    key: value for key, value in values.items()
                    if str(key).removeprefix("door:").split("|", 1)[0] in entity_ids
                }
                for field, values in settings.items() if isinstance(values, dict)
            },
        }

    def _room_presence_sensors(self, room: str | None = None) -> list[dict[str, Any]]:
        """Return the presence sensors an exhaust fan can follow, with cameras left out."""
        inventory = self.inventory.fetch(
            include_all=True,
            predicate=lambda entity: (
                str(entity.get("entity_id") or "").startswith(("binary_sensor.", "camera."))
                and (room is None or str(entity.get("area") or "") == room)
            ),
            fields=("entity_id", "friendly_name", "state", "area", "device_class", "device_id", "device_name"),
        )
        return ExhaustFanPresence.sensors(inventory["entities"], room)

    def _room_humidity_sensors(self, room: str | None = None) -> list[dict[str, Any]]:
        """Return the humidity sensors Switches rooms can pair with an exhaust fan."""
        inventory = self.inventory.fetch(
            include_all=True,
            predicate=lambda entity: ExhaustFanHumidity.is_sensor(entity) and (room is None or str(entity.get("area") or "") == room),
            fields=("entity_id", "friendly_name", "state", "area", "device_class", "unit_of_measurement"),
        )
        return ExhaustFanHumidity.sensors(inventory["entities"], room)

    def _home_configurator_room(self, room: str) -> dict[str, Any]:
        """Return all settings required to render one selected room."""
        room_inventory = self.inventory.refresh_room(room)
        room_entities = room_inventory["entities"]
        all_entities = self.inventory.fetch(include_all=True, predicate=lambda entity: entity.get("domain") == "input_select")["entities"]
        aliases = self.room_aliases.read()
        control_settings = self.switch_control_settings.read()
        room_modes = self.room_modes.read()
        bedroom_modes = self.bedroom_modes.read()
        wake_routines = self.wake_routines.read()
        presence_assignments = self.presence_assignments.read()
        presence_timings = self.presence_timings.read()
        presence_mode_settings = self.presence_mode_settings.read()
        discovery = self.button_inventory.peek()
        buttons = [
            button
            for button in discovery["buttons"]
            if str(button.get("area") or "Other") == room
        ]
        entities_by_id = {
            str(entity.get("entity_id") or ""): entity
            for entity in all_entities
        }
        is_fridge_room = any(
            is_device_alarm_room_name(value)
            for value in (room, aliases.get(room))
        )
        fridge_devices = fridge_alarm_catalog(room_entities) if is_fridge_room else []
        fridge_entity_ids = {
            str(sensor.get("entity_id") or "")
            for device in fridge_devices
            for key in ("temperature_sensors", "door_sensors")
            for sensor in device[key]
        }
        saved_fridge_settings = (
            self.fridge_alarm_settings.read() if fridge_entity_ids else {}
        )
        fridge_settings = {
            entity_id: setting
            for entity_id, setting in saved_fridge_settings.items()
            if entity_id in fridge_entity_ids
        }
        room_helper = (
            f"input_select.fht_{BedroomModeAutomationManager._slug(room)}_mode"
        )
        mode_type = self._room_mode_type(
            f"{room} {aliases.get(room, '')}"
        )
        enabled_room_modes = room_modes.get(room, [])
        room_ids = {str(entity.get("entity_id") or "") for entity in room_entities}
        device_ids = {str(button.get("device_id") or "") for button in buttons}
        device_ids.update(str(entity.get("device_id") or "") for entity in room_entities)
        device_ids.discard("")

        def room_assignments(values):
            return {key: value for key, value in values.items()
                    if str(key).removeprefix("door:").split("|", 1)[0] in room_ids
                    or (str(key).startswith("button:") and str(key)[7:].split("|", 1)[0] in device_ids)}

        return {
            **room_inventory,
            "display_name": aliases.get(room) or room,
            "alias": aliases.get(room) or "",
            "mode_type": mode_type,
            "current_mode": self._visible_room_mode(
                mode_type,
                self._normalized_helper_state(
                    entities_by_id,
                    room_helper,
                    "",
                ),
                enabled_room_modes,
            ),
            "buttons": buttons,
            "buttons_pending": discovery["pending"],
            "catalog_revision": self._catalog_revision(),
            "control_settings": {
                "assignments": room_assignments(self.switch_assignments.read()),
                **{key: room_assignments(value) if isinstance(value, dict) else value
                   for key, value in control_settings.items()},
            },
            "presence": {
                "assignments": room_assignments(presence_assignments),
                "timings": room_assignments(presence_timings),
                "mode_settings": room_assignments(presence_mode_settings),
            },
            "bedroom_mode": bedroom_modes.get(room, {}),
            "wake_routine": wake_routines.get(room, {}),
            "door_sensors": [
                entity
                for entity in room_entities
                if is_door_sensor_entity(entity)
            ],
            "fridge_alarms": {
                "devices": fridge_devices,
                "settings": fridge_settings,
            },
            "house_mode": self._normalized_helper_state(
                entities_by_id,
                HOUSE_MODE_HELPER,
                "Unknown",
            ).title(),
            "webhooks": {
                "armed_away": bool(
                    os.environ.get("BEDROOM_ARMED_AWAY_WEBHOOK", "").strip()
                ),
                "armed_stay_kids": bool(
                    os.environ.get(
                        "BEDROOM_ARMED_STAY_KIDS_WEBHOOK",
                        "",
                    ).strip()
                ),
            },
        }

    def do_GET(self) -> None:
        """Serve the interface or health status."""
        if not self._request_is_allowed():
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "Ingress access required."},
            )
            return

        parsed_path = urlsplit(self.path)
        path = parsed_path.path
        if path.startswith("/api/maintenance/"):
            self._handle_maintenance(path, parse_qs(parsed_path.query))
            return
        if path.startswith("/api/access/"):
            self._handle_access(path, parse_qs(parsed_path.query))
            return
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "future_homes_tech_app",
                    "running_version": os.environ.get("FHT_RUNNING_VERSION", ""),
                    "inventory": self.inventory._freshness_payload(),
                },
            )
            return
        if path == "/api/settings/history":
            try:
                page = str(parse_qs(parsed_path.query).get("page", [""])[0])
                entries = (
                    SETTINGS_HISTORY.page_entries(page, self._settings_store_paths()) if page
                    else SETTINGS_HISTORY.all_entries(self._settings_store_paths())
                )
            except ValueError as err:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(err)})
                return
            except OSError:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": "Unable to read the saved settings history."},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True, "page": page, "entries": entries})
            return
        if path == "/api/live/revision":
            slots = self.server.live_waiter_slots
            if not slots.acquire(blocking=False):
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {
                    "ok": False, "error": "Live update capacity reached. Retrying shortly.",
                })
                return
            try:
                query = parse_qs(parsed_path.query)
                after_revision = int(query.get("after", ["0"])[0])
                timeout = float(query.get("timeout", ["25"])[0])
                update = self.inventory.wait_for_revision(
                    after_revision,
                    timeout,
                )
            except (TypeError, ValueError) as err:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": f"Invalid live revision request: {err}"},
                )
                return
            finally:
                slots.release()
            self._send_json(HTTPStatus.OK, {"ok": True, **update})
            return
        if path == "/api/menu/status":
            inventory = self.inventory.peek(include_all=True, predicate=lambda entity: entity.get("domain") == "climate", fields=("entity_id", "domain", "state"))
            self._send_json(HTTPStatus.OK, {
                "ok": True,
                "climate_offline": sum(
                    entity.get("domain") == "climate"
                    and str(entity.get("state") or "").casefold() in {"unknown", "unavailable"}
                    for entity in inventory["entities"]
                ),
                "stale": inventory["stale"],
            })
            return
        if path == "/api/home-configurator/index":
            try:
                payload = self._home_configurator_index()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True, **payload})
            return
        if path == "/api/room-controls":
            try:
                query = parse_qs(parsed_path.query, keep_blank_values=True)
                payload = self._room_controls(query.get("kind", [""])[0], query.get("room", [None])[0])
                self._send_json(HTTPStatus.OK, {"ok": True, **payload})
            except ValueError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
            except HomeAssistantAPIError as error:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if path in {"/api/home-configurator/catalog", "/api/home-configurator/buttons", "/api/buttons"}:
            try:
                if path.endswith("/catalog"):
                    payload = self._shared_editor_catalog()
                else:
                    room = str(parse_qs(parsed_path.query).get("room", [""])[0])
                    payload = {"buttons": [button for button in self.button_inventory.fetch()
                                           if path == "/api/buttons" or str(button.get("area") or "Other") == room]}
                    device_ids = {str(button.get("device_id") or "") for button in payload["buttons"]}
                    event_ids = {entity_id for button in payload["buttons"] for entity_id in button.get("event_entity_ids", [])}
                    settings = {"assignments": self.switch_assignments.read(), **self.switch_control_settings.read()}
                    payload["control_settings"] = {
                        field: {key: value for key, value in values.items()
                                if (str(key).startswith("button:") and str(key)[7:].split("|", 1)[0] in device_ids)
                                or str(key).split("|", 1)[0] in event_ids}
                        for field, values in settings.items() if isinstance(values, dict)
                    }
                self._send_json(HTTPStatus.OK, {"ok": True, **payload})
            except HomeAssistantAPIError as error:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if path == "/api/home-configurator/room":
            try:
                query = parse_qs(parsed_path.query)
                room = str(query.get("room", [""])[0]).strip()
                if not room:
                    raise ValueError("A valid room is required.")
                payload = self._home_configurator_room(room)
            except ValueError as err:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": str(err)},
                )
                return
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True, **payload})
            return
        if path == "/api/lighting/status":
            try:
                inventory = self.inventory.fetch_lighting()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True, **inventory})
            return
        if path == "/api/security/status":
            try:
                inventory = self.inventory.fetch_security()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True, **inventory})
            return
        if path == "/api/weather/temperature":
            try:
                weather = self.inventory.fetch_state(
                    DEFAULT_WEATHER_ENTITY
                )
                attributes = weather.get("attributes") or {}
                temperature = attributes.get(
                    "temperature",
                    attributes.get("current_temperature"),
                )
                unit = attributes.get("temperature_unit")
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "entity_id": DEFAULT_WEATHER_ENTITY,
                    "temperature": temperature,
                    "unit": unit,
                },
            )
            return
        if path == "/api/protect/arm-mode":
            try:
                arm_mode = self.protect_api.fetch_arm_mode()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, **arm_mode},
            )
            return
        if path == "/api/protect/nvr-object":
            try:
                nvr_object = self.protect_api.fetch_nvr_object()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True, **nvr_object})
            return
        if path == "/api/protect/resources":
            try:
                resources = self.protect_api.fetch_resource_inventory()
                home_assistant_devices = protect_device_links_from_storage()
                current_entities = {
                    entity["entity_id"]: entity
                    for entity in self.inventory.fetch(include_all=True)[
                        "entities"
                    ]
                }
                seen_links: set[int] = set()
                for link in home_assistant_devices.values():
                    if id(link) in seen_links:
                        continue
                    seen_links.add(id(link))
                    for entity in link["entities"]:
                        current = current_entities.get(entity["entity_id"], {})
                        entity["friendly_name"] = (
                            current.get("friendly_name")
                            or entity["entity_id"]
                        )
                        entity["state"] = current.get("state", "unknown")
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "resources": resources,
                    "home_assistant_devices": home_assistant_devices,
                },
            )
            return
        if path == "/api/room-devices":
            try:
                self._send_json(HTTPStatus.OK, {"ok": True, "rooms": self._room_devices()})
            except HomeAssistantAPIError as err:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(err)})
            return
        # ?force=1 (opening the App) checks GitHub sooner than the regular polls.
        beta_force = parse_qs(parsed_path.query).get("force", [""])[0] == "1"
        if path == "/api/beta/status":
            self._send_json(HTTPStatus.OK, {"ok": True, **self.beta_channel.status(force=beta_force)})
            return
        if path == "/api/app-info":
            try:
                app_info = self.app_info.fetch()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    **app_info,
                    **self.beta_channel.status(force=beta_force),
                    "site_profile": SITE_PROFILE.describe(),
                },
            )
            return
        if path == "/api/site-profile":
            # Read-only: the file is edited by hand and read when the App starts.
            self._send_json(HTTPStatus.OK, {"ok": True, **SITE_PROFILE.describe()})
            return
        if path == "/api/switch-light-groups":
            try:
                assignments = self.switch_assignments.read()
                control_settings = self.switch_control_settings.read()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "assignments": assignments,
                    **control_settings,
                    "timings": self.presence_timings.read(),
                },
            )
            return
        if path == "/api/presence-light-groups":
            try:
                changed, _groups = self.presence_groups.sync()
                if changed:
                    self.configuration_publisher.reload_domains(("template",))
                assignments = self.presence_assignments.read()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(err)},
                )
                return
            house_mode_entity = self.inventory.cached_entity(HOUSE_MODE_HELPER)
            house_mode = str((house_mode_entity or {}).get("state") or "unknown")
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "assignments": assignments,
                    "actual_loads": self.switch_control_settings.read()[
                        "actual_loads"
                    ],
                    "timings": self.presence_timings.read(),
                    "mode_settings": self.presence_mode_settings.read(),
                    "house_mode": house_mode,
                    "house_mode_entity_id": HOUSE_MODE_HELPER,
                    "group_count": len(self.presence_groups.discover()),
                },
            )
            return
        if path == "/api/light-schedules":
            try:
                schedules = self.light_schedules.read()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(err)},
                )
                return
            # Lights the group generator offers as themselves instead of a
            # one-light group, such as a single porch or side-yard light.
            single_lights = sorted({
                targets[0]
                for targets in generated_light_group_replacements().values()
                if len(targets) == 1 and targets[0].startswith("light.")
                and not targets[0].startswith(LIGHT_GROUP_ENTITY_PREFIX)
            })
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "schedules": schedules, "single_lights": single_lights},
            )
            return
        if path == "/api/fridge-alarms":
            try:
                entities = self.inventory.fetch(include_all=True)["entities"]
                payload = {"ok": True, "fridge_alarms": {
                    "devices": fridge_alarm_catalog([
                        entity for entity in entities
                        if any(label in " ".join(
                            str(entity.get(key) or "")
                            for key in ("area", "device_name", "friendly_name", "entity_id")
                        ).replace("_", " ").casefold()
                            for label in ("fridge", "refrigerator", "freezer"))
                    ]),
                    "settings": device_alarm_buzzer_settings(self.fridge_alarm_settings.read(), entities),
                    "alarm_targets": fridge_alarm_output_catalog(entities),
                    "webhook_configured": bool(os.environ.get("DEVICE_ALARM_WEBHOOK", "").strip()),
                    **self._phone_notify_payload(entities),
                }}
            except (HomeAssistantAPIError, ValueError) as err:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(err)})
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if path == "/api/future-tech-portal":
            try:
                payload = self.future_tech_portal.payload(self.inventory)
            except (HomeAssistantAPIError, ValueError) as err:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(err)})
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if path == "/api/door-open-alerts":
            try:
                payload = self._door_open_alert_payload()
            except (HomeAssistantAPIError, ValueError) as err:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(err)})
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if path in {"/api/room-modes", "/api/room-scenes"}:
            try:
                payload = self._room_modes_payload() if path == "/api/room-modes" else self._room_scenes_payload()
            except (HomeAssistantAPIError, ValueError) as err:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(err)})
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if path == "/api/bedroom-modes":
            try:
                settings = self.bedroom_modes.read()
                door_sensors = self.inventory.fetch_security()["entities"]
                all_entities = self.inventory.fetch(include_all=True)["entities"]
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(err)},
                )
                return
            entities_by_id = {
                str(entity.get("entity_id") or ""): entity
                for entity in all_entities
            }
            sun_entity = entities_by_id.get("sun.sun")
            configured_house_mode = self._normalized_helper_state(
                entities_by_id,
                HOUSE_MODE_HELPER,
                "Night",
            )
            configured_house_mode = configured_house_mode.title()
            solar_day = (
                self.bedroom_mode_automations.solar_day(sun_entity)
                if sun_entity
                else None
            )
            if configured_house_mode == "Sleep":
                house_mode = "Sleep"
            elif solar_day is None:
                house_mode = (
                    configured_house_mode
                    if configured_house_mode in {"Day", "Night"}
                    else "Unknown"
                )
            else:
                house_mode = "Day" if solar_day else "Night"
            protect_state = self._normalized_helper_state(
                entities_by_id,
                PROTECT_STATUS_HELPER,
                "unknown",
            ).casefold()
            armed_status = (
                "Disarmed"
                if "disarmed" in protect_state or "disabled" in protect_state
                else "Unknown"
                if protect_state in {"unknown", "unavailable", ""}
                else "Armed"
            )
            current_modes: dict[str, str] = {}
            for area in settings:
                helper = (
                    "input_select.fht_"
                    + BedroomModeAutomationManager._slug(area)
                    + "_mode"
                )
                current_modes[area] = self._normalized_helper_state(
                    entities_by_id,
                    helper,
                    "Not Set",
                )
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "settings": settings,
                    "current_modes": current_modes,
                    "house_mode": house_mode,
                    "armed_status": armed_status,
                    "door_sensors": door_sensors,
                    "toddler_entities": {
                        "lights": [
                            entity for entity in all_entities
                            if str(entity.get("entity_id") or "").startswith("light.")
                        ],
                        "chimes": [
                            entity for entity in all_entities
                            if str(entity.get("entity_id") or "").startswith("button.")
                            and re.search(
                                r"\b(chime|ring|play|sound|siren)\b",
                                " ".join(filter(None, [
                                    str(entity.get("friendly_name") or ""),
                                    str(entity.get("device_name") or ""),
                                    str(entity.get("entity_id") or "").replace("_", " "),
                                ])),
                                flags=re.IGNORECASE,
                            )
                        ],
                        "indicator_effects": [
                            entity for entity in all_entities
                            if str(entity.get("entity_id") or "").startswith("select.")
                            and re.search(
                                r"\b(inovelli|led|indicator|effect|notification)\b",
                                " ".join(filter(None, [
                                    str(entity.get("friendly_name") or ""),
                                    str(entity.get("device_name") or ""),
                                    str(entity.get("entity_id") or "").replace("_", " "),
                                ])),
                                flags=re.IGNORECASE,
                            )
                        ],
                        "indicator_colors": [
                            entity for entity in all_entities
                            if str(entity.get("entity_id") or "").startswith(("number.", "select."))
                            and re.search(
                                r"\b(inovelli|led|indicator|notification)\b.*\bcolor\b|\bcolor\b.*\b(inovelli|led|indicator|notification)\b",
                                " ".join(filter(None, [
                                    str(entity.get("friendly_name") or ""),
                                    str(entity.get("device_name") or ""),
                                    str(entity.get("entity_id") or "").replace("_", " "),
                                ])),
                                flags=re.IGNORECASE,
                            )
                        ],
                        "indicator_brightness": [
                            entity for entity in all_entities
                            if str(entity.get("entity_id") or "").startswith("number.")
                            and re.search(
                                r"\b(inovelli|led|indicator|notification)\b.*\b(brightness|level)\b|\b(brightness|level)\b.*\b(inovelli|led|indicator|notification)\b",
                                " ".join(filter(None, [
                                    str(entity.get("friendly_name") or ""),
                                    str(entity.get("device_name") or ""),
                                    str(entity.get("entity_id") or "").replace("_", " "),
                                ])),
                                flags=re.IGNORECASE,
                            )
                        ],
                    },
                    **self._phone_notify_payload(all_entities),
                    "webhooks": {
                        "armed_away": bool(
                            os.environ.get("BEDROOM_ARMED_AWAY_WEBHOOK", "").strip()
                        ),
                        "armed_stay_kids": bool(
                            os.environ.get(
                                "BEDROOM_ARMED_STAY_KIDS_WEBHOOK",
                                "",
                            ).strip()
                        ),
                    },
                },
            )
            return
        if path == "/api/wake-routines":
            try:
                settings = self.wake_routines.read()
                entities = self.inventory.fetch(include_all=True)["entities"]
                room_mode_settings = self.room_modes.read()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "settings": settings,
                    "days": list(WakeRoutineSettings.DAYS),
                    "lights": [
                        entity for entity in entities
                        if str(entity.get("entity_id") or "").startswith(
                            "light."
                        )
                        and not str(entity.get("entity_id") or "").startswith("light.fht_")
                    ],
                    "light_groups": [
                        entity for entity in entities
                        if str(entity.get("entity_id") or "").startswith("light.fht_")
                    ],
                    "media_players": [
                        entity for entity in entities
                        if str(entity.get("entity_id") or "").startswith(
                            "media_player."
                        )
                    ],
                    "room_mode_catalog": self.room_modes.catalog(),
                    "room_mode_settings": room_mode_settings,
                    "override_targets": {
                        area: WakeRoutineAutomationManager.override_button(area)
                        for area in settings
                    },
                },
            )
            return
        if path == "/api/homekit-light-groups":
            self._send_json(HTTPStatus.OK, {"ok": True, "entities": self.homekit_light_groups.read()})
            return
        if path == "/api/homekit-climate":
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "entities": self.homekit_light_groups.read_climate()},
            )
            return
        if path == "/api/homekit-security":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "entities": self.homekit_light_groups.read_security(),
                },
            )
            return
        if path == "/api/app-color":
            self._send_json(HTTPStatus.OK, {"ok": True, "color": self.bedroom_mode_automations.app_color()})
            return
        if path == "/api/room-aliases":
            try:
                aliases = self.room_aliases.read()
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "aliases": aliases},
            )
            return
        if re.fullmatch(r"/interface-[0-9a-f]{16}\.(css|js)", path):
            self._serve_interface_asset(path)
            return
        interface_asset = INTERFACE_ASSETS.get(path)
        if interface_asset:
            self._serve_asset(*interface_asset)
            return
        if path.startswith("/api/"):
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "API route not found."},
            )
            return

        self._serve_index()

    def do_POST(self) -> None:
        """Run an App action."""
        if not self._request_is_allowed():
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "Ingress access required."},
            )
            return

        path = urlsplit(self.path).path
        if path.startswith("/api/maintenance/"):
            self._handle_maintenance(path, {}, write=True)
            return
        if path.startswith("/api/access/"):
            self._handle_access(path, {}, write=True)
            return
        try:
            if path in CONFIGURATION_MUTATION_PATHS:
                with CONFIGURATION_ACTIVATION_LOCK:
                    self._dispatch_POST()
            else:
                self._dispatch_POST()
        except RequestBodyTooLarge as err:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"ok": False, "error": str(err)},
            )

    def _dispatch_POST(self) -> None:
        """Dispatch one already-authorized App action."""

        path = urlsplit(self.path).path
        if path == "/api/beta/update":
            self._install_beta_update()
            return
        if path == "/api/app/update":
            try:
                version = self.app_info.install_update()
            except HomeAssistantAPIError as err:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(err)})
                return
            self._send_json(HTTPStatus.OK, {
                "ok": True, "version": version, "restarting": True,
                "entity_id": getattr(self.app_info, "update_entity", ""),
            })
            return
        if path == "/api/app-color":
            try:
                color = self.bedroom_mode_automations.save_app_color(self._read_json_object().get("color"))
            except ValueError as err:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(err)})
                return
            except OSError:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Unable to save App Color."})
                return
            self._send_json(HTTPStatus.OK, {"ok": True, "color": color})
            return
        if path == "/api/settings/revert":
            self._revert_settings()
            return
        if path == "/api/light-groups/refresh":
            try:
                result = subprocess.run(
                    ["future-homes-tech-generate-light-groups"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                generation_state, _, count = result.stdout.strip().partition(" ")
                changed = generation_state == "changed"
                if changed:
                    self.configuration_publisher.reload_all()
                    self.registry_organizer.categorize_light_groups()
            except (OSError, subprocess.SubprocessError) as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": f"Unable to refresh light groups: {err}"},
                )
                return
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "changed": changed, "count": int(count or 0)},
            )
            return
        if path == "/api/fridge-alarms":
            saved = False
            try:
                payload = self._read_json_object()
                entity_id = str(payload.get("entity_id") or "").strip()
                kind = str(payload.get("kind") or "").strip().casefold()
                entities = self.inventory.fetch(include_all=True)["entities"]
                entity = next(
                    (
                        item
                        for item in entities
                        if str(item.get("entity_id") or "") == entity_id
                    ),
                    None,
                )
                if entity is None or fridge_alarm_sensor_kind(entity) != kind:
                    raise ValueError("A current refrigerator sensor is required.")
                searchable = " ".join(
                    str(entity.get(key) or "")
                    for key in (
                        "area",
                        "device_name",
                        "friendly_name",
                        "entity_id",
                    )
                ).replace("_", " ").casefold()
                if not any(
                    label in searchable
                    for label in ("fridge", "refrigerator", "freezer")
                ):
                    raise ValueError("The selected sensor is not assigned to Fridges.")
                raw_targets = payload.get("alert_targets")
                if raw_targets is None:
                    legacy_target = str(payload.get("alert_target") or "").strip()
                    raw_targets = [legacy_target] if legacy_target else []
                if not isinstance(raw_targets, list):
                    raise ValueError("Alarm outputs must be a list.")
                alert_targets = list(
                    dict.fromkeys(
                        str(target or "").strip()
                        for target in raw_targets
                        if str(target or "").strip()
                    )
                )
                output_entities = {
                    item["entity_id"]
                    for items in fridge_alarm_output_catalog(entities).values()
                    for item in items
                }
                if any(target not in output_entities for target in alert_targets):
                    raise ValueError("A current siren or chime output is required.")
                known_phones = self.phone_notify_services.known()
                phone_targets = self._require_known_phones(
                    payload.get("notify_targets"), known_phones
                )
                settings = self.fridge_alarm_settings.save(
                    entity_id,
                    kind,
                    {
                        "enabled": payload.get("enabled", False),
                        "threshold": payload.get("threshold", 40),
                        "delay_minutes": payload.get("delay_minutes", 5),
                        "alert_targets": alert_targets,
                        "alert_behavior": "until_clear",
                        "unifi_webhook": payload.get("unifi_webhook", False),
                        "notify_targets": phone_targets,
                    },
                )
                saved = True
                automations = self.fridge_alarm_automations.sync(
                    settings,
                    entities,
                    notify_services=known_phones,
                )
                self.registry_organizer.categorize_automations(attempts=1)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST,
                    err,
                    saved=saved,
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY,
                    err,
                    saved=saved,
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "settings": settings,
                    "automations": automations,
                },
            )
            return
        if path == "/api/future-tech-portal":
            saved = False
            portal = self.future_tech_portal
            try:
                payload = self._read_json_object()
                action = str(payload.get("action") or "")
                if action == "save_token":
                    portal.save_token(payload.get("token"))
                    saved = True
                    # The first inventory doubles as the connection test.
                    portal.send_inventory(self.inventory)
                elif action == "remove_token":
                    portal.remove_token()
                    saved = True
                elif action == "settings":
                    current = portal.settings.read()
                    portal.settings.save(
                        payload.get("enabled", current["enabled"]),
                        payload.get("integrations", current["integrations"]),
                    )
                    saved = True
                    portal.apply()
                elif action == "send_inventory":
                    portal.send_inventory(self.inventory)
                elif action == "send_apps":
                    apps_sent = portal.send_apps()
                else:
                    raise ValueError("Unknown Future Tech Portal action.")
                response = portal.payload(self.inventory)
                if action == "send_apps":
                    response = {**response, "apps_sent": apps_sent}
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(HTTPStatus.BAD_REQUEST, err, saved=saved)
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(HTTPStatus.BAD_GATEWAY, err, saved=saved)
                return
            self._send_json(HTTPStatus.OK, {**response, "saved": saved, "activated": True})
            return
        if path == "/api/door-open-alerts":
            saved = False
            try:
                payload = self._read_json_object()
                entity_id = str(payload.get("entity_id") or "").strip()
                entities = self.inventory.fetch(include_all=True)["entities"]
                entity = next(
                    (
                        item
                        for item in entities
                        if str(item.get("entity_id") or "") == entity_id
                    ),
                    None,
                )
                if entity is None:
                    # A sensor that has gone missing may still be switched off.
                    if entity_id not in self.door_open_alert_settings.read():
                        raise ValueError("A current door or window sensor is required.")
                elif not is_door_sensor_entity(entity) or is_refrigerator_entity(entity):
                    raise ValueError("A current door or window sensor is required.")
                raw_targets = payload.get("alert_targets")
                if raw_targets is None:
                    raw_targets = []
                if not isinstance(raw_targets, list):
                    raise ValueError("Alarm outputs must be a list.")
                alert_targets = list(
                    dict.fromkeys(
                        str(target or "").strip()
                        for target in raw_targets
                        if str(target or "").strip()
                    )
                )
                output_entities = {
                    item["entity_id"]
                    for items in fridge_alarm_output_catalog(entities).values()
                    for item in items
                }
                if any(target not in output_entities for target in alert_targets):
                    raise ValueError("A current siren or chime output is required.")
                settings = self.door_open_alert_settings.save(
                    entity_id,
                    {
                        "enabled": payload.get("enabled", False),
                        "delay_minutes": payload.get("delay_minutes", 5),
                        "when": payload.get("when", "any"),
                        "alert_targets": alert_targets,
                        "unifi_webhook": payload.get("unifi_webhook", False),
                        "notification": payload.get("notification", True),
                    },
                )
                saved = True
                automations = self.door_open_alert_automations.sync(
                    settings,
                    entities,
                )
                self.registry_organizer.categorize_automations(attempts=1)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST,
                    err,
                    saved=saved,
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY,
                    err,
                    saved=saved,
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "settings": settings,
                    "automations": automations,
                },
            )
            return
        if path == "/api/room-aliases":
            saved = False
            try:
                payload = self._read_json_object()
                aliases = self.room_aliases.save(
                    str(payload.get("room") or ""),
                    str(payload.get("alias") or ""),
                )
                saved = True
                assignments = self.switch_assignments.read()
                inventory = self.inventory.fetch()
                control_settings = (
                    self.switch_control_settings.reconcile_actual_load_names(
                        inventory["entities"]
                    )
                )
                self.control_automations.sync(
                    assignments,
                    inventory["entities"],
                    self.button_inventory.fetch(),
                    control_settings["mode_assignments"],
                    control_settings["load_target_assignments"],
                    control_settings["actual_loads"],
                    control_settings["action_assignments"],
                    control_settings["action_settings"],
                    exhaust_timers=control_settings.get("exhaust_timers", {}),
                    exhaust_humidity=control_settings.get("exhaust_humidity", {}),
                    exhaust_presence=control_settings.get("exhaust_presence", {}),
                )
                self.registry_organizer.categorize_automations(attempts=1)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST, err, saved=saved
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY, err, saved=saved
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "aliases": aliases,
                },
            )
            return
        if path == "/api/switch-light-groups":
            saved = False
            try:
                payload = self._read_json_object()
                assignment_id = str(
                    payload.get("assignment_id")
                    or payload.get("switch_entity_id")
                    or ""
                )
                setting = str(payload.get("setting") or "light_group")
                inventory = None
                if setting == "exhaust_timer":
                    inventory = self.inventory.fetch()
                    entity = next((item for item in inventory["entities"] if item.get("entity_id") == assignment_id), {})
                    if not ExhaustFanTimer.eligible(entity):
                        raise ValueError("This switch does not have an exhaust fan load.")
                    control_settings = self.switch_control_settings.save_exhaust_timer(assignment_id, payload.get("minutes"))
                    assignments = self.switch_assignments.read()
                elif setting == "exhaust_humidity":
                    inventory = self.inventory.fetch(include_all=True)
                    entity = next((item for item in inventory["entities"] if item.get("entity_id") == assignment_id), {})
                    if not ExhaustFanTimer.eligible(entity):
                        raise ValueError("This switch does not have an exhaust fan load.")
                    sensor_id = str(payload.get("sensor") or "")
                    room = ExhaustFanHumidity.room_of(entity)
                    if sensor_id and sensor_id not in {sensor["entity_id"] for sensor in ExhaustFanHumidity.sensors(inventory["entities"], room)}:
                        raise ValueError("Choose a humidity sensor from the same room as the fan.")
                    control_settings = self.switch_control_settings.save_exhaust_humidity(
                        assignment_id, sensor_id, payload.get("start_above"), payload.get("stop_below"))
                    assignments = self.switch_assignments.read()
                elif setting == "exhaust_presence":
                    inventory = self.inventory.fetch(include_all=True)
                    entity = next((item for item in inventory["entities"] if item.get("entity_id") == assignment_id), {})
                    if not ExhaustFanTimer.eligible(entity):
                        raise ValueError("This switch does not have an exhaust fan load.")
                    sensor_id = str(payload.get("sensor") or "")
                    room = ExhaustFanHumidity.room_of(entity)
                    if sensor_id and sensor_id not in {sensor["entity_id"] for sensor in ExhaustFanPresence.sensors(inventory["entities"], room)}:
                        raise ValueError("Choose a presence sensor from the same room as the fan.")
                    control_settings = self.switch_control_settings.save_exhaust_presence(
                        assignment_id, sensor_id, payload.get("activation_minutes"), payload.get("clear_minutes"))
                    assignments = self.switch_assignments.read()
                elif setting == "actual_load_definition":
                    inventory = self.inventory.fetch()
                    load_name = ""
                    if bool(payload.get("enabled")):
                        load_entity = next(
                            (
                                entity
                                for entity in inventory["entities"]
                                if entity.get("entity_id") == assignment_id
                            ),
                            None,
                        )
                        if load_entity is None:
                            raise ValueError("The selected switch was not found.")
                        load_name = str(
                            load_entity.get("friendly_name")
                            or load_entity.get("entity_id")
                            or ""
                        )
                    control_settings = (
                        self.switch_control_settings.save_actual_load(
                            assignment_id,
                            load_name,
                        )
                    )
                    saved = True
                    assignments = self.switch_assignments.read()
                    automations = self.control_automations.sync(
                        assignments,
                        inventory["entities"],
                        self.button_inventory.fetch(),
                        control_settings["mode_assignments"],
                        control_settings["load_target_assignments"],
                        control_settings["actual_loads"],
                        control_settings["action_assignments"],
                        control_settings["action_settings"],
                        exhaust_timers=control_settings.get("exhaust_timers", {}),
                        exhaust_humidity=control_settings.get("exhaust_humidity", {}),
                        exhaust_presence=control_settings.get("exhaust_presence", {}),
                    )
                    self.registry_organizer.categorize_automations(attempts=1)
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "saved": True,
                            "activated": True,
                            "assignments": assignments,
                            **control_settings,
                            "automations": automations,
                        },
                    )
                    return
                if setting in {"exhaust_timer", "exhaust_humidity", "exhaust_presence"}:
                    pass
                elif setting == "actions":
                    raw_actions = payload.get("actions", [])
                    if not isinstance(raw_actions, list):
                        raise ValueError("Selected actions must be a list.")
                    inventory = self.inventory.fetch(include_all=True)
                    entities_by_id = {
                        str(entity.get("entity_id") or ""): entity
                        for entity in inventory["entities"]
                        if isinstance(entity, dict)
                    }
                    actual_loads = self.switch_control_settings.read()[
                        "actual_loads"
                    ]
                    for raw_action in raw_actions:
                        action = str(raw_action or "").strip()
                        action_type, separator, target_id = action.partition(":")
                        if not separator or not target_id:
                            raise ValueError("One or more selected actions are invalid.")
                        if action_type == "light_group":
                            target = entities_by_id.get(target_id)
                            if target is None or str(target.get("domain") or "") != "light":
                                raise ValueError("A selected light action was not found.")
                        elif action_type == "actual_load":
                            if target_id not in actual_loads:
                                raise ValueError("A selected actual load was not found.")
                        elif action_type == "switch_target":
                            target = entities_by_id.get(target_id)
                            if target is None or str(target.get("domain") or "") != "switch":
                                raise ValueError("A selected switch or plug was not found.")
                            if assignment_id == target_id:
                                raise ValueError("A switch cannot target itself.")
                        elif action_type == "entity_target":
                            target = entities_by_id.get(target_id)
                            if (
                                target is None
                                or str(target.get("domain") or "")
                                not in CONTROL_ENTITY_DOMAINS
                            ):
                                raise ValueError("A selected device target was not found.")
                            if assignment_id == target_id:
                                raise ValueError("A control cannot target itself.")
                        elif action_type == "room_mode":
                            mode_entity_id, separator, mode_option = target_id.partition("|")
                            if (
                                not separator
                                or mode_option not in {"Sleep", "Toddler"}
                                or not mode_entity_id.startswith("input_select.fht_")
                                or not mode_entity_id.endswith("_mode")
                            ):
                                raise ValueError("A selected room mode is invalid.")
                        elif action_type == "wake_override":
                            if (
                                not target_id.startswith("input_button.fht_")
                                or not target_id.endswith("_wake_override")
                            ):
                                raise ValueError("A selected wake override is invalid.")
                        else:
                            raise ValueError("One or more selected actions are invalid.")
                    if "door_modes" in payload:
                        control_settings = self.switch_control_settings.save_door_card(
                            assignment_id, raw_actions, payload["door_modes"], payload.get("timeout_minutes", 0))
                    else:
                        control_settings = self.switch_control_settings.save_actions(
                            assignment_id, raw_actions, payload.get("action_setting"))
                    assignments = self.switch_assignments.save(assignment_id, "")
                    if assignment_id.startswith("door:"):
                        door_entity_id, _ = parse_door_assignment_id(assignment_id)
                        self.door_assignments.save(
                            door_entity_id,
                            "",
                        )
                elif setting == "actual_load_target":
                    self.switch_control_settings.save_actions(assignment_id, [])
                    assignments = self.switch_assignments.save(
                        assignment_id,
                        "",
                    )
                    control_settings = self.switch_control_settings.save_mode(
                        assignment_id,
                        "",
                    )
                    control_settings = (
                        self.switch_control_settings.save_load_target(
                            assignment_id,
                            str(payload.get("target_entity_id") or ""),
                        )
                    )
                elif setting == "action":
                    self.switch_control_settings.save_actions(assignment_id, [])
                    action_type = str(payload.get("action_type") or "none")
                    target_entity_id = str(
                        payload.get("target_entity_id") or ""
                    )
                    if action_type in {"sleep_mode", "room_mode", "wake_override"}:
                        mode_entity_id, _, mode_option = target_entity_id.partition("|")
                        mode_option = mode_option or "Sleep"
                        assignments = self.switch_assignments.save(
                            assignment_id,
                            "",
                        )
                        control_settings = (
                            self.switch_control_settings.save_mode(
                                assignment_id,
                                mode_entity_id,
                                mode_option,
                            )
                        )
                        control_settings = (
                            self.switch_control_settings.save_load_target(
                                assignment_id,
                                "",
                            )
                        )
                    elif action_type == "light_group":
                        assignments = self.switch_assignments.save(
                            assignment_id,
                            target_entity_id,
                        )
                        control_settings = (
                            self.switch_control_settings.save_mode(
                                assignment_id,
                                "",
                            )
                        )
                        control_settings = (
                            self.switch_control_settings.save_load_target(
                                assignment_id,
                                "",
                            )
                        )
                    elif action_type == "actual_load":
                        assignments = self.switch_assignments.save(
                            assignment_id,
                            "",
                        )
                        control_settings = (
                            self.switch_control_settings.save_mode(
                                assignment_id,
                                "",
                            )
                        )
                        control_settings = (
                            self.switch_control_settings.save_load_target(
                                assignment_id,
                                target_entity_id,
                            )
                        )
                    elif action_type == "switch_target":
                        inventory = self.inventory.fetch()
                        assignments = self.switch_assignments.save(
                            assignment_id,
                            "",
                        )
                        control_settings = (
                            self.switch_control_settings.save_mode(
                                assignment_id,
                                "",
                            )
                        )
                        control_settings = (
                            self.switch_control_settings.save_discovered_switch_target(
                                assignment_id,
                                target_entity_id,
                                inventory["entities"],
                            )
                        )
                    elif action_type == "none":
                        assignments = self.switch_assignments.save(
                            assignment_id,
                            "",
                        )
                        control_settings = (
                            self.switch_control_settings.save_mode(
                                assignment_id,
                                "",
                            )
                        )
                        control_settings = (
                            self.switch_control_settings.save_load_target(
                                assignment_id,
                                "",
                            )
                        )
                    else:
                        raise ValueError("A valid switch action is required.")
                else:
                    self.switch_control_settings.save_actions(assignment_id, [])
                    assignments = self.switch_assignments.save(
                        assignment_id,
                        str(payload.get("light_group_entity_id") or ""),
                    )
                    control_settings = self.switch_control_settings.read()
                    control_settings = (
                        self.switch_control_settings.save_load_target(
                            assignment_id,
                            "",
                        )
                    )
                saved = True
                if inventory is None:
                    inventory = self.inventory.fetch()
                control_settings = (
                    self.switch_control_settings.reconcile_actual_load_names(
                        inventory["entities"]
                    )
                )
                automations = self.control_automations.sync(
                    assignments,
                    inventory["entities"],
                    self.button_inventory.fetch(),
                    control_settings["mode_assignments"],
                    control_settings["load_target_assignments"],
                    control_settings["actual_loads"],
                    control_settings["action_assignments"],
                    control_settings["action_settings"],
                    exhaust_timers=control_settings.get("exhaust_timers", {}),
                    exhaust_humidity=control_settings.get("exhaust_humidity", {}),
                    exhaust_presence=control_settings.get("exhaust_presence", {}),
                )
                self.registry_organizer.categorize_automations(attempts=1)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST, err, saved=saved
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY, err, saved=saved
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "assignments": assignments,
                    **control_settings,
                    "automations": automations,
                },
            )
            return
        if path == "/api/presence-light-groups":
            saved = False
            try:
                payload = self._read_json_object()
                presence_entity_id = str(
                    payload.get("presence_entity_id") or ""
                )
                raw_target_ids = payload.get("target_entity_ids")
                if raw_target_ids is None:
                    legacy_target_id = str(
                        payload.get("target_entity_id")
                        or payload.get("light_group_entity_id")
                        or ""
                    )
                    raw_target_ids = [legacy_target_id] if legacy_target_id else []
                if not isinstance(raw_target_ids, list):
                    raise ValueError("Selected presence actions must be a list.")
                target_entity_ids = list(dict.fromkeys(
                    str(target_id or "").strip()
                    for target_id in raw_target_ids
                    if str(target_id or "").strip()
                ))
                entities = self.inventory.fetch(include_all=True)["entities"]
                raw_parent_group_ids = payload.get("parent_presence_group_ids", [])
                if not isinstance(raw_parent_group_ids, list):
                    raise ValueError("Parent presence groups must be a list.")
                parent_presence_group_ids = list(dict.fromkeys(
                    str(parent_id or "").strip()
                    for parent_id in raw_parent_group_ids
                    if str(parent_id or "").strip()
                    and str(parent_id or "").strip() != presence_entity_id
                ))
                entity_ids = {
                    str(entity.get("entity_id") or "")
                    for entity in entities
                    if isinstance(entity, dict)
                }
                for target_entity_id in target_entity_ids:
                    if target_entity_id not in entity_ids:
                        raise ValueError("The selected presence action was not found.")
                presence_entity = next((
                    entity for entity in entities
                    if entity.get("entity_id") == presence_entity_id
                ), None)
                presence_area = str((presence_entity or {}).get("original_area")
                    or (presence_entity or {}).get("area") or "")
                for parent_id in parent_presence_group_ids:
                    parent_entity = next((
                        entity for entity in entities
                        if entity.get("entity_id") == parent_id
                    ), None)
                    parent_area = str((parent_entity or {}).get("original_area")
                        or (parent_entity or {}).get("area") or "")
                    if not parent_entity or parent_id not in entity_ids:
                        raise ValueError("The selected parent presence group was not found.")
                    parent_group_name = str(parent_entity.get("friendly_name") or "")
                    is_parent_group = (
                        isinstance(parent_entity.get("members"), list)
                        or (parent_id.startswith("binary_sensor.fht_")
                            and "group" in f"{parent_id} {parent_group_name}".lower())
                    )
                    if not is_parent_group:
                        raise ValueError("Parent presence selections must be presence groups.")
                    if presence_area and parent_area != presence_area:
                        raise ValueError("Parent presence groups must be in the same area.")
                assignments = self.presence_assignments.save(
                    presence_entity_id,
                    target_entity_ids,
                )
                timings = self.presence_timings.save(
                    presence_entity_id,
                    payload.get("activation_delay", 0),
                    payload.get("clear_delay", 0),
                    parent_presence_group_ids,
                )
                previous_mode_settings = self.presence_mode_settings.read().get(presence_entity_id)
                mode_settings = self.presence_mode_settings.save(
                    presence_entity_id,
                    payload.get("mode_settings", {}),
                )
                saved = True
                automations = self.presence_automations.sync(
                    assignments,
                    entities,
                    timings,
                    mode_settings,
                    room_modes=self.room_modes.read(),
                )
                try:
                    self.presence_automations.apply_saved_settings(presence_entity_id, previous_mode_settings)
                except HomeAssistantAPIError as err:
                    print(f"[Presence] WARNING Saved settings apply on next detection: {err}", flush=True)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST, err, saved=saved
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY, err, saved=saved
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "assignments": assignments,
                    "actual_loads": self.switch_control_settings.read()[
                        "actual_loads"
                    ],
                    "timings": timings,
                    "mode_settings": mode_settings,
                    "automations": automations,
                },
            )
            return
        if path == "/api/presence-groups/refresh":
            try:
                changed, groups = self.presence_groups.sync()
                if changed:
                    self.configuration_publisher.reload_domains(("template",))
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "changed": changed, "count": len(groups)},
            )
            return
        if path == "/api/light-schedules":
            saved = False
            try:
                payload = self._read_json_object()
                entity_id = str(payload.get("entity_id") or "")
                inventory = self.inventory.fetch()
                # A light group, or a light that has no group of its own
                # (a single porch light is never made into a group).
                valid_entity_ids = {
                    str(entity.get("entity_id") or "")
                    for entity in inventory["entities"]
                    if str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
                    or (str(entity.get("entity_id") or "").startswith("light.") and entity.get("area"))
                }
                if entity_id not in valid_entity_ids:
                    raise ValueError("A current light or Future Homes Tech light group is required.")
                schedules = self.light_schedules.save(
                    entity_id,
                    payload.get("schedule"),
                )
                saved = True
                automations = self.light_schedule_automations.sync(
                    schedules,
                    inventory["entities"],
                )
                self.registry_organizer.categorize_automations(attempts=1)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST, err, saved=saved
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY, err, saved=saved
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "schedules": schedules,
                    "automations": automations,
                },
            )
            return
        if path == "/api/room-modes":
            saved = False
            try:
                payload = self._read_json_object()
                if "house_settings" in payload:
                    house_settings = payload["house_settings"]
                    if not isinstance(house_settings, dict):
                        raise ValueError("Whole Home settings must be an object.")
                    index = self._home_configurator_index()
                    valid_sleep_sources = {
                        option["entity_id"]
                        for option in index["sleep_mode_options"]
                    }
                    requested_sleep_sources = house_settings.get(
                        "sleep_mode_sources", []
                    )
                    if (
                        not isinstance(requested_sleep_sources, list)
                        or not set(map(str, requested_sleep_sources)).issubset(
                            valid_sleep_sources
                        )
                    ):
                        raise ValueError(
                            "One or more selected bedroom Sleep modes are unavailable."
                        )
                    if "floor_sleep_modes" in house_settings:
                        raw_floors = house_settings["floor_sleep_modes"]
                        if not isinstance(raw_floors, dict):
                            raise ValueError("Floor Sleep settings must be an object.")
                        floors_by_id = {floor["floor_id"]: floor for floor in index["floors"] if floor.get("floor_id") and floor["name"].casefold() != "whole home"}
                        floor_modes = {}
                        for floor_id, selected in raw_floors.items():
                            allowed = {option["entity_id"] for option in index["sleep_mode_options"] if option.get("floor_id") == floor_id}
                            if floor_id not in floors_by_id or not isinstance(selected, dict) or not isinstance(selected.get("sources"), list) or any(not isinstance(source, str) or source not in allowed for source in selected["sources"]):
                                raise ValueError("Select only current bedrooms belonging to that floor.")
                            floor_modes[floor_id] = {"name": floors_by_id[floor_id]["name"], "sources": selected["sources"]}
                        house_settings["floor_sleep_modes"] = floor_modes
                    settings = self.bedroom_mode_automations.save_house_settings(house_settings)
                    saved = True
                    self.bedroom_mode_automations.sync(
                        self.bedroom_modes.read(),
                        self.inventory.fetch()["entities"],
                        self.inventory.fetch_security()["entities"],
                    )
                    self.bedroom_mode_automations.refresh_house_mode(self.bedroom_modes.read(), self.inventory)
                    controls = self.switch_control_settings.read()
                    self.control_automations.sync(
                        self.switch_assignments.read(),
                        self.inventory.fetch()["entities"],
                        self.button_inventory.fetch(),
                        controls["mode_assignments"],
                        controls["load_target_assignments"],
                        controls["actual_loads"],
                        controls["action_assignments"],
                        controls["action_settings"],
                        exhaust_timers=controls.get("exhaust_timers", {}),
                        exhaust_humidity=controls.get("exhaust_humidity", {}),
                        exhaust_presence=controls.get("exhaust_presence", {}),
                    )
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "saved": True,
                            "activated": True,
                            "house_settings": settings,
                        },
                    )
                    return
                area = str(payload.get("area") or "").strip()
                if area not in {room["name"] for room in self._room_modes_payload()["rooms"]}:
                    raise ValueError("Select a room with supported modes.")
                settings = self.room_modes.save(
                    str(payload.get("area") or ""),
                    payload.get("enabled_modes"),
                    scope=payload.get("mode_scope", ""),
                )
                saved = True
                self.bedroom_mode_automations.sync(
                    self.bedroom_modes.read(),
                    self.inventory.fetch(include_all=True)["entities"],
                    self.inventory.fetch_security()["entities"],
                    reload_managed=False,
                )
                self.room_scene_automations.sync(self.room_scenes.read(), settings, reload_automations=False)
                self.configuration_publisher.reload_domains(("input_select", "automation"))
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST, err, saved=saved
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY, err, saved=saved
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "settings": settings,
                },
            )
            return
        if path == "/api/room-scenes":
            saved = False
            try:
                payload = self._read_json_object()
                inventory = self.inventory.fetch(
                    include_all=True,
                    predicate=lambda entity: str(entity.get("entity_id") or "").startswith("light."),
                    fields=("entity_id",),
                )
                enabled = self.room_modes.read()
                settings = self.room_scenes.save(
                    str(payload.get("area") or "").strip(),
                    str(payload.get("mode") or ""),
                    payload.get("settings"),
                    enabled,
                    {entity["entity_id"] for entity in inventory["entities"]},
                )
                saved = True
                self.room_scene_automations.sync(settings, enabled)
                response = self._room_scenes_payload()
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(HTTPStatus.BAD_REQUEST, err, saved=saved)
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(HTTPStatus.BAD_GATEWAY, err, saved=saved)
                return
            self._send_json(HTTPStatus.OK, {
                **response, "saved": True, "activated": True,
            })
            return
        if path == "/api/bedroom-modes":
            saved = False
            try:
                payload = self._read_json_object()
                security_inventory = self.inventory.fetch_security()
                full_inventory = self.inventory.fetch(include_all=True)
                valid_door_sensors = {
                    str(entity.get("entity_id") or "")
                    for entity in security_inventory["entities"]
                }
                valid_entities = {
                    str(entity.get("entity_id") or "")
                    for entity in full_inventory["entities"]
                }
                known_phones = self.phone_notify_services.known()
                raw_settings = payload.get("settings")
                for field in ("armed_away_notify_targets", "armed_stay_kids_notify_targets"):
                    self._require_known_phones(
                        raw_settings.get(field) if isinstance(raw_settings, dict) else None,
                        known_phones,
                    )
                settings = self.bedroom_modes.save(
                    str(payload.get("area") or ""),
                    payload.get("settings"),
                    valid_door_sensors,
                    valid_entities,
                )
                saved = True
                inventory = full_inventory
                automations = self.bedroom_mode_automations.sync(
                    settings,
                    inventory["entities"],
                    security_inventory["entities"],
                    notify_services=known_phones,
                )
                house_mode = self.bedroom_mode_automations.refresh_house_mode(
                    settings,
                    self.inventory,
                )
                self.registry_organizer.categorize_automations(attempts=1)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST, err, saved=saved
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY, err, saved=saved
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "settings": settings,
                    "automations": automations,
                    "house_mode": house_mode,
                },
            )
            return
        if path == "/api/wake-routines":
            saved = False
            try:
                payload = self._read_json_object()
                inventory = self.inventory.fetch(include_all=True)
                valid_entities = {
                    str(entity.get("entity_id") or "")
                    for entity in inventory["entities"]
                }
                settings = self.wake_routines.save(
                    str(payload.get("area") or ""),
                    payload.get("settings"),
                    valid_entities,
                )
                saved = True
                automations = self.wake_routine_automations.sync(
                    settings,
                    inventory["entities"],
                )
                self.registry_organizer.categorize_automations(attempts=1)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_REQUEST, err, saved=saved
                )
                return
            except HomeAssistantAPIError as err:
                self._send_operation_failure(
                    HTTPStatus.BAD_GATEWAY, err, saved=saved
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": True,
                    "settings": settings,
                    "automations": automations,
                    "override_entity_id": WakeRoutineAutomationManager.override_button(
                        str(payload.get("area") or "")
                    ),
                },
            )
            return
        if path == "/api/homekit-light-groups":
            try:
                payload = self._read_json_object()
                inventory = self.inventory.fetch()
                entity_names = {
                    entity["entity_id"]: str(
                        entity.get("friendly_name") or entity["entity_id"]
                    )
                    for entity in inventory["entities"]
                    if str(entity.get("entity_id") or "").startswith(
                        (LIGHT_GROUP_ENTITY_PREFIX, "climate.")
                    )
                }
                entities = self.homekit_light_groups.save(
                    str(payload.get("entity_id") or ""),
                    bool(payload.get("included")),
                    entity_names,
                )
            except (ValueError, json.JSONDecodeError) as err:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(err)})
                return
            except HomeAssistantAPIError as err:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(err)})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": False,
                    "activation_required": "home_assistant_restart",
                    "entities": entities,
                },
            )
            return
        if path == "/api/homekit-climate":
            try:
                payload = self._read_json_object()
                inventory = self.inventory.fetch()
                entity_names = {
                    entity["entity_id"]: str(
                        entity.get("friendly_name") or entity["entity_id"]
                    )
                    for entity in inventory["entities"]
                    if str(entity.get("entity_id") or "").startswith(
                        (LIGHT_GROUP_ENTITY_PREFIX, "climate.")
                    )
                }
                entities = self.homekit_light_groups.save_climate(
                    str(payload.get("entity_id") or ""),
                    bool(payload.get("included")),
                    entity_names,
                )
            except (ValueError, json.JSONDecodeError) as err:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(err)})
                return
            except HomeAssistantAPIError as err:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(err)})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": False,
                    "activation_required": "home_assistant_restart",
                    "entities": entities,
                },
            )
            return
        if path == "/api/homekit-security":
            try:
                payload = self._read_json_object()
                inventory = self.inventory.fetch(include_all=True)
                security_inventory = self.inventory.fetch_security()
                entity_names = {
                    entity["entity_id"]: str(
                        entity.get("friendly_name") or entity["entity_id"]
                    )
                    for entity in inventory["entities"]
                }
                security_names = {
                    entity["entity_id"]: str(
                        entity.get("friendly_name") or entity["entity_id"]
                    )
                    for entity in security_inventory["entities"]
                }
                entity_names.update(security_names)
                entities = self.homekit_light_groups.save_security(
                    str(payload.get("entity_id") or ""),
                    bool(payload.get("included")),
                    entity_names,
                )
            except (ValueError, json.JSONDecodeError) as err:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": str(err)},
                )
                return
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "saved": True,
                    "activated": False,
                    "activation_required": "home_assistant_restart",
                    "entities": entities,
                },
            )
            return
        if path == "/api/phone-alerts/test":
            try:
                payload = self._read_json_object()
                service = phone_notify_service_id(payload.get("service"))
                if not service:
                    raise ValueError("A Companion app phone is required.")
                known_phones = self.phone_notify_services.known()
                if known_phones is not None and service not in known_phones:
                    raise ValueError(
                        "That phone is no longer signed in to the Home Assistant Companion app."
                    )
                self.phone_notify_services.send(
                    service,
                    "Future Homes Tech",
                    "Test alert from the Future Homes Tech app. Phone alerts are working.",
                )
            except (ValueError, json.JSONDecodeError) as err:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": str(err)},
                )
                return
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True})
            return
        if path == "/api/controls/toggle":
            try:
                payload = self._read_json_object()
                entity_id = str(payload.get("entity_id") or "")
                if not is_direct_control_entity_id(entity_id):
                    raise ValueError("A valid switch, light, or fan is required.")
                self.configuration_publisher.toggle_control(entity_id)
            except (ValueError, json.JSONDecodeError) as err:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": str(err)},
                )
                return
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True})
            return
        if path == "/api/lighting/action":
            try:
                payload = self._read_json_object()
                raw_entity_ids = payload.get("entity_ids")
                entity_ids = (
                    [str(entity_id) for entity_id in raw_entity_ids]
                    if isinstance(raw_entity_ids, list)
                    else [str(payload.get("entity_id") or "")]
                )
                self.configuration_publisher.light_action(
                    str(payload.get("action") or ""),
                    entity_ids,
                    payload.get("brightness_pct"),
                )
            except (ValueError, TypeError, json.JSONDecodeError) as err:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": str(err)},
                )
                return
            except HomeAssistantAPIError as err:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "error": str(err)},
                )
                return
            self._send_json(HTTPStatus.OK, {"ok": True})
            return
        if path == "/api/climate/action":
            try:
                payload = self._read_json_object()
                self.configuration_publisher.climate_action(
                    str(payload.get("action") or ""),
                    str(payload.get("entity_id") or ""),
                    payload.get("value"),
                )
            except (ValueError, TypeError, json.JSONDecodeError) as err:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(err)})
                return
            except HomeAssistantAPIError as err:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(err)})
                return
            self._send_json(HTTPStatus.OK, {"ok": True})
            return
        if path != "/api/entities":
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "API route not found."},
            )
            return

        try:
            payload = self._read_json_object()
            inventory = self.inventory.fetch(
                include_all=bool(payload.get("include_all")),
                force=bool(payload.get("force")),
            )
        except (ValueError, json.JSONDecodeError) as err:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": str(err)},
            )
            return
        except HomeAssistantAPIError as err:
            print(f"[Entity Inventory] ERROR {err}", flush=True)
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": str(err)},
            )
            return

        self._send_json(
            HTTPStatus.OK,
            {"ok": True, **inventory},
        )

    def handle_one_request(self) -> None:
        """Track request latency without logging credentials or query values."""
        self._request_started_at = time.monotonic()
        self._request_id = secrets.token_hex(6)
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def log_request(
        self,
        code: int | str = "-",
        size: int | str = "-",
    ) -> None:
        """Emit one structured, query-redacted access record."""
        path = urlsplit(getattr(self, "path", "")).path
        elapsed = max(
            0.0,
            time.monotonic() - getattr(self, "_request_started_at", time.monotonic()),
        )
        print(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": getattr(self, "_request_id", ""),
                    "client": self.client_address[0],
                    "method": getattr(self, "command", ""),
                    "path": path,
                    "status": int(code) if str(code).isdigit() else str(code),
                    "bytes": int(size) if str(size).isdigit() else None,
                    "duration_ms": round(elapsed * 1000, 1),
                },
                separators=(",", ":"),
            ),
            flush=True,
        )

    def log_message(self, format_string: str, *args: Any) -> None:
        """Emit structured server errors while suppressing raw request lines."""
        print(
            json.dumps(
                {
                    "event": "http_server_message",
                    "request_id": getattr(self, "_request_id", ""),
                    "message": format_string % args,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )

    def _settings_store_paths(self) -> dict[str, Path]:
        """Map each settings file a page can undo to the store path in use."""
        homekit = self.homekit_light_groups
        return {
            "switch_control_settings.json": self.switch_control_settings._path,
            "presence_light_group_assignments.json": self.presence_assignments._path,
            "presence_light_group_timings.json": self.presence_timings._path,
            "presence_mode_settings.json": self.presence_mode_settings._path,
            "room_modes.json": self.room_modes._path,
            "light_schedules.json": self.light_schedules._path,
            "room_scenes.json": self.room_scenes._path,
            "fridge_alarm_settings.json": self.fridge_alarm_settings._path,
            "door_open_alert_settings.json": self.door_open_alert_settings._path,
            "room_aliases.json": self.room_aliases._path,
            "homekit_light_groups.json": homekit._path,
            "homekit_climate_entities.json": homekit._climate_path,
            "homekit_security_entities.json": homekit._security_path,
        }

    def _revert_settings(self) -> None:
        """Put one settings file back to a saved version, then rebuild on it.

        The same coordinated regeneration the App runs at start-up rebuilds
        every generated package, so automations match the restored settings.
        """
        restored = False
        try:
            payload = self._read_json_object()
            page = str(payload.get("page") or "")
            store = str(payload.get("store") or "")
            store_paths = self._settings_store_paths()
            store_path = SETTINGS_HISTORY.page_store_path(page, store, store_paths)
            changed = SETTINGS_HISTORY.restore(
                store_path, str(payload.get("timestamp") or ""), atomic_write_text
            )
            restored = True
            sync_generated_configuration_on_startup(
                type(self),
                self.configuration_publisher,
                self.registry_organizer,
                attempts=1,
                raise_errors=True,
            )
            activation: dict[str, Any] = {"activated": True}
            if page == "homekit":
                # The bridge package is not part of the start-up rebuild.
                names = {
                    str(entity["entity_id"]): str(entity.get("friendly_name") or entity["entity_id"])
                    for entity in self.inventory.fetch()["entities"]
                    if entity.get("entity_id")
                }
                self.homekit_light_groups.rebuild_package(names)
                activation = {"activated": False, "activation_required": "home_assistant_restart"}
            entries = SETTINGS_HISTORY.page_entries(page, store_paths)
        except ValueError as err:
            self._send_operation_failure(HTTPStatus.BAD_REQUEST, err, saved=restored)
            return
        except (HomeAssistantAPIError, OSError) as err:
            self._send_operation_failure(
                HTTPStatus.BAD_GATEWAY if restored else HTTPStatus.INTERNAL_SERVER_ERROR,
                err,
                saved=restored,
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {"ok": True, "saved": True, "restored": changed, **activation, "entries": entries},
        )

    def _read_json_object(self) -> dict[str, Any]:
        """Read one bounded UTF-8 JSON object from the request body."""
        raw_length = self.headers.get("Content-Length", "0").strip()
        if not raw_length.isdigit():
            raise ValueError("Content-Length must be a non-negative integer.")
        content_length = int(raw_length)
        if content_length > MAX_JSON_BODY_BYTES:
            raise RequestBodyTooLarge(
                f"JSON request bodies are limited to {MAX_JSON_BODY_BYTES} bytes."
            )
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            raise ValueError("The JSON request body was incomplete.")
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except UnicodeDecodeError as err:
            raise ValueError("The JSON request body must use UTF-8.") from err
        if not isinstance(payload, dict):
            raise ValueError("The JSON request body must be an object.")
        return payload

    def _send_security_headers(self) -> None:
        """Apply shared response hardening headers."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )

    def _install_beta_update(self) -> None:
        """Download the latest Beta build and restart only this App."""
        if not beta_mode_enabled():
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": "Turn on Beta mode in the App configuration first."},
            )
            return
        if not BETA_INSTALL_LOCK.acquire(blocking=False):
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": "A Beta update is already installing."},
            )
            return
        try:
            version = self.beta_channel.install_latest()
            self.beta_channel.restart_app()
        except (BETA.BetaChannelError, OSError) as err:
            print(f"[Beta] WARNING Beta update failed: {err}", flush=True)
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(err)})
            return
        finally:
            BETA_INSTALL_LOCK.release()
        print(f"[Beta] Installed Beta {version}; restarting the App.", flush=True)
        self._send_json(HTTPStatus.OK, {"ok": True, "version": version, "restarting": True})

    def _request_is_allowed(self) -> bool:
        """Allow only the Home Assistant Ingress proxy in production."""
        return (
            self.allow_non_ingress
            or self.client_address[0] == self.ingress_proxy_ip
        )

    def _interface_bundle(self) -> dict[str, Any]:
        index_path = self.web_root / "index.html"
        metadata = index_path.stat()
        return interface_bundle(str(self.web_root), metadata.st_mtime_ns, metadata.st_size)

    def _serve_interface_asset(self, path: str) -> None:
        try:
            asset = self._interface_bundle()["assets"].get(path)
        except (OSError, ValueError):
            asset = None
        if asset is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Interface asset is unavailable. Refresh the app."})
            return
        headers = getattr(self, "headers", {})
        cache_control = "private, max-age=31536000, immutable"
        not_modified = headers.get("If-None-Match") == asset["etag"]
        self.send_response(HTTPStatus.NOT_MODIFIED if not_modified else HTTPStatus.OK)
        self.send_header("Cache-Control", cache_control)
        self.send_header("ETag", asset["etag"])
        self.send_header("Vary", "Accept-Encoding")
        self._send_security_headers()
        if not_modified:
            self.end_headers()
            return
        use_gzip = "gzip" in headers.get("Accept-Encoding", "").casefold()
        content = asset["gzip"] if use_gzip else asset["content"]
        self.send_header("Content-Type", asset["content_type"])
        self.send_header("Content-Length", str(len(content)))
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(content)

    def _serve_index(self) -> None:
        """Serve the single-page App interface."""
        headers = getattr(self, "headers", {})
        try:
            nonce = secrets.token_urlsafe(18)
            content = self._interface_bundle()["html"].replace(
                "__FHT_CSP_NONCE__",
                nonce,
            ).encode("utf-8")
        except (OSError, ValueError):
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "App interface is unavailable."},
            )
            return

        use_gzip = "gzip" in headers.get("Accept-Encoding", "").casefold()
        response_content = gzip.compress(content, compresslevel=6) if use_gzip else content
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(response_content)))
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.send_header("Vary", "Accept-Encoding")
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self._send_security_headers()
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            f"style-src 'self' 'nonce-{nonce}'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
        )
        self.end_headers()
        self.wfile.write(response_content)

    def _serve_asset(
        self,
        filename: str,
        content_type: str,
    ) -> None:
        """Serve an approved static interface asset."""
        asset_path = self.web_root / filename
        try:
            content = asset_path.read_bytes()
        except OSError:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "App asset is unavailable."},
            )
            return

        etag = f'"{hashlib.sha256(content).hexdigest()}"'
        headers = getattr(self, "headers", {})
        immutable = bool(re.search(r"-[0-9a-f]{8,64}\.", filename))
        cache_control = (
            "public, max-age=31536000, immutable"
            if immutable
            else "public, max-age=3600, must-revalidate"
        )
        if headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            self._send_security_headers()
            self.end_headers()
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("ETag", etag)
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(content)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
    ) -> None:
        """Send a JSON response."""
        content = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = getattr(self, "headers", {})
        use_gzip = (
            len(content) >= 1024
            and "gzip" in headers.get("Accept-Encoding", "").casefold()
        )
        response_content = gzip.compress(content, compresslevel=5) if use_gzip else content
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Accept-Encoding")
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(response_content)

    def _send_operation_failure(
        self,
        status: HTTPStatus,
        error: Exception,
        *,
        saved: bool = False,
    ) -> None:
        """Report persistence and Home Assistant activation separately."""
        self._send_json(
            status,
            {
                "ok": False,
                "saved": saved,
                "activated": False,
                "error": str(error),
            },
        )


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> BoundedThreadingHTTPServer:
    """Create the configured Ingress HTTP server."""
    room_aliases = RoomAliases(
        Path(
            os.environ.get(
                "ROOM_ALIASES_PATH",
                DEFAULT_ROOM_ALIASES_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.room_aliases = room_aliases
    FutureHomesTechRequestHandler.access_store = ACCESS.AccessStore(
        Path(os.environ.get("ACCESS_DATA_DIR", "/data/users_access")),
        timezone=SITE_PROFILE.timezone,
    )
    FutureHomesTechRequestHandler.access_admin = ACCESS.AccessAdmin(
        lambda: execute_websocket_commands(
            os.environ.get("SUPERVISOR_TOKEN", ""),
            os.environ.get("HOME_ASSISTANT_WEBSOCKET_URL", DEFAULT_HOME_ASSISTANT_WEBSOCKET_URL),
            [{"type": "config/auth/list"}],
        )[0]
    )
    FutureHomesTechRequestHandler.load_ha_persons = lambda: execute_websocket_commands(
        os.environ.get("SUPERVISOR_TOKEN", ""),
        os.environ.get("HOME_ASSISTANT_WEBSOCKET_URL", DEFAULT_HOME_ASSISTANT_WEBSOCKET_URL),
        [{"type": "person/list"}],
    )[0]
    FutureHomesTechRequestHandler.inventory = EntityInventory(
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
        states_url=os.environ.get(
            "HOME_ASSISTANT_STATES_URL",
            DEFAULT_HOME_ASSISTANT_STATES_URL,
        ),
        websocket_url=os.environ.get(
            "HOME_ASSISTANT_WEBSOCKET_URL",
            DEFAULT_HOME_ASSISTANT_WEBSOCKET_URL,
        ),
        config_directory=Path(
            os.environ.get(
                "HOMEASSISTANT_CONFIG_DIR",
                DEFAULT_HOME_ASSISTANT_CONFIG_DIR,
            )
        ),
        room_aliases=room_aliases,
    )
    maintenance_inventory = FutureHomesTechRequestHandler.inventory
    FutureHomesTechRequestHandler.maintenance = MAINTENANCE.Maintenance(
        maintenance_inventory,
        lambda commands: execute_websocket_commands(maintenance_inventory._token, maintenance_inventory._websocket_url, commands),
        maintenance_inventory._config_directory,
        Path(os.environ.get("MAINTENANCE_DATA_DIR", "/data/maintenance")),
    )
    FutureHomesTechRequestHandler.button_inventory = ButtonDeviceInventory(
        token=FutureHomesTechRequestHandler.inventory._token,
        websocket_url=FutureHomesTechRequestHandler.inventory._websocket_url,
        config_directory=FutureHomesTechRequestHandler.inventory._config_directory,
    )
    FutureHomesTechRequestHandler.button_inventory.warm()
    FutureHomesTechRequestHandler.protect_api = ProtectAPI(
        api_key=os.environ.get("PROTECT_API_KEY", ""),
        webhook_url=DEFAULT_PROTECT_WEBHOOK_URL,
        verify_ssl=os.environ.get("PROTECT_VERIFY_SSL", "1") == "1",
        ca_certificate=os.environ.get("PROTECT_CA_CERTIFICATE", ""),
    )
    FutureHomesTechRequestHandler.app_info = SupervisorAppInfo(
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
        info_url=os.environ.get(
            "SUPERVISOR_APP_INFO_URL",
            DEFAULT_SUPERVISOR_APP_INFO_URL,
        ),
    )
    FutureHomesTechRequestHandler.retired_approvals = RetiredEntityApprovals(
        Path(os.environ.get("FHT_DATA_DIR", "/data"))
    )
    SETTINGS_HISTORY.track(Path(os.environ.get("FHT_DATA_DIR", "/data")))
    FutureHomesTechRequestHandler.beta_channel = BETA.BetaChannel(
        root=Path(os.environ.get("FHT_BETA_ROOT", BETA.DEFAULT_BETA_ROOT)),
        stable_version=os.environ.get("FHT_STABLE_VERSION", ""),
        config_url=os.environ.get("FHT_BETA_CONFIG_URL", BETA.DEFAULT_BETA_CONFIG_URL),
        archive_url=os.environ.get("FHT_BETA_ARCHIVE_URL", BETA.DEFAULT_BETA_ARCHIVE_URL),
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
        restart_url=os.environ.get("SUPERVISOR_APP_RESTART_URL", BETA.DEFAULT_RESTART_URL),
        commit_url=os.environ.get("FHT_BETA_COMMIT_URL", BETA.DEFAULT_BETA_COMMIT_URL),
        refs_url=os.environ.get("FHT_BETA_REFS_URL", BETA.DEFAULT_BETA_REFS_URL),
        github_token=os.environ.get("FHT_GITHUB_TOKEN", ""),
        info_url=os.environ.get("SUPERVISOR_APP_INFO_URL", BETA.DEFAULT_APP_INFO_URL),
    )
    FutureHomesTechRequestHandler.switch_assignments = (
        SwitchLightGroupAssignments(
            Path(
                os.environ.get(
                    "SWITCH_ASSIGNMENTS_PATH",
                    DEFAULT_SWITCH_ASSIGNMENTS_PATH,
                )
            )
        )
    )
    FutureHomesTechRequestHandler.switch_control_settings = (
        SwitchControlSettings(
            Path(
                os.environ.get(
                    "SWITCH_CONTROL_SETTINGS_PATH",
                    DEFAULT_SWITCH_CONTROL_SETTINGS_PATH,
                )
            )
        )
    )
    FutureHomesTechRequestHandler.fridge_alarm_settings = FridgeAlarmSettings(
        Path(
            os.environ.get(
                "FRIDGE_ALARM_SETTINGS_PATH",
                DEFAULT_FRIDGE_ALARM_SETTINGS_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.fridge_alarm_automations = (
        FridgeAlarmAutomationManager(
            Path(
                os.environ.get(
                    "FRIDGE_ALARM_AUTOMATIONS_PATH",
                    DEFAULT_FRIDGE_ALARM_AUTOMATIONS_PATH,
                )
            ),
            HomeAssistantHelperPublisher(
                token=os.environ.get("SUPERVISOR_TOKEN", ""),
                services_url=os.environ.get(
                    "HOME_ASSISTANT_SERVICES_URL",
                    DEFAULT_HOME_ASSISTANT_SERVICES_URL,
                ),
            ),
        )
    )
    FutureHomesTechRequestHandler.door_open_alert_settings = DoorOpenAlertSettings(
        Path(
            os.environ.get(
                "DOOR_OPEN_ALERT_SETTINGS_PATH",
                DEFAULT_DOOR_OPEN_ALERT_SETTINGS_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.door_open_alert_automations = (
        DoorOpenAlertAutomationManager(
            Path(
                os.environ.get(
                    "DOOR_OPEN_ALERT_AUTOMATIONS_PATH",
                    DEFAULT_DOOR_OPEN_ALERT_AUTOMATIONS_PATH,
                )
            ),
            HomeAssistantHelperPublisher(
                token=os.environ.get("SUPERVISOR_TOKEN", ""),
                services_url=os.environ.get(
                    "HOME_ASSISTANT_SERVICES_URL",
                    DEFAULT_HOME_ASSISTANT_SERVICES_URL,
                ),
            ),
        )
    )
    FutureHomesTechRequestHandler.future_tech_portal = FutureTechPortalManager(
        FutureTechPortalSettings(
            Path(
                os.environ.get(
                    "FUTURE_TECH_PORTAL_SETTINGS_PATH",
                    DEFAULT_FUTURE_TECH_PORTAL_SETTINGS_PATH,
                )
            )
        ),
        Path(os.environ.get("HOMEASSISTANT_CONFIG_DIR", DEFAULT_HOME_ASSISTANT_CONFIG_DIR)),
        HomeAssistantHelperPublisher(
            token=os.environ.get("SUPERVISOR_TOKEN", ""),
            services_url=os.environ.get(
                "HOME_ASSISTANT_SERVICES_URL",
                DEFAULT_HOME_ASSISTANT_SERVICES_URL,
            ),
        ),
        option_token=os.environ.get("FUTURE_TECH_TOKEN", ""),
        option_url=os.environ.get("FUTURE_TECH_URL", ""),
    )
    FutureHomesTechRequestHandler.phone_notify_services = PhoneNotifyServices(
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
        services_url=os.environ.get(
            "HOME_ASSISTANT_SERVICES_URL",
            DEFAULT_HOME_ASSISTANT_SERVICES_URL,
        ),
    )
    FutureHomesTechRequestHandler.presence_assignments = (
        PresenceLightGroupAssignments(
            Path(
                os.environ.get(
                    "PRESENCE_ASSIGNMENTS_PATH",
                    DEFAULT_PRESENCE_ASSIGNMENTS_PATH,
                )
            )
        )
    )
    FutureHomesTechRequestHandler.presence_automations = (
        PresenceAutomationManager(
            Path(
                os.environ.get(
                    "PRESENCE_AUTOMATIONS_PATH",
                    DEFAULT_PRESENCE_AUTOMATIONS_PATH,
                )
            ),
            HomeAssistantHelperPublisher(
                token=os.environ.get("SUPERVISOR_TOKEN", ""),
                services_url=os.environ.get(
                    "HOME_ASSISTANT_SERVICES_URL",
                    DEFAULT_HOME_ASSISTANT_SERVICES_URL,
                ),
            ),
        )
    )
    FutureHomesTechRequestHandler.presence_groups = PresenceGroupManager(
        Path(
            os.environ.get(
                "PRESENCE_GROUPS_PATH",
                DEFAULT_PRESENCE_GROUPS_PATH,
            )
        ),
        FutureHomesTechRequestHandler.inventory._config_directory,
    )
    FutureHomesTechRequestHandler.presence_timings = PresenceTimingSettings(
        Path(
            os.environ.get(
                "PRESENCE_TIMINGS_PATH",
                DEFAULT_PRESENCE_TIMINGS_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.presence_mode_settings = (
        PresenceModeSettings(
            Path(
                os.environ.get(
                    "PRESENCE_MODE_SETTINGS_PATH",
                    DEFAULT_PRESENCE_MODE_SETTINGS_PATH,
                )
            )
        )
    )
    FutureHomesTechRequestHandler.light_schedules = LightScheduleSettings(
        Path(
            os.environ.get(
                "LIGHT_SCHEDULES_PATH",
                DEFAULT_LIGHT_SCHEDULES_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.light_schedule_automations = (
        LightScheduleAutomationManager(
            Path(
                os.environ.get(
                    "LIGHT_SCHEDULE_AUTOMATIONS_PATH",
                    DEFAULT_LIGHT_SCHEDULE_AUTOMATIONS_PATH,
                )
            ),
            HomeAssistantHelperPublisher(
                token=os.environ.get("SUPERVISOR_TOKEN", ""),
                services_url=os.environ.get(
                    "HOME_ASSISTANT_SERVICES_URL",
                    DEFAULT_HOME_ASSISTANT_SERVICES_URL,
                ),
            ),
        )
    )
    FutureHomesTechRequestHandler.room_modes = RoomModeSettings(
        Path(
            os.environ.get(
                "ROOM_MODES_PATH",
                DEFAULT_ROOM_MODES_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.bedroom_modes = BedroomModeSettings(
        Path(
            os.environ.get(
                "BEDROOM_MODES_PATH",
                DEFAULT_BEDROOM_MODES_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.room_scenes = RoomSceneSettings(
        Path(os.environ.get("ROOM_SCENES_PATH", DEFAULT_ROOM_SCENES_PATH))
    )
    FutureHomesTechRequestHandler.room_scene_automations = RoomSceneAutomationManager(
        Path(os.environ.get("ROOM_SCENE_AUTOMATIONS_PATH", DEFAULT_ROOM_SCENE_AUTOMATIONS_PATH)),
        HomeAssistantHelperPublisher(
            token=os.environ.get("SUPERVISOR_TOKEN", ""),
            services_url=os.environ.get("HOME_ASSISTANT_SERVICES_URL", DEFAULT_HOME_ASSISTANT_SERVICES_URL),
        ),
    )
    FutureHomesTechRequestHandler.bedroom_mode_automations = (
        BedroomModeAutomationManager(
            Path(
                os.environ.get(
                    "BEDROOM_MODE_AUTOMATIONS_PATH",
                    DEFAULT_BEDROOM_MODE_AUTOMATIONS_PATH,
                )
            ),
            HomeAssistantHelperPublisher(
                token=os.environ.get("SUPERVISOR_TOKEN", ""),
                services_url=os.environ.get(
                    "HOME_ASSISTANT_SERVICES_URL",
                    DEFAULT_HOME_ASSISTANT_SERVICES_URL,
                ),
            ),
            armed_away_webhook_configured=bool(
                os.environ.get("BEDROOM_ARMED_AWAY_WEBHOOK", "").strip()
            ),
            room_modes=FutureHomesTechRequestHandler.room_modes,
            armed_stay_kids_webhook_configured=bool(
                os.environ.get(
                    "BEDROOM_ARMED_STAY_KIDS_WEBHOOK",
                    "",
                ).strip()
            ),
        )
    )
    FutureHomesTechRequestHandler.wake_routines = WakeRoutineSettings(
        Path(
            os.environ.get(
                "WAKE_ROUTINES_PATH",
                DEFAULT_WAKE_ROUTINES_PATH,
            )
        )
    )
    FutureHomesTechRequestHandler.wake_routine_automations = (
        WakeRoutineAutomationManager(
            Path(
                os.environ.get(
                    "WAKE_ROUTINE_AUTOMATIONS_PATH",
                    DEFAULT_WAKE_ROUTINE_AUTOMATIONS_PATH,
                )
            ),
            HomeAssistantHelperPublisher(
                token=os.environ.get("SUPERVISOR_TOKEN", ""),
                services_url=os.environ.get(
                    "HOME_ASSISTANT_SERVICES_URL",
                    DEFAULT_HOME_ASSISTANT_SERVICES_URL,
                ),
            ),
        )
    )
    FutureHomesTechRequestHandler.homekit_light_groups = HomeKitLightGroupSelection(
        Path(os.environ.get("HOMEKIT_LIGHT_GROUPS_PATH", DEFAULT_HOMEKIT_LIGHT_GROUPS_PATH)),
        Path(os.environ.get("HOMEKIT_CLIMATE_PATH", DEFAULT_HOMEKIT_CLIMATE_PATH)),
        Path(os.environ.get("HOMEKIT_PACKAGE_PATH", DEFAULT_HOMEKIT_PACKAGE_PATH)),
        Path(os.environ.get("HOMEKIT_SECURITY_PATH", DEFAULT_HOMEKIT_SECURITY_PATH)),
    )
    FutureHomesTechRequestHandler.control_automations = (
        ControlAutomationManager(
            Path(
                os.environ.get(
                    "CONTROL_AUTOMATIONS_PATH",
                    DEFAULT_CONTROL_AUTOMATIONS_PATH,
                )
            ),
            HomeAssistantHelperPublisher(
                token=os.environ.get("SUPERVISOR_TOKEN", ""),
                services_url=os.environ.get(
                    "HOME_ASSISTANT_SERVICES_URL",
                    DEFAULT_HOME_ASSISTANT_SERVICES_URL,
                ),
            ),
        )
    )
    FutureHomesTechRequestHandler.door_assignments = (
        DoorLightGroupAssignments(
            Path(
                os.environ.get(
                    "DOOR_ASSIGNMENTS_PATH",
                    DEFAULT_DOOR_ASSIGNMENTS_PATH,
                )
            )
        )
    )
    FutureHomesTechRequestHandler.door_automations = DoorAutomationManager(
        Path(
            os.environ.get(
                "DOOR_AUTOMATIONS_PATH",
                DEFAULT_DOOR_AUTOMATIONS_PATH,
            )
        ),
        HomeAssistantHelperPublisher(
            token=os.environ.get("SUPERVISOR_TOKEN", ""),
            services_url=os.environ.get(
                "HOME_ASSISTANT_SERVICES_URL",
                DEFAULT_HOME_ASSISTANT_SERVICES_URL,
            ),
        ),
    )
    FutureHomesTechRequestHandler.configuration_publisher = (
        HomeAssistantHelperPublisher(
            token=os.environ.get("SUPERVISOR_TOKEN", ""),
            services_url=os.environ.get(
                "HOME_ASSISTANT_SERVICES_URL",
                DEFAULT_HOME_ASSISTANT_SERVICES_URL,
            ),
        )
    )
    FutureHomesTechRequestHandler.registry_organizer = (
        HomeAssistantRegistryOrganizer(
            token=os.environ.get("SUPERVISOR_TOKEN", ""),
            websocket_url=os.environ.get(
                "HOME_ASSISTANT_WEBSOCKET_URL",
                DEFAULT_HOME_ASSISTANT_WEBSOCKET_URL,
            ),
        )
    )
    FutureHomesTechRequestHandler.web_root = Path(
        os.environ.get("APP_WEB_ROOT", DEFAULT_WEB_ROOT)
    )
    FutureHomesTechRequestHandler.ingress_proxy_ip = os.environ.get(
        "INGRESS_PROXY_IP",
        DEFAULT_INGRESS_PROXY_IP,
    )
    FutureHomesTechRequestHandler.allow_non_ingress = (
        os.environ.get("ALLOW_NON_INGRESS") == "1"
    )
    if FutureHomesTechRequestHandler.allow_non_ingress:
        print(
            "[Security] WARNING ALLOW_NON_INGRESS=1 disables the ingress-only "
            "request boundary. Do not use this setting in production.",
            flush=True,
        )
    if not FutureHomesTechRequestHandler.protect_api._verify_ssl:
        print(
            "[Security] WARNING Protect TLS verification is disabled by an "
            "explicit compatibility override.",
            flush=True,
        )
    return BoundedThreadingHTTPServer(
        (host, port),
        FutureHomesTechRequestHandler,
    )


HEALTHY_START_SECONDS = 180


def confirm_healthy_start(beta_channel: Any, delay: float = HEALTHY_START_SECONDS) -> None:
    """Count a start as healthy only after the App has kept running a while.

    A Beta that crashes soon after its web server starts is then still
    skipped after repeated attempts instead of restarting forever.
    """
    time.sleep(delay)
    try:
        beta_channel.confirm_started()
    except OSError as err:
        print(f"[Beta] WARNING Unable to record a healthy start: {err}", flush=True)


def main() -> int:
    """Run the Future Homes Tech App server."""
    host = os.environ.get("APP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("APP_PORT", str(DEFAULT_PORT)))
    print(f"[Site Profile] {SITE_PROFILE.summary()}", flush=True)
    for problem in SITE_PROFILE.problems:
        print(f"[Site Profile] WARNING {problem}", flush=True)
    server = create_server(host, port)
    FutureHomesTechRequestHandler.inventory.start_live_updates()
    helper_publisher = HomeAssistantHelperPublisher(
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
        services_url=os.environ.get(
            "HOME_ASSISTANT_SERVICES_URL",
            DEFAULT_HOME_ASSISTANT_SERVICES_URL,
        ),
    )
    registry_organizer = HomeAssistantRegistryOrganizer(
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
        websocket_url=os.environ.get(
            "HOME_ASSISTANT_WEBSOCKET_URL",
            DEFAULT_HOME_ASSISTANT_WEBSOCKET_URL,
        ),
    )
    threading.Thread(
        target=publish_protect_status_forever,
        args=(
            FutureHomesTechRequestHandler.protect_api,
            helper_publisher,
            registry_organizer,
        ),
        name="protect-status-publisher",
        daemon=True,
    ).start()
    threading.Thread(
        target=organize_light_groups_on_startup,
        args=(FutureHomesTechRequestHandler.registry_organizer,),
        name="light-group-registry-sync",
        daemon=True,
    ).start()
    threading.Thread(
        target=sync_generated_configuration_on_startup,
        args=(
            FutureHomesTechRequestHandler,
            helper_publisher,
            registry_organizer,
        ),
        name="managed-configuration-sync",
        daemon=True,
    ).start()
    threading.Thread(
        target=confirm_healthy_start,
        args=(FutureHomesTechRequestHandler.beta_channel,),
        name="beta-health-confirmation",
        daemon=True,
    ).start()
    print(
        f"[Web UI] Future Homes Tech App listening on {host}:{port}",
        flush=True,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        FutureHomesTechRequestHandler.inventory.stop_live_updates()
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
