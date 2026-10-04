# Future Tech Portal reporting

Home Assistant pushes device status to the Future Tech Portal at
`https://futuretech.studio/api/beta/ingest`. It only sends: the portal can't
send commands back, and nothing in Home Assistant is opened to the internet.

You set it up in the App under **Settings → Home Configurator → Future Tech Portal**. The App
writes everything Home Assistant needs.

## What you do by hand

1. **Create the token in the portal.** Go to Properties → the property →
   System → Integrations → Create token, and choose source **Home Assistant**.
2. **Give it to the App**, in either place:
   - **Settings → Home Configurator → Future Tech Portal**: paste the token and press
     **Save token**.
   - **The App's Configuration tab** (Settings → Apps → Future Homes Tech App
     → Configuration): fill in **Future Tech Portal token**, right under the
     Protect API key, save, and restart the App. **Future Tech Portal URL**
     beside it defaults to `https://futuretech.studio/api/beta/ingest`; change
     it only if the portal tells you to. It must start with `https://`.

   You can paste the token on its own (`fts_…`), with `Bearer`, or as the
   whole `future_tech_token: "Bearer fts_…"` line.
3. **Restart or reload.** The App reloads Home Assistant's REST commands,
   templates, scripts and automations itself, so normally there's nothing
   more to do. If Home Assistant didn't pick it up, restart Home Assistant
   once (Settings → System → Restart).

When the token is saved, the App sends the first inventory straight away. The
Connection card turns green once the portal has accepted a report.

## What the App writes

| File | Contents |
| --- | --- |
| `/homeassistant/secrets.yaml` | One line: `future_tech_token: "Bearer fts_…"`. Every other line is left as it was. No backup copy is kept, so an old token is not left behind. |
| `/homeassistant/packages/future_tech_portal.yaml` | The reporting package. It reads the token with `!secret future_tech_token` and never contains it. The App rewrites this file, so don't edit it by hand. |
| `/data/future_tech_portal_settings.json` (App data) | Whether reports are on, and which integrations report. No token. |

A token entered in the Configuration tab is also kept by Home Assistant with
the App's other options, the same way as the Protect API key. The App copies
it into `secrets.yaml` each time it starts, and the Future Tech Portal card in Home Configurator then shows
that the token comes from the Configuration tab: change or clear it there.
Leave the option blank to manage the token from Home Configurator instead.

The App already makes sure `configuration.yaml` loads packages
(`homeassistant: packages: !include_dir_named packages`).

The token is never stored in App data, never written to a log, never put in an
automation, template or notification, and never sent back to the browser. The
page only shows whether a token is saved.

## What is reported

By default, devices from these integrations are reported: UniFi Network,
UniFi Protect, Zigbee (ZHA), Z-Wave, Matter, MQTT and ESPHome. You choose the
integrations on the settings page.

- For UniFi Network, only Ubiquiti equipment is reported, not the phones and
  laptops it tracks.
- To report a device from another integration, add the Home Assistant label
  `future_tech_report` to it. A labeled entity that has no device is reported
  under its entity ID.
- To leave a device or entity out, add the label `future_tech_exclude`.
- Disabled devices and entities are never reported.

