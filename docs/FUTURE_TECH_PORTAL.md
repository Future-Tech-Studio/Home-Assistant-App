# Future Tech Portal reporting

Home Assistant pushes device status to the Future Tech Portal at
`https://futuretech.studio/api/beta/ingest`. It only sends: the portal can't
send commands back, and nothing in Home Assistant is opened to the internet.

You set it up in the App under **Settings → Portal Configurator**. The App
writes everything Home Assistant needs.

## What you do by hand

1. **Create the token in the portal.** Go to Properties → the property →
   System → Integrations → Create token, and choose source **Home Assistant**.
2. **Give it to the App**, in either place:
   - **Settings → Portal Configurator**: paste the token and press
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
it into `secrets.yaml` each time it starts, and the Future Tech Portal card in Portal Configurator then shows
that the token comes from the Configuration tab: change or clear it there.
Leave the option blank to manage the token from Portal Configurator instead.

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
its battery sensor) and `lastSeenAt`: for a device that is online, the time
of the report; for one that is offline, when it was last seen online.

A Home Assistant restart resets every entity's "last changed" time, so that
can't be used for an offline device: it would say "offline since" the
restart. Instead the package remembers, for each offline device, the last
time it reported before it dropped off, and keeps that across restarts. For
devices that were already offline when reporting started, the App looks it up
in Home Assistant's history (10 days by default). If a device has been offline
longer than the history goes back, `lastSeenAt` is left out. `device.offline`
events carry `lastSeenAt` too.
`integration` is the Home Assistant integration that created the device
(for example `zha`, `unifiprotect`, `zwave_js`), `integrationName` is that
integration's name in Home Assistant, and `integrations` lists every
integration on the device when there is more than one. Helpers that only
wrap another integration's entity, such as Switch as X (`switch_as_x`),
groups and templates, are never reported as the integration; a Matter Wi-Fi
switch shown as a light through Switch as X is reported as `matter`.

Matter devices also carry `network`: `thread`, `wifi` or `ethernet`, so the
portal can tell Matter over Thread from Matter over Wi-Fi. Home Assistant's
Matter entities don't say which; the App reads it from the Matter
integration's diagnostics (the network each device supports) when it starts
and whenever an inventory is sent by hand, and the hourly inventories reuse
it. Bridged Matter devices take their bridge's network.

A device is offline when its main entity is unavailable. UniFi Network keeps
a disconnected switch or access point's entities available, so for UniFi gear
the device's State sensor is used instead: `disconnected` or
`heartbeat_missed` means offline, both in the inventory and for
`device.offline` / `device.recovered`.
Values a device doesn't have are left out.

The category is chosen in this order:

1. UniFi Network equipment → `network`.
2. Locks, doorbells, intercoms, keypads and access readers → `access`.
3. Cameras → `camera`.
4. Hubs, bridges, coordinators, gateways and NVRs → `hub`. This includes any
   device that other reported devices connect through.
5. Devices with only sensors or binary sensors → `sensor`.
6. Everything else → `other`.

## System versions

Every inventory request also says which Home Assistant it comes from, for the
portal's property System → Home Assistant card:

```json
{"kind": "inventory",
 "system": {"appVersion": "0.7.51", "coreVersion": "2026.9.3",
            "supervisorVersion": "2026.09.1", "osVersion": "16.2"},
 "devices": [...]}
```

Once a day, after the devices, the inventory sends one more request listing every
installed Home Assistant App (add-on) and everything installed through HACS:

```json
{"kind": "apps", "appVersion": "0.7.55", "apps": [
  {"appId": "core_mosquitto", "name": "Mosquitto broker", "source": "addon",
   "version": "6.5.1", "latestVersion": "6.5.2", "updateAvailable": true, "state": "started"},
  {"appId": "custom-components/alexa_media_player", "name": "Alexa Media Player", "source": "hacs",
   "version": "4.13.0", "latestVersion": "4.13.2", "updateAvailable": true, "category": "integration"},
  {"appId": "custom_components/local_thing", "name": "Local Thing", "source": "custom",
   "version": "1.0.0", "category": "integration"}
]}
```

Send inventory now always includes it, and **Send app versions now** sends only
this report, straight away. `source` says where each item came from:

- `addon`: every App installed from the App Store, from any repository:
  Home Assistant's own, community and custom repositories, and local Apps.
  This list comes from the Supervisor. `appId` is the App's slug.
- `hacs`: everything HACS installed, in every HACS category. `category` is
  `integration`, `plugin` (dashboard cards), `theme`, `python_script`,
  `appdaemon` or `template`. `name` is the name HACS shows, and
  `latestVersion` is the newest version HACS knows of. `appId` is the GitHub
  repository. HACS's records are read from `.storage/hacs.repositories`, or
  from its newer `.storage/hacs.data`.
