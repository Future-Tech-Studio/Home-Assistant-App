# Site Profile

The site profile is the one place that holds the values which differ from one
Future Homes Tech home to the next: the UniFi Protect console address, the
property's time zone, the weather entity, and the room and door naming rules
that were written for this home. Everything else in the App is the same in
every home, so a second home runs the same App build with a different profile
and no code changes.

## Files

| File | Role |
| ---- | ---- |
| `future_homes_tech_app/site_profile.json` | Shipped defaults: this home's values. Installed as `/usr/local/bin/site_profile.json`. |
| `/data/site_profile.json` | Optional per-installation override. Only the keys it names change; every other key keeps its default. |

The loader is `future_homes_tech_app/fht_site.py`. Each App process (the web
server, `future-homes-tech-configure`, the light group generator, the Users
database) reads the merged profile once when it starts. After editing
`/data/site_profile.json`, restart the App to apply the change.

`/data` is the App's private storage, so the override travels with the saved
settings transfer (`docs/SETTINGS_TRANSFER.md`) and with full backups.

## Writing an override

Only include the keys that differ. Nested keys live under their section:

```json
{
  "protect": {
    "base_url": "https://console.example.net/proxy/protect/integration/v1"
  },
  "timezone": "America/Denver",
  "rooms": {
    "hidden_areas": ["adopting", "bridges", "unifi", "garage"]
  }
}
```

Lists replace the default list completely (they do not add to it), so repeat
any default entries you want to keep. Words are compared without regard to
case.

A value that fails its check, or a key the profile does not know, is reported
and ignored; the shipped default stays in use for that key and every other key
still applies. A file that is not valid JSON leaves all defaults in use. The
checks never repeat the file's content in their messages.

## Seeing the active profile

- **Settings → UniFi** shows a read-only **Site Profile** card with the active
  values, which file they came from, which keys the override changed, and any
  problems found in the override.
- `GET /api/site-profile` returns the same information; `/api/app-info`
  carries it as `site_profile`, which the browser uses for its own room-name
  and weather fallbacks.
- In Home Assistant's Terminal: `future-homes-tech-site check` prints the
  source summary and any problems (exit code 1 when there are problems);
  `future-homes-tech-site show` prints the merged profile;
  `future-homes-tech-site get <key>` prints one value;
  `future-homes-tech-site protect-webhook <name>` prints one full webhook
  address. `run.sh` uses the last of these when the Device Alarm Webhook
  option is blank.
- The App log prints one `[Site Profile]` line at start, plus a `WARNING` line
  per problem.

For a developer checkout, `FHT_SITE_PROFILE_PATH` points the loader at a
different override file, and `FHT_DATA_DIR` moves the default `/data`.

## Keys

### `protect.base_url`

The UniFi Protect integration API address of this home's console, ending in
`/integration/v1`. Must be HTTPS with no sign-in details, query, or fragment;
a trailing `/` is removed. Every Protect request the App makes (arm mode, NVR
status, resources) and every Alarm Manager webhook below is built from it.

Default: `https://unifi.fht.internal/proxy/protect/integration/v1`

### `protect.webhooks.device_offline`

The Alarm Manager alarm the App calls when a device goes offline
(`rest_command.unifi_device_offline`, and the webhook the server uses to
derive its Protect API base). Either the alarm's name, appended to
`<base_url>/alarm-manager/webhook/`, or a full `http(s)://` address used as
is. Spaces in a name are encoded for you.

Default: `device_offline`

### `protect.webhooks.armed_siren`

The alarm that sounds the siren when an exterior-door entry delay runs out
(`rest_command.future_homes_tech_armed_siren`). Same form as above.

Default: `Armed%20Siren`

### `protect.webhooks.device_alarm`

