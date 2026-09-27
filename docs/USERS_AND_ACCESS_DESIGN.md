# Future Homes Tech — Users and Access

Status: first administration/credential/reservation implementation in candidate 0.5.24; hardware and guest execution stages remain gated  
Date: September 12, 2026  
Reviewed baseline: 0.5.23; homeowner-approved stable: 0.5.23

Implementation scope and operational limitations are recorded in `USERS_ACCESS_0.5.24.md`. This document remains the target design; it is not a claim that all later delivery stages or acceptance tests are complete.

## 1. Product decision

Add Settings → Users as the administration page for residents, children, guests, staff, reservations, and credentials. Use the same compact glass styling and single sticky navigation row as Alarm. Build one access model that can serve a family home, a whole-home rental, or separately rented rooms. Do not treat this as simply a list of names and PINs.

Keep five concepts separate:

1. Person: the human, assigned bedrooms, optional contact details, optional Home Assistant person/user link.
2. Role and permissions: what that person may view, control, or administer.
3. Credential: a PIN or future digital key, with its own scope, schedule, and revocation state.
4. Reservation: an approved stay that supplies room assignments and the maximum guest access interval.
5. Device: a lock, wall panel, or alarm system that must independently support and enforce the requested operation.

A bedroom assignment does not automatically grant access to its locks, cameras, all home controls, or disarming the building. A Home Assistant person entity is not the same thing as a login account. Home Assistant documents these separately. [Home Assistant Persons](https://www.home-assistant.io/integrations/person/)

## 2. Settings → Users interface

Sticky navigation: **Users | People | Reservations | Access Groups | Wall Panels | Activity**.

Only load the selected tab and selected person's detail. Keep advanced policies behind a settings control rather than putting every option on every card. Show no raw entity IDs or unmasked PINs in list views.

### People

Searchable rows: name, user type, assigned bedroom(s), status, and credential status. Filters: Active, Upcoming guests, Disabled, Expired, Archived.

Add/Edit Person contains:

- Name; optional photo, email, phone, notes; optional existing Home Assistant account/person link.
- Role preset, with a review of the exact allowed actions.
- Primary bedroom plus optional additional rooms; bedroom not required for staff or whole-home guests.
- Access groups and explicit door/lock permissions.
- Permanent, date/time-limited, recurring staff-hours, or reservation-controlled access.
- PIN: Create, Enter manually, Generate random, Replace, Revoke. Reveal a newly generated PIN only in the secured credential-creation flow, not in normal autosaved fields.
- Allowed wall panels and dashboard capabilities.
- Disable person, archive person, and delete person as separate actions.

Use normal autosave for non-sensitive profile edits. Use explicit confirmation for issuing/replacing/revoking credentials, granting disarm/unlock privileges, approving an extension, and deleting users. Never make a partially typed PIN active through autosave.

### Role presets

| Preset | Intended default |
| --- | --- |
| Owner | Site administration, user/access management, approval authority; strong administrator login required. |
| Manager / co-host | Manage guests and reservations within assigned properties/units; no installer credentials or global security changes by default. |
| Resident | Assigned home controls and individually approved alarm/door permissions. |
| Child | Assigned bedroom controls and selected modes; no user administration, PIN visibility, or disarm by default. |
| Guest | Explicit reservation rooms, shared areas, panels, and dates; no system settings or other guests' information. |
| Housekeeping / maintenance | Selected doors/rooms during approved recurring hours or a work visit. |
| Installer / service | Time-limited configuration access approved by the owner; no standing right to unlock or disarm unless separately granted. |
| Custom | Explicit capability selection; unassigned permissions remain denied. |

Capabilities must distinguish view, control, and configure. Separate permission switches for Arm Away, Arm Stay Kids, Arm Stay Adult, Disarm, Silence/Acknowledge Alerts, Unlock Doors, Manage Users, Manage Reservations, Approve Extensions, and Read Audit History. Do not equate disarming with clearing or silencing every device alarm.

### Reservations

Create Reservation fields: guest/party, property, whole-home or unit/bedroom selection, shared access groups, arrival date and time, departure date and time, property time zone, optional booking reference, PIN issuance, and optional notes.

Lifecycle: Draft → Confirmed → Upcoming → In stay → Completed; Cancelled is separate. Credential lifecycle is independent, so a confirmed reservation can still show PIN not issued or device provisioning pending.

- Generate credentials before arrival but activate only at the approved start instant.
- Default to a separate credential for each adult guest. A shared party code is an optional explicit choice with reduced individual attribution.
- Access interval is start-inclusive, end-exclusive. No default grace period after departure.
- Extend Stay opens a proposed new checkout date/time. Only an authorized approver can apply it; record approver, old/new times, and reason.
- Check unit availability before extension. Requests or calendar edits do not themselves extend access.
- If a credential has already expired or been revoked, do not silently resurrect it. Issue a replacement through an explicit approval flow.
- Cancellation, early checkout, or Revoke Access immediately denies new software authorizations and queues physical credential removal.
- Room move requires an explicit access review; remove old-room access and provision new-room access with separate device acknowledgements.
- A household member retains their resident permissions if a separate guest reservation ends; credentials and grants are scoped, not global toggles on the person.

Example: Guest Alex has Bedroom 2, Front Entry, and shared Kitchen access from Friday 3:00 PM through Monday 10:00 AM, in the property's time zone. Alex cannot unlock Bedroom 3 or disarm the whole building without an additional grant. An approved Monday-noon extension changes only that stay. If a lock is offline, show Extension pending on that lock rather than claiming success.

Manual reservations are the first supported source. Airbnb-style does not mean an Airbnb API connection is already available. Calendar/PMS integration is a later adapter with deduplication, cancellation handling, and explicit conflict rules. A delayed or stale calendar feed must not automatically prolong access. Calendar links must be stored as secrets where they contain access tokens.

### Access Groups

Examples: Whole Home Guest, Bedroom 2 Guest, Shared Guest Areas, Housekeeping, Maintenance, Owner Only.

Each group identifies explicit doors/locks, panels, and permitted operations. Display friendly names but store registry identifiers. Separate security zones from ordinary room/floor organization. Adding a new lock to an area must not silently give every guest access to it. Review and approve group membership changes.

Reserve property and unit IDs now, even when only one house exists. Every query, relationship, reservation, and action must enforce property scope. One property's PIN must never authorize a different customer's installation. Future centralized hotel/multi-property administration is a separate deployment feature, not something certified by running a single Home Assistant instance.

### Wall Panels

Enroll each physical panel with a name, assigned room/unit, device-scoped credential, supported display profile, permitted modules, and inactivity timeout.

Planned mini-dashboard modules: approved room lights/groups, climate limits, shades, selected room modes, wake-up routine, alarm actions, and later locks. Default to the assigned room rather than preload the entire house. Public/shared view contains no guest directory or personal information.

Basic room controls can be available under the panel's restricted device permissions. Sensitive actions require a person PIN and explicit authorization. PIN entry does not reveal administrative settings or convert the panel into an owner session. Return to the restricted view after timeout, cancel, completion, or sign-out.

SONOFF documents Home Assistant access through supported app/webpage approaches; Shelly describes Home Assistant support for Wall Display XL. Exact models, firmware, browser behavior, certificate trust, and token storage still require testing on the actual panels. Manufacturer support alone is not proof of a secure unattended kiosk. [SONOFF NSPanel Pro FAQ](https://sonoff.tech/blogs/news/sonoff-nspanel-pro-version-update-information-and-faq), [Shelly Wall Display XL](https://www.shelly.com/products/shelly-wall-display-xl-black)

## 3. Identity and authorization foundation

Current source inspection found that the app checks requests originate through the ingress proxy and sets `panel_admin: true`. No per-person access policy for rooms, reservations, credentials, or sensitive commands exists in that request guard. The sidebar admin flag controls menu availability; it is not a new FHT access-control implementation. [Home Assistant app configuration](https://developers.home-assistant.io/docs/apps/configuration/)

Do not expose the present administrative app to guests or wall panels by merely hiding menus. Before guest access is enabled:

- Establish an authenticated administrator identity from a verified Home Assistant context. Prefer an authenticated companion integration endpoint for delegated operations; if trusted ingress identity is used instead, verify its behavior on the installed version and reject missing or forged identity. Never trust a user ID supplied by browser JSON.
- Retain Home Assistant authentication for owner/manager administration; require reauthentication for sensitive changes and support MFA through that identity system. A short PIN is not an internet administrator password.
- Use a separate, narrow panel command boundary. No Supervisor token, owner token, Protect key, or raw webhook URL in the guest browser or panel bundle.
- Enforce authorization on the server for reads, searches, subscriptions, and writes, not just visible buttons. This includes preventing a guessed room/user/credential ID from crossing scopes.
- Keep FHT access people independent of Home Assistant login users. Creating a guest does not automatically create an unrestricted HA login. Linking or creating a native HA login is a separate authorized operation through supported HA mechanisms, never direct `.storage` edits.

Home Assistant has its own entity permissions and service-call user context. These should be respected, but the app still needs explicit reservation, PIN, panel, and door policy enforcement for delegated actions. [Home Assistant permission checks](https://developers.home-assistant.io/docs/auth_permissions/)

An access decision requires all applicable conditions: active person, authenticated caller/panel, allowed role action, correct property/resource, active grant, valid credential, approved time window, non-revoked state, and any required online confirmation. Explicit denials win. Check again immediately before executing a queued sensitive action.

## 4. PIN lifecycle and secret handling

Default proposal: cryptographically generated six-digit PINs; support stronger lengths when the target keypad supports them. Validate length/alphabet across every selected lock before issuance. Preserve leading zeroes. Reject common manual PINs and prevent ambiguous duplicates within the same acceptance scope. Do not derive PINs from phone numbers, birthdays, room numbers, or sequential booking numbers.

- A person can hold multiple credentials for different purposes/stays; credential IDs are stable and never reused as lock slot IDs.
- Draft, Scheduled, Active, Expired, Revoked, and Deleted are server lifecycle states. Device status is separate: Not connected, Pending installation, Installed, Removal pending, Removed, Failed.
- Hash locally verified PINs with a salted password-grade algorithm such as Argon2id plus an independently held pepper. Tune resource cost on the HA hardware and rate-limit before costly verification. Numeric PINs have limited entropy; hashing alone does not make them strong passwords.
- Where a future lock must receive the actual PIN, hold only the necessary recoverable material in authenticated encrypted storage with a separate key, restrictive permissions, key-rotation and backup procedures. Do not claim a one-way hash can be sent to a keypad as its PIN.
- No raw PINs in normal API responses, entity attributes, helpers, logs, browser storage, analytics, or automation YAML/traces. Audit adapters for unintended secret exposure before enabling them.
- Rate-limit attempts by panel and credential/person where known, with an aggregate site budget to resist distributed guessing. Use progressive delay and generic failure messages; preserve a secure owner recovery path without remotely disabling emergency egress.
- Revoke invalidates panel sessions and pending authorizations. Replacing a PIN retires the old one; it does not add a permanent second credential by accident.

These credential protections follow OWASP's separation of secret storage and authentication controls. [Password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

## 5. Time, extension, deletion, and offline correctness

- Store instants in UTC and display/edit them in the property's IANA time zone; initialize this installation to America/Phoenix. Require a clear choice for ambiguous or nonexistent daylight-saving times at other sites.
- Enforce expiry during every authorization, not only through an in-memory timer. A process restart cannot reactivate expired access.
- Start/expiry scheduling uses persistent jobs and recomputes on startup or clock changes. If trusted time is unavailable, deny new time-sensitive authorizations and flag the fault.
- Device commands carry a credential/grant version. Do not retry a stale install or old extension after revocation; revocation takes precedence.
- Never report a physical PIN as removed until the lock/controller confirms it. Offline devices show Removal pending and an owner warning; they may still accept the PIN.
- Strict unattended rental expiry requires a tested lock/controller with native schedule enforcement. Software-only removal while a lock is offline cannot guarantee a checkout deadline. Mark unsupported devices clearly rather than advertise that guarantee.
- On Home Assistant/controller outage, cached dashboard visuals may remain, but they cannot grant new privileges. Offline PIN verification would be a separately designed and tested, bounded authorization lease, not a browser-local copy of the PIN database.
- Delete credential revokes it immediately in the FHT layer, removes device copies where possible, and destroys recoverable secret material after necessary cleanup. Retain a non-secret revocation tombstone so backup restoration cannot reinstall it.
- Delete person first revokes their credentials, sessions and grants. Offer archive for ordinary departures; support deletion/anonymization under the chosen retention policy while retaining the minimum non-secret audit evidence. Block deletion of the final administrative recovery identity.
- Backup restore must reconcile revocations and device state before issuing credentials. Restoring an old database must not resurrect cancelled stays.
- Do not build fire/emergency egress or certified hotel access guarantees out of dashboard automations. Hardware and installation requirements need separate assessment.

## 6. Alarm and lock integration boundaries

Requested alarm actions are explicit commands: Arm Away, Arm Stay Kids, Arm Stay Adult, and Disarm. Store permission for each independently. Custom Kids/Adult profiles need explicit mapping to the installed system; do not assume they are native UniFi profile names.

Flow: enrolled panel → person/PIN verification → resource and time authorization → server-side named command → configured HA/UniFi adapter → confirmation → non-secret audit event.

Keep UniFi webhook configuration installer-only and separate from DeviceAlarm alerts. Never accept an arbitrary webhook URL from a panel. A webhook HTTP success means request accepted, not confirmed Armed or Disarmed. Display Pending until authoritative status confirms the result; otherwise show Unknown/Failed. Do not perform dangerous blind retries after an uncertain result, especially for disarming or unlocking. A door-unlock event does not automatically disarm the property unless an explicit policy authorizes that link.

For physical locks, implement a capability adapter per integration/model: read status, install code, confirm code, remove code, native validity schedule, slot limits, PIN constraints, remote/local operation, and attributable access events. Keep a lock-specific mapping of credential ID to device slot/provider credential ID. Record unsupported capabilities and partial failures per lock.

The generic Home Assistant lock interface is not a universal credential-management API; code programming is integration-specific. For example, ZHA documents a code-slot action, which does not establish that every lock or protocol supports the same feature. [Home Assistant Lock](https://www.home-assistant.io/integrations/lock/), [ZHA set lock user code](https://www.home-assistant.io/actions/zha.set_lock_user_code/)

With no locks installed, the UI may create access policies and draft credentials, but must say **Not connected to a lock**. Creating a PIN must never display **Door access installed** without a real adapter acknowledgement.

## 7. Storage and performance

Use a dedicated versioned transactional SQLite access store under the app's private data directory, not shared dashboard entity attributes or loosely related JSON files. Do not migrate unrelated settings merely to add this feature.

Core records: properties, units/rooms, people, HA identity links, roles, role capabilities, access groups, grants, reservations, extension approvals, credentials, panel enrollments, lock bindings, provisioning jobs, and audit events. Use foreign keys, unique scoped identifiers, validated schedules, revision checks, and transactionally queued provisioning work. UI labels may change; identifiers must not depend on friendly-name matching.

- Pagination/search for People and Activity; indexed lookup for credentials and current grants.
- Separate small authorized panel payloads from the full administrative inventory.
- Reuse the room/device catalog; no repeated full entity fetch per person or tab.
- Event-driven changes and nearest-deadline scheduling; no new full-inventory polling loop for reservations.
- Sensitive responses use no-store caching. Static assets can retain versioned caching. Permission caches are scoped and immediately invalidated when grants change.
- A bounded background queue handles provider calls, expiry, and reconciliation without blocking page rendering.
- Audit actor, affected subject, action, target resource, panel, timestamp, reason, permission revision, and result. Never record the PIN. Local append-only auditing is not tamper-proof against a compromised host; stronger hotel auditing needs an independently protected destination.

## 8. Recommended delivery sequence

1. **Identity and permissions:** prove trusted administrator identity; implement scoped storage, authorization, audit, and owner recovery. No guest exposure yet.
2. **Users and reservations:** People CRUD, bedroom assignments, role presets, PIN generation/revocation, access windows, approved extensions, and explicit unprovisioned states. Test with simulated devices.
3. **Mini dashboards and alarm commands:** enroll panels, build small room-scoped views and PIN action approval, verify actual UniFi profile mappings and status confirmation.
4. **First physical lock adapter:** choose hardware only after checking schedule/code/remove capabilities; test slot programming, offline expiry, revocation, and restore behavior on real locks.
5. **Rental/hotel operations:** PMS/calendar adapters, staff schedules, room moves, party credentials, remote approvals and notifications, multi-property management, and stronger independent audit/monitoring as required.

Future credential types can include NFC/RFID, mobile keys or one-use invitations through compatible adapters. Biometric templates should stay in qualified hardware/providers, not in this app. Payment processing, emergency dispatch, biometric access, and commercial certification are not part of the initial user-management release.

Each stage is a reversible candidate, not a replacement for stable 0.5.23 until explicit homeowner approval. Preserve versioned database migrations and an access-data recovery plan; an old binary cannot safely interpret a future credentials database merely because its app archive exists.

## 9. Release acceptance tests

- Create a disabled user and fully configure them without activating a credential.
- Generate a PIN, preserve leading zeroes, reject collisions, and prove no secret appears in normal responses/logs.
- Deny early arrival, allow exactly at start, and deny exactly at checkout; repeat across restart and time-zone changes.
- Reject unapproved extensions; apply approved changes with approver audit and per-device status.
- Revoke before arrival, during a stay, during a queued install, and while a lock/panel is offline.
- Verify cancelled/expired credentials remain denied after restoring an older backup.
- Guest cannot read or command another bedroom, guest, property, or administrative endpoint by changing IDs or directly calling APIs.
- Child cannot disarm; staff cannot enter outside work hours; manager cannot elevate their own permissions.
- Panel escape, refresh, back navigation, browser storage, copied URL, and device-token theft do not expose an owner session or arbitrary commands.
- Validate every alarm mode against actual upstream status without triggering production sirens during development.
- Lock tests distinguish Installed, Failed and Pending, and prove native expiry where the product promises offline expiry.
- Renaming rooms/devices or changing a guest's bedroom does not silently change access grants.
- Startup and tab navigation stay responsive with hotel-sized data; authorization remains correct under concurrent changes.

## 10. Decisions to confirm before external access

The design can proceed with household mode, manual reservations, six-digit generated PINs, no checkout grace, and no physical lock provisioned. Before wall-panel or door access is activated, confirm exact panel models/firmware, first lock/controller hardware, who may approve extensions, desired guest disarm permissions, data retention, and the scope of any commercial deployment. These are security acceptance decisions, not reasons to defer the users/reservations foundation.