Each device is sent with: `externalId` (the Home Assistant device ID),
`name`, `category`, `manufacturer`, `model`, `hardware`, `firmware`,
`firmwareUpdateAvailable` (from the device's `update` entity), `online`
(false when the device's main entity is unavailable), `battery` (0–100, from
its battery sensor) and `lastSeenAt` (when the main entity last changed).
`integration` is the Home Assistant integration that provides the device
(for example `zha`, `unifiprotect`, `zwave_js`), `integrationName` is that
integration's name in Home Assistant, and `integrations` lists every
integration on the device when there is more than one.
Values a device doesn't have are left out.

The category is chosen in this order:

1. UniFi Network equipment → `network`.
2. Locks, doorbells, intercoms, keypads and access readers → `access`.
3. Cameras → `camera`.
4. Hubs, bridges, coordinators, gateways and NVRs → `hub`. This includes any
   device that other reported devices connect through.
5. Devices with only sensors or binary sensors → `sensor`.
6. Everything else → `other`.

## Automations and activity

With each inventory, Home Assistant also sends the home's automations (the
portal's own are left out), up to 500 per request:

```json
{"kind": "automations", "automations": [
  {"automationId": "automation.porch_lights_at_sunset", "name": "Porch lights at sunset",
   "enabled": true, "configId": "porch_lights_at_sunset",
   "lastTriggeredAt": "2026-10-03T23:42:34.727953+00:00"}
]}
```

`configId` and `lastTriggeredAt` are left out when an automation has none.

Every time one of them runs, an event goes out straight away:

```json
{"kind": "events", "events": [
  {"eventId": "01M422BS774RN6RRCCREJPJ3Z5", "type": "automation.triggered",
   "occurredAt": "2026-10-03T23:42:34.727953+00:00",
   "automationId": "automation.porch_lights_at_sunset",
   "name": "Porch lights at sunset", "source": "state of binary_sensor.front_door"}
]}
```

`automationId` matches the automations list, `source` is Home Assistant's
description of what set it off (up to 200 characters), and `eventId` is the
run's unique context ID. Reports are sent one at a time with half a second
between them, so a burst of automations stays within 120 requests a minute.

## When it reports

| Automation | When | Sends |
| --- | --- | --- |
| Future Tech - inventory | 60 seconds after Home Assistant starts, and every hour at :07 | Every reported device in one request (up to 500 devices; a larger home is split only to stay under 256 KB) |
| Future Tech - offline/online | When a device's main entity has been unavailable for 2 minutes, and when it comes back | `device.offline` / `device.recovered` |
| Future Tech - low battery | A battery sensor below 20%, at most once per device per day | `battery.low` with `batteryPercent` |
| Future Tech - activity | Every time any other automation runs | `automation.triggered` |
| Future Tech - heartbeat | Every 10 minutes | `heartbeat` |

The list of devices for offline/online follows each inventory, so new and
removed devices are picked up within the hour. Changes in the first five
minutes after a restart are left to the inventory sent at start. If many
devices go offline at once, the reports are spread over a minute to stay
within the portal's 120 requests a minute.

## Errors

- **Any answer other than 2xx** shows a Home Assistant notification titled
  "Future Tech Portal" with the status code only (no token, no device data).
  It clears itself on the next successful report.
- **401 or 403** (token rejected or revoked): automatic reports pause. Save a
  new token, or press **Send inventory now**, to try again. A restart also
  tries once.
- **429 or 5xx**: nothing is retried right away; the next scheduled report
  tries again.
- **Other 4xx**: that report is not repeated.

Nothing is ever retried in a loop. Home Assistant writes the report contents
(device names and states, never the token) to its log when the portal answers
with an error. Don't turn on debug logging for `rest_command`: at debug level
Home Assistant logs request headers, which include the token.

## Testing it

- In the App: press **Send inventory now**. The Connection card shows the
  result after a few seconds.
- In Home Assistant: Developer Tools → Actions → choose
  `script.future_tech_send_inventory` → Perform action. Or Settings →
  Automations & Scenes → Scripts → **Future Tech - send inventory** → Run.
- The sensors `sensor.future_tech_portal` (last HTTP status, last success)
  and `sensor.future_tech_portal_devices` (number of reported devices) show
  what happened.
- Developer Tools → YAML → **Check configuration** validates the package.

`scripts/check_portal_package.py` runs the package inside a real Home
Assistant core against a local mock portal. It needs the `homeassistant` Python
package, so it isn't part of the release gate.

## UniFi Protect alarms

Protect can also report to the portal directly:

1. In the portal, create a second token with source **UniFi Protect**.
2. In Protect, go to Alarm Manager and create or edit an alarm.
3. Set Action to Webhook → Custom Webhook → Advanced Settings.
4. Choose POST, set the URL to `https://futuretech.studio/api/beta/ingest`,
   and add the header `Authorization: Bearer <that token>`.

## Turning it off

- **Send reports** off: the package is removed and the token stays saved.
- **Remove token**: the package is removed first, then the token line in
  secrets.yaml.