The alarm used by device alerts such as refrigerator doors
(`rest_command.fht_device_alarm_webhook`). The App option
`device_alarm_webhook` (Settings → Apps → Future Homes Tech App →
Configuration) still takes a full address and wins when set; `config.yaml`
keeps this home's address as that option's default because an option default
cannot read a file. When the option is blank, `run.sh` and
`future-homes-tech-configure` use this profile value. Same form as above.

Default: `DeviceAlarm`

### `timezone`

The property's IANA time zone, used by Users & Access to interpret arrival and
checkout times and shown in its labels. The Users database's property record
is set to this value each time the App starts; reservations already saved keep
the zone they were saved with.

Default: `America/Phoenix`

### `weather_entity`

The `weather.*` entity the toolbar temperature and the live weather channel
read. The Climate page's own `input_text.fht_weather_entity` helper still wins
there when it names a `weather.*` entity.

Default: `weather.forecast_home`

### `rooms.hidden_areas`

Home Assistant Areas that Home Configurator leaves out of its Floor and room
index because they hold infrastructure rather than rooms (compared without
regard to case).

Default: `["adopting", "bridges", "unifi"]`

### `rooms.device_alarm_room_names`

Room names (or App display names) that mean "this room holds the device
alert sensors": the room shows the refrigerator and device alarm editor and is
left out of ordinary room lists.

Default: `["bridges", "device alarms", "fridges"]`

### `rooms.sleep_source_excluded_words`

A bedroom-type room whose name or display name contains any of these words is
not offered as a Sleep mode source for floor sleep settings (a bathroom is a
bedroom-type room by name but has no one sleeping in it).

Default: `["bathroom"]`

### `doors.exterior_area_words`

Accepted and validated, but not read by any current feature: the header
Exterior Doors indicator that used it has been removed. A door, garage door,
or opening sensor whose Area name contained any of these words counted as an
exterior entry door. The key stays so existing overrides remain valid.

Default: `["entry", "exterior"]`

### `doors.exterior_door_name_words`

Accepted and validated, but not read by any current feature (see above). A
door sensor whose name or entity ID contained any of these phrases counted as
an exterior entry door whatever its Area.

Default: `["back door", "entry door", "exterior door", "front door", "patio door", "side door"]`

### `catalog.retired_unavailable_lights`

`light.*` entity IDs that Home Assistant still lists but this home retired.
While one is unavailable or unknown and has no group members, the action
editors do not offer it; if it comes back it is offered again.

Default: `["light.kitchen_1g_lights", "light.kitchen_switch_1g_load_control_lights", "light.kitchen_switch_1g_rgb_indicator_lights"]`

### `catalog.indicator_light_pattern`

A regular expression (Python syntax) matched against each light's entity ID
and names, with underscores shown as spaces and in lower case. A match marks
the light as a switch indicator LED: the action editors never offer it and the
light group generator never groups it. An empty string turns the rule off.

Default: `\b(?:rgb indicator|switch(?: \d+g)? rgb)\b`

## What deliberately stays in code

These look home-specific but describe how the product works, so they are the
same in every Future Homes Tech home and are not profile keys:

- The `device_alarm_webhook` option default in `config.yaml` (an option
  default cannot read a file; see `protect.webhooks.device_alarm`).
- Product room types and their keyword lists: `bedroom` as the Room Modes
  type, the "pantry" door-mode behaviour, the "master bedroom" naming
  preference, and the browser's area sort order.
- Refrigerator alert words (`fridge`, `refrigerator`, `freezer`) and the
  siren / chime output rules, which describe device kinds, not this home.
- The door-sensor rules that exclude batteries, tamper, moisture, and
  doorbell sensors.
- Home Assistant and Supervisor addresses (`http://supervisor/...`) and the
  Ingress proxy address, which are the same on every Home Assistant install.
- Private values such as the Protect API key, the entry delay webhook ID, and
  interior door webhooks: those stay App options or secrets, never profile
  keys. The profile holds no credentials and must not be given any.

The browser keeps a built-in fallback for the device-alarm room names and the
weather entity for the moment before `/api/app-info` has answered; both follow
the profile once it has.