- `custom`: an integration copied into `custom_components` by hand, which
  HACS doesn't manage. `appId` is `custom_components/<domain>`.

`version` is an empty string when an item doesn't declare one. Fields a source
doesn't have are left out.

`appVersion` is the Future Homes Tech App build that is running (a Beta build
when Beta mode is on). The App reads Core, Supervisor and OS versions from the
Supervisor when it starts and on Send inventory now; until then Core and
Supervisor come from Home Assistant's own update entities. Values Home
Assistant doesn't provide are left out.

## Automation activity

Every time an automation runs (the portal's own are left out), an event is
queued and goes out with the next batch (see **Events**):

```json
{"kind": "events", "appVersion": "0.8.2", "events": [
  {"eventId": "01M422BS774RN6RRCCREJPJ3Z5", "type": "automation.triggered",
   "occurredAt": "2026-10-03T23:42:34.727953+00:00",
   "automationId": "automation.porch_lights_at_sunset",
   "name": "Porch lights at sunset", "source": "state of binary_sensor.front_door"}
]}
```

`automationId` is the automation's entity ID, `source` is Home Assistant's
description of what set it off (up to 200 characters), and `eventId` is the
run's unique context ID.

## Events

`automation.triggered`, `device.offline`, `device.recovered` and `battery.low`
all go into one queue in Home Assistant, each with its own `eventId` and
`occurredAt` (when it happened, not when it was sent).

- **Every 5 minutes** the queue goes out as one request:
  `{"kind": "events", "appVersion": "…", "events": [ … ]}`, oldest first. More
  than 500 waiting are split into requests of up to 500 (or fewer, to stay
  under 256 KB). Once 500 are waiting they go at once, without waiting for the
  5 minutes.
- **Heartbeat**: a 5-minute window with nothing to send sends one `heartbeat`
  event instead. Otherwise the batch counts as the heartbeat.
- **Kept on failure**: a 429, a 5xx or no answer keeps the events for the next
  send. A 401 or 403 pauses sending (below); events keep queueing meanwhile.
  Any other 4xx drops that batch, as it would be refused again.
- **Limits**: the queue keeps at most 2,000 events, or about 240,000
  characters, whichever comes first (a Home Assistant template can return no
  more than 262,144 characters). That is roughly 900 to 1,200 typical events.
  When it is full the oldest are dropped. Events older than 7 days, which the
  portal refuses, are dropped before sending.
- The queue is the sensor `sensor.future_tech_portal_queue` (its state is the
  number waiting). The events are held in its `attribution` attribute, which
  Home Assistant's history database never stores, so a large queue doesn't
  grow the database or fill the log with size warnings. It is kept across
  restarts.

## When it reports

| Automation | When | Sends |
| --- | --- | --- |
| Future Tech - inventory | 60 seconds after Home Assistant starts, and every hour at :07 | Every reported device in one request (up to 500 devices; a larger home is split only to stay under 256 KB) |
| Future Tech - offline/online | When a device's main entity has been unavailable for 2 minutes, and when it comes back | Queues `device.offline` / `device.recovered` |
| Future Tech - low battery | A battery sensor below 20%, at most once per device per day | Queues `battery.low` with `batteryPercent` |
| Future Tech - activity | Every time any other automation runs | Queues `automation.triggered` |
| Future Tech - send events | Every 5 minutes, and as soon as 500 events are waiting | The queued events, or a `heartbeat` when there are none |

The list of devices for offline/online follows each inventory, so new and
removed devices are picked up within the hour. Changes in the first five
minutes after a restart are left to the inventory sent at start.

## Errors

- **Any answer other than 2xx** shows a Home Assistant notification titled
  "Future Tech Portal" with the status code only (no token, no device data).
  It clears itself on the next successful report.
- **401 or 403** (token rejected or revoked): automatic reports pause. Save a
  new token, or press **Send inventory now**, to try again. A restart also
  tries once.
- **429 or 5xx**: nothing is retried right away; the next scheduled report
  tries again. Queued events stay queued for the next send.
- **Other 4xx**: that report is not repeated (a batch of events is dropped).

Nothing is ever retried in a loop. Home Assistant writes the report contents
(device names and states, never the token) to its log when the portal answers
with an error. Don't turn on debug logging for `rest_command`: at debug level
Home Assistant logs request headers, which include the token.

## Testing it

- In the App: press **Send inventory now**. The Connection card shows the
  result after a few seconds. **Send app versions now** sends only the Apps
  and HACS report; **Last app versions** on the Connection card is the last
  time the portal accepted it.
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
