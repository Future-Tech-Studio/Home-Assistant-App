# Users & Access — 0.5.24 candidate

## Available now

Settings → Users provides people, bedroom/room assignments, role presets and individually selected capabilities, optional recurring hours, private notes, manual reservations, explicit access groups, planned wall-panel configurations, and audit history. Editing requires a signed-in Home Assistant administrator. FHT roles describe future access rights; they do not grant administration of Home Assistant or of this page.

Create a person first. For guests, create and confirm their reservation before issuing a PIN from that reservation. Every confirmed reservation must select its occupied rooms; select all relevant rooms for a whole-home stay. Overlapping confirmed bookings are rejected. This release operates one property, initialized to America/Phoenix; it is not a central multi-property hotel service.

PINs can be entered manually (6–10 digits) or generated securely (6 digits, including leading zeroes). Issuance displays the value once, cleared on close/navigation or after 60 seconds. Normal reads never contain the PIN, hash, salt, or duplicate-check fingerprint. Test PIN is an administrator-only simulation; it checks the PIN, saved schedule, person status and reservation without sending any command. Six-digit PINs are not administrator passwords.

Request extension records a pending proposal. Approve extension separately checks the current reservation revision, checkout deadline and room availability. Only approval changes checkout and eligible active/scheduled credentials. Cancelled stays cannot be reactivated; extensions cannot revive expired or revoked credentials. Start is inclusive and checkout exclusive, evaluated on every test rather than an in-memory timer. Recurring hours are same-day windows; overnight shifts need a later expanded schedule editor.

Disable/archive revokes current PINs. Re-enabling a profile does not reactivate them. Delete person cancels their stays, revokes credentials and removes profile contact/notes/assignments while retaining non-secret identifiers and audit evidence. Native HA user accounts are never created, renamed or deleted. The HA administrator account remains the recovery identity independent of FHT profiles.

## Security boundary

The new APIs accept `X-Remote-User-Id` only from the configured ingress proxy, verify it with Home Assistant's `config/auth/list`, and reject missing/inactive/non-admin/system-generated identities. Production `ALLOW_NON_INGRESS` does not bypass this additional Users boundary. Reads cache HA user verification for at most five seconds; each mutation verifies fresh. If the installed Supervisor supplies no verified ingress identity, Users fails closed with an actionable message; do not work around this by adding browser-supplied identity headers or exposing a direct port.

The identity behavior is based on Supervisor's identity injection/header stripping and Core's administrator registry. Installation-specific ingress verification is still required after installing the candidate. [Supervisor ingress](https://github.com/home-assistant/supervisor/blob/main/supervisor/api/ingress.py), [Core authentication administration](https://github.com/home-assistant/core/blob/dev/homeassistant/components/config/auth.py)

Writes require same-origin JSON plus a short-lived CSRF token bound to the verified actor. The new access store is isolated under `/data/users_access`; its directory is mode 0700, database/key mode 0600. Salted PBKDF2-HMAC-SHA256 uses 600,000 iterations and a separate pepper key, using Python's standard library rather than adding a native cryptographic dependency. PIN operations are rate-limited before hashing by actor and site, with counters persisted across restarts. A keyed duplicate fingerprint prevents ambiguous PIN reuse, including previously revoked values.

The SQLite schema is versioned, all mutations are transactional, references validated, and record revisions prevent stale edits. Sensitive responses are `no-store`. No PIN material is added to helpers, automations, browser storage, or application archives. There is no recoverable PIN encryption/provisioning yet: physical adapters will require reissuing a credential through an appropriate secure provisioning flow.

The existing general app endpoints have not been converted into guest endpoints. Keep the admin app admin-only. Users, reservations and panel planning do not provide guest login, restricted HA accounts or browser mini-dashboard access.

## Not activated in this release

- Physical lock programming, slot allocation, native expiry, installation/removal acknowledgements, or offline access guarantees.
- Wall-panel enrollment tokens, PIN-operated mini dashboards, protected UniFi/HA arm/disarm commands, or webhook mappings.
- Airbnb/PMS/calendar synchronization, multi-property administration, NFC/mobile credentials, payment or emergency-response services.

Door/lock groups and wall-panel profiles are explicit planning records. A door sensor is not an actuator. Every issued credential says no device is connected. Unsupported actions have no public execution endpoint. These are hard gates, not an optional insecure mode.

Before enabling real execution, complete trusted panel enrollment, scoped command authorization, credential provisioning and removal reconciliation, authoritative alarm status confirmation, independent revocation/recovery protection, hardware compatibility and offline tests. Do not expose a six-digit PIN endpoint to the public internet. Restoring an older private access database can restore historical credentials; this candidate does not claim backup anti-rollback protection. A restore must remain disconnected until an administrator reviews and reissues access. None of these later guarantees is established by the current simulation tests.

## Backup and rollback

Stable application rollback is 0.5.23. Preserve the complete `/data/users_access` directory in a private Home Assistant app backup after setup; the key is required for existing verification records. Missing keys fail closed rather than silently regenerating a key against an existing database. Never share these private backups or place them in the public repository.

An app-code rollback does not roll back access data and 0.5.23 does not use this new directory. Do not delete the directory during rollback. A newer unsupported schema fails closed. The saved 0.5.23 source/runtime archives contain no live user database.

## Validation

`scripts/release_gate.sh` includes isolated model and real loopback HTTP tests: trusted identity, guest denial, CSRF, PIN privacy, persistence, exact time boundaries, DST ambiguity, recurring hours, cancellations, extensions, overlap/conflict checks, secret destruction, pagination and unsupported-device gates.

For optional browser validation, run `python3 tests/run_access_browser.py` with Playwright available (`FHT_PLAYWRIGHT` may point to its package and `FHT_NODE_BINARY` to Node). It starts and stops a fresh loopback fixture automatically. For manual preview, use `python3 tests/access_preview.py`. The fixture uses a temporary database, substitutes verified test identities, and cannot call real devices. Desktop/mobile testing covers user creation, PIN generation/testing, reservations, extension approval, group/panel planning, audit navigation, and zero Users requests during normal startup. The preview is not part of the runtime image.
