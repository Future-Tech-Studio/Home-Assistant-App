# Users & Access — 0.8.9 Beta

Closes gaps listed in `USERS_ACCESS_0.5.24.md`. Still no lock programming, wall-panel enrollment, guest login or alarm commands; every PIN check remains a simulation.

## Added

- **Overnight recurring hours.** `staff_schedule.end` earlier than `start` runs past midnight; `days` are the days a shift starts. Equal start and end are rejected. Older apps compare `start <= now < end`, which is never true for an overnight schedule, so they deny rather than widen access.
- **People filters.** `GET /api/access/people?state=active|upcoming|disabled|expired|archived`. Each row carries `access_state`. Guests follow their confirmed stays. Filtering runs after the read because the state depends on the clock and the guest's stays.
- **Home Assistant person link.** `ha_person` holds a Home Assistant person id from `person/list` (cached for 60 seconds). One profile per person; a failed lookup keeps an existing link; deleting the profile clears it. This links records only. It grants nothing and doesn't touch Home Assistant accounts.
- **Room moves.** `POST /api/access/reservations/move` with `rooms`, `groups`, `reason`, `access_reviewed: true`. Editing rooms on a confirmed stay is refused (409). Availability is checked from now (or arrival) to checkout. Credentials are not room-bound in software, so the PIN stays; access groups are replaced only by what the admin submits. Each move is kept in `room_moves` and audited as `reservations.room_moved`.
- **Restore review.** A new `meta` table stores the inode of `users.sqlite`. SQLite writes in place, so the inode changes only when the file is replaced (a backup restore or a move to new hardware). On mismatch the store records `restore_review`, audits `store.restore_detected`, and `verify_pin` denies credentials created before that moment. `POST /api/access/review` with `action: revoke_all | keep` ends the hold. `GET /api/access/catalog` returns `restore_review`.

## Limits

- Restore detection is best-effort and local. A database last written by 0.8.8 or older has no marker, so restoring it is not detected. This is still not tamper-proof anti-rollback.
- Schema version stays 1. The `meta` table and new JSON fields are ignored by Stable 0.8.4, which can still open the database. Edits saved from 0.8.4 drop `ha_person` and `room_moves` from that record.

## Validation

`tests/test_access.py` (overnight boundaries, filters, link uniqueness and fallback, reviewed moves and their audit, restore hold, keep/revoke, restart and pre-0.8.9 databases), `tests/test_access_http.py` (routes, CSRF and identity on the new writes, cached and failing person lookups) and `tests/access_browser.cjs` (link, overnight hint, Move rooms review, filters).
