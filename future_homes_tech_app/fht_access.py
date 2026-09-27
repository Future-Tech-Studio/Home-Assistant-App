"""Private users and scheduled-access administration; no device execution."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CAPABILITIES = {
    "room_control": "Room controls",
    "room_modes": "Room modes",
    "arm_away": "Arm Away",
    "arm_stay_kids": "Arm Stay Kids",
    "arm_stay_adult": "Arm Stay Adult",
    "disarm": "Disarm",
    "unlock": "Unlock assigned doors",
    "acknowledge": "Acknowledge alerts",
}
ROLES = {
    "owner": "Owner", "manager": "Manager / co-host", "resident": "Resident",
    "child": "Child", "guest": "Guest", "staff": "Housekeeping / maintenance",
    "installer": "Installer / service", "custom": "Custom",
}
ROLE_DEFAULTS = {
    "owner": list(CAPABILITIES), "manager": ["room_control", "room_modes"],
    "resident": ["room_control", "room_modes"], "child": ["room_control", "room_modes"],
    "guest": ["room_control"], "staff": [], "installer": [], "custom": [],
}
COLLECTIONS = {"people", "groups", "reservations", "panels"}
PIN_ITERATIONS = 600_000
SCHEMA_VERSION = 1


class AccessError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def clean_text(value, label, limit=160, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str) or len(value) > limit:
        raise AccessError(f"{label} must be text, up to {limit} characters.")
    value = value.strip()
    if required and not value:
        raise AccessError(f"{label} is required.")
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise AccessError(f"{label} contains unsupported characters.")
    return value


def choices(value, allowed, label):
    if not isinstance(value, list) or len(value) > 250 or any(not isinstance(item, str) for item in value):
        raise AccessError(f"Choose valid {label}.")
    if set(value) - set(allowed):
        raise AccessError(f"Some {label} are no longer available. Reload and review the selection.")
    return sorted(set(value))


def timestamp(value, zone, required=False):
    if value in (None, ""):
        if required:
            raise AccessError("Arrival and departure dates and times are required.")
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            candidates = []
            for fold in (0, 1):
                aware = parsed.replace(tzinfo=ZoneInfo(zone), fold=fold)
                if aware.astimezone(timezone.utc).astimezone(ZoneInfo(zone)).replace(tzinfo=None) == parsed:
                    candidates.append(aware.timestamp())
            if len(set(candidates)) != 1:
                raise AccessError("This local time is ambiguous or skipped by daylight saving. Choose another time or include a UTC offset.")
            return candidates[0]
        return parsed.timestamp()
    except (ValueError, OverflowError, ZoneInfoNotFoundError) as error:
        if isinstance(error, AccessError):
            raise
        raise AccessError("Enter a valid date and time.") from error


def iso_time(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else ""


class AccessAdmin:
    """Verify proxy-provided identity against HA's administrator registry."""

    def __init__(self, load_users, clock=time.time):
        self.load_users = load_users
        self.clock = clock
        self.secret = secrets.token_bytes(32)
        self.lock = threading.Lock()
        self.cached_users = []
        self.cached_until = 0

    def authenticate(self, peer, proxy, headers, fresh=False):
        user_id = headers.get("X-Remote-User-Id", "")
        if peer != proxy or not re.fullmatch(r"[a-fA-F0-9]{32}", user_id):
            raise AccessError("Open Users through Home Assistant while signed in as an administrator. No trusted user identity was received.", 403)
        with self.lock:
            if fresh or self.clock() >= self.cached_until:
                self.cached_until = 0
                try:
                    users = self.load_users()
                except Exception as error:
                    raise AccessError("Home Assistant could not verify your administrator account. Try again when it is available.", 503) from error
                if not isinstance(users, list):
                    raise AccessError("Home Assistant returned no verified user registry.", 503)
                self.cached_users = users
                self.cached_until = self.clock() + 5
            user = next((item for item in self.cached_users if item.get("id") == user_id), {})
            if user.get("is_active") is not True or user.get("system_generated") or not (
                user.get("is_owner") is True or "system-admin" in user.get("group_ids", [])
            ):
                raise AccessError("Only an active Home Assistant administrator can manage Users & Access.", 403)
        return {"id": user_id, "name": user.get("name") or "Home Assistant administrator"}

    def csrf(self, actor, bucket=None):
        if bucket is None:
            bucket = int(self.clock() // 600)
        return hmac.new(self.secret, f"{actor['id']}:{bucket}".encode(), hashlib.sha256).hexdigest()

    def check_csrf(self, actor, headers):
        if headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise AccessError("Use the Users page to submit changes.", 415)
        if headers.get("Sec-Fetch-Site") == "cross-site":
            raise AccessError("Cross-site access changes are not allowed.", 403)
        token = headers.get("X-FHT-Access-CSRF", "")
        bucket = int(self.clock() // 600)
        if not any(hmac.compare_digest(token, self.csrf(actor, value)) for value in (bucket, bucket - 1)):
            raise AccessError("Your secure form session expired. Retry the change.", 403)


class AccessStore:
    """Transactional single-property foundation with explicit future-device gates."""

    def __init__(self, directory, clock=time.time):
        self.directory = Path(directory)
        self.path = self.directory / "users.sqlite"
        self.clock = clock
        self.lock = threading.RLock()
        self.initialized = False
        self.pepper = None

    def _initialize(self):
        if self.initialized:
            return
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        key_path = self.directory / "pin-verification.key"
        if not key_path.exists():
            if self.path.exists():
                raise AccessError("The access verification key is missing. Restore the complete private Users backup; existing PINs cannot be recovered.", 503)
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(secrets.token_bytes(32))
                handle.flush()
                os.fsync(handle.fileno())
        self.pepper = key_path.read_bytes()
        if len(self.pepper) != 32:
            raise AccessError("The private access verification key is invalid.", 503)
        os.chmod(key_path, 0o600)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(descriptor)
        os.chmod(self.path, 0o600)
        with sqlite3.connect(self.path) as database:
            version = database.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise AccessError("This Users database needs a newer app. Do not downgrade its private data.", 503)
            database.executescript("""
                CREATE TABLE IF NOT EXISTS properties (id TEXT PRIMARY KEY, name TEXT NOT NULL, timezone TEXT NOT NULL);
                INSERT OR IGNORE INTO properties VALUES ('home', 'Whole Home', 'America/Phoenix');
                CREATE TABLE IF NOT EXISTS people (
                    id TEXT PRIMARY KEY, property_id TEXT NOT NULL REFERENCES properties(id),
                    name TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS groups (
                    id TEXT PRIMARY KEY, property_id TEXT NOT NULL REFERENCES properties(id),
                    name TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS panels (
                    id TEXT PRIMARY KEY, property_id TEXT NOT NULL REFERENCES properties(id),
                    name TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY, property_id TEXT NOT NULL REFERENCES properties(id),
                    person_id TEXT NOT NULL REFERENCES people(id), name TEXT NOT NULL,
                    data TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS credentials (
                    id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id),
                    reservation_id TEXT REFERENCES reservations(id), label TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE, salt BLOB, digest BLOB,
                    pin_length INTEGER NOT NULL, start_at REAL, end_at REAL,
                    state TEXT NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS extensions (
                    id TEXT PRIMARY KEY, reservation_id TEXT NOT NULL REFERENCES reservations(id),
                    base_revision INTEGER NOT NULL, new_end REAL NOT NULL, reason TEXT NOT NULL,
                    state TEXT NOT NULL, requested_by TEXT NOT NULL, reviewed_by TEXT, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, actor_id TEXT NOT NULL, actor_name TEXT NOT NULL,
                    action TEXT NOT NULL, subject TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (bucket TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS people_name ON people(property_id, name COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS reservation_person ON reservations(person_id);
                CREATE INDEX IF NOT EXISTS credential_person ON credentials(person_id);
                CREATE INDEX IF NOT EXISTS credential_reservation ON credentials(reservation_id);
                CREATE INDEX IF NOT EXISTS extension_reservation ON extensions(reservation_id);
                PRAGMA user_version = 1;
            """)
        self.initialized = True

    @contextmanager
    def connection(self):
        with self.lock:
            self._initialize()
            database = sqlite3.connect(self.path, timeout=10)
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA foreign_keys=ON")
            database.execute("PRAGMA secure_delete=ON")
            try:
                database.execute("BEGIN IMMEDIATE")
                yield database
                database.commit()
            except Exception:
                database.rollback()
                raise
            finally:
                database.close()

    def _audit(self, database, actor, action, subject, detail=""):
        database.execute("INSERT INTO audit(actor_id,actor_name,action,subject,detail,created) VALUES(?,?,?,?,?,?)",
                         (actor["id"], actor["name"], action, subject, detail, self.clock()))

    def _record(self, database, collection, identifier):
        if collection not in COLLECTIONS:
            raise AccessError("Unknown Users collection.", 404)
        row = database.execute(f"SELECT * FROM {collection} WHERE id=? AND property_id='home'", (identifier,)).fetchone()
        if row is None:
            raise AccessError("This record no longer exists. Reload the list.", 404)
        return {**json.loads(row["data"]), "id": row["id"], "revision": row["revision"]}

    def _all(self, database, collection):
        return [{**json.loads(row["data"]), "id": row["id"], "revision": row["revision"]}
                for row in database.execute(f"SELECT * FROM {collection} WHERE property_id='home'")]

    def _revision(self, record, payload):
        if type(payload.get("revision")) is not int or record["revision"] != payload["revision"]:
            raise AccessError("This record changed in another session. Reopen it before saving.", 409)

    def _put(self, database, collection, data, identifier=None, revision=0):
        identifier = identifier or secrets.token_hex(16)
        data = {key: value for key, value in data.items() if key not in ("id", "revision")}
        columns = "id,property_id,name,data,revision"
        values = [identifier, "home", data["name"], json.dumps(data), revision + 1]
        updates = "name=excluded.name,data=excluded.data,revision=excluded.revision"
        if collection == "reservations":
            columns += ",person_id"
            values.append(data["person_id"])
            updates += ",person_id=excluded.person_id"
        database.execute(f"INSERT INTO {collection} ({columns}) VALUES ({','.join('?' for value in values)}) ON CONFLICT(id) DO UPDATE SET {updates}", values)
        return {**data, "id": identifier, "revision": revision + 1}

    def _window(self, payload, zone, required=False):
        start = timestamp(payload.get("start_at"), zone, required)
        end = timestamp(payload.get("end_at"), zone, required)
        if start is not None and end is not None and end <= start:
            raise AccessError("Departure / access end must be after the start.")
        return iso_time(start), iso_time(end)

    def _groups(self, database, values):
        return choices(values, [item["id"] for item in self._all(database, "groups")], "access groups")

    def _revoke_person(self, database, person_id, deleted=False):
        database.execute("UPDATE credentials SET state=?,salt=NULL,digest=NULL,revision=revision+1 WHERE person_id=? AND state NOT IN ('revoked','deleted')",
                         ("deleted" if deleted else "revoked", person_id))

    def _check_availability(self, database, rooms, start, end, excluding=None):
        for other in self._all(database, "reservations"):
            if other["id"] == excluding or other["status"] != "confirmed":
                continue
            if set(rooms) & set(other["rooms"]) and start < timestamp(other["end_at"], other["timezone"]) and end > timestamp(other["start_at"], other["timezone"]):
                raise AccessError("These rooms overlap another confirmed reservation.", 409)

    def save(self, collection, payload, actor, catalog):
        if collection not in COLLECTIONS:
            raise AccessError("Unknown Users collection.", 404)
        if payload.get("confirmed") is not True:
            raise AccessError("Confirm this access change before saving.")
        with self.connection() as database:
            old = self._record(database, collection, payload["id"]) if payload.get("id") else None
            if old:
                self._revision(old, payload)
                if old.get("status") == "deleted":
                    raise AccessError("Deleted users cannot be restored by editing.", 409)
            data = {"name": clean_text(payload.get("name"), "Name", required=True)}
            zone = database.execute("SELECT timezone FROM properties WHERE id='home'").fetchone()[0]
            room_ids = [room["id"] for room in catalog.get("rooms", [])]
            if collection == "people":
                role = payload.get("role", "resident")
                status = payload.get("status", "active")
                if role not in ROLES or status not in ("active", "disabled", "archived"):
                    raise AccessError("Choose a valid role and user status.")
                start, end = self._window(payload, zone)
                schedule = payload.get("staff_schedule", {})
                if not isinstance(schedule, dict):
                    raise AccessError("Choose valid recurring hours.")
                days = choices(schedule.get("days", []), [str(day) for day in range(7)], "weekdays")
                hours = {}
                if days:
                    for key in ("start", "end"):
                        value = schedule.get(key, "")
                        if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                            raise AccessError("Recurring hours must use HH:MM.")
                        hours[key] = value
                    if hours["start"] >= hours["end"]:
                        raise AccessError("Recurring access must end after it starts on the same day.")
                data.update(role=role, status=status, rooms=choices(payload.get("rooms", []), room_ids, "rooms"),
                            groups=self._groups(database, payload.get("groups", [])),
                            permissions=choices(payload.get("permissions", ROLE_DEFAULTS[role]), CAPABILITIES, "permissions"),
                            start_at=start, end_at=end, timezone=zone,
                            staff_schedule={"days": days, **hours},
                            contact=clean_text(payload.get("contact"), "Contact details", 300),
                            notes=clean_text(payload.get("notes"), "Notes", 1000))
                if old and status != "active":
                    self._revoke_person(database, old["id"])
                if old and role == "guest" and old["role"] != "guest":
                    database.execute("UPDATE credentials SET state='revoked',salt=NULL,digest=NULL,revision=revision+1 WHERE person_id=? AND reservation_id IS NULL AND state='active'", (old["id"],))
            elif collection == "groups":
                data.update(resources=choices(payload.get("resources", []), [item["id"] for item in catalog.get("resources", [])], "doors / locks"),
                            permissions=choices(payload.get("permissions", []), CAPABILITIES, "permissions"))
            elif collection == "panels":
                rooms = choices(payload.get("rooms", []), room_ids, "rooms")
                if len(rooms) > 1:
                    raise AccessError("Assign one room to each wall panel.")
                timeout = payload.get("timeout", 60)
                if type(timeout) is not int or not 15 <= timeout <= 300:
                    raise AccessError("Panel timeout must be 15–300 seconds.")
                data.update(rooms=rooms, model=clean_text(payload.get("model"), "Panel model", 100), timeout=timeout,
                            modules=choices(payload.get("modules", []), ("lights", "climate", "shades", "room_modes", "alarm"), "panel modules"),
                            status="planned", device_access="not_enrolled")
            elif collection == "reservations":
                person = self._record(database, "people", payload.get("person_id", ""))
                if person["status"] != "active":
                    raise AccessError("Choose an active guest before making a reservation.")
                status = payload.get("status", "confirmed")
                if status not in ("draft", "confirmed"):
                    raise AccessError("Choose Draft or Confirmed; use Cancel stay to cancel.")
                if old and old["status"] == "cancelled":
                    raise AccessError("Cancelled stays cannot be reactivated. Create a new reservation.", 409)
                if old and old["status"] == "confirmed" and status == "draft":
                    raise AccessError("Use Cancel stay to withdraw a confirmed reservation.", 409)
                start, end = self._window(payload, zone, True)
                if timestamp(end, zone) <= self.clock():
                    raise AccessError("The checkout time must be in the future.")
                if old and timestamp(end, zone) > timestamp(old["end_at"], zone):
                    raise AccessError("Use Request extension to extend an existing stay.", 409)
                if old and old["person_id"] != person["id"]:
                    raise AccessError("The guest cannot change on an existing reservation. Cancel and create a new stay.")
                rooms = choices(payload.get("rooms", []), room_ids, "reserved rooms")
                if not rooms:
                    raise AccessError("Choose the rooms reserved for this stay.")
                if status == "confirmed":
                    self._check_availability(database, rooms, timestamp(start, zone), timestamp(end, zone), old["id"] if old else None)
                data.update(person_id=person["id"], rooms=rooms, groups=self._groups(database, payload.get("groups", [])),
                            start_at=start, end_at=end, timezone=zone, status=status,
                            notes=clean_text(payload.get("notes"), "Reservation notes", 1000))
            result = self._put(database, collection, data, old["id"] if old else None, old["revision"] if old else 0)
            self._audit(database, actor, f"{collection}.{'updated' if old else 'created'}", result["id"])
            return result

    def remove(self, collection, payload, actor):
        if payload.get("confirmed") is not True:
            raise AccessError("Confirm removal first.")
        with self.connection() as database:
            record = self._record(database, collection, payload.get("id", ""))
            self._revision(record, payload)
            if collection == "people":
                self._revoke_person(database, record["id"], deleted=True)
                for reservation in self._all(database, "reservations"):
                    if reservation["person_id"] == record["id"]:
                        reservation.update(status="cancelled", name="Deleted guest stay", notes="")
                        self._put(database, "reservations", reservation, reservation["id"], reservation["revision"])
                record.update(name="Deleted person", status="deleted", contact="", notes="", rooms=[], groups=[], permissions=[], staff_schedule={})
                self._put(database, collection, record, record["id"], record["revision"])
            elif collection == "reservations":
                record["status"] = "cancelled"
                self._put(database, collection, record, record["id"], record["revision"])
                database.execute("UPDATE credentials SET state='revoked',salt=NULL,digest=NULL,revision=revision+1 WHERE reservation_id=? AND state='active'", (record["id"],))
            else:
                if collection == "groups":
                    people = [item for item in self._all(database, "people") if item["status"] == "active"]
                    stays = [item for item in self._all(database, "reservations") if item["status"] != "cancelled" and timestamp(item["end_at"], item["timezone"]) > self.clock()]
                    if any(record["id"] in item.get("groups", []) for item in people + stays):
                        raise AccessError("Remove this access group from active people and upcoming/current reservations before deleting it.", 409)
                database.execute(f"DELETE FROM {collection} WHERE id=? AND property_id='home'", (record["id"],))
            self._audit(database, actor, f"{collection}.{'cancelled' if collection == 'reservations' else 'deleted'}", record["id"])

    def _credential(self, row):
        state = row["state"]
        if state == "active":
            if row["end_at"] is not None and self.clock() >= row["end_at"]:
                state = "expired"
            elif row["start_at"] is not None and self.clock() < row["start_at"]:
                state = "scheduled"
        return {key: row[key] for key in ("id", "person_id", "reservation_id", "label", "pin_length", "revision")} | {
            "state": state, "start_at": iso_time(row["start_at"]), "end_at": iso_time(row["end_at"]),
            "device_status": "not_connected", "physical_access_installed": False,
        }

    def _rate_limit(self, actor):
        with self.connection() as database:
            now = self.clock()
            for bucket, maximum in (("site", 60), ("actor:" + actor["id"], 10)):
                row = database.execute("SELECT * FROM attempts WHERE bucket=?", (bucket,)).fetchone()
                if row and now - row["started"] < 60 and row["count"] >= maximum:
                    raise AccessError("Too many PIN operations. Wait one minute before trying again.", 429)
            for bucket in ("site", "actor:" + actor["id"]):
                database.execute("INSERT INTO attempts VALUES(?,?,1) ON CONFLICT(bucket) DO UPDATE SET started=CASE WHEN ?-started>=60 THEN ? ELSE started END,count=CASE WHEN ?-started>=60 THEN 1 ELSE count+1 END", (bucket, now, now, now, now))

    def issue_pin(self, payload, actor):
        if payload.get("confirmed") is not True:
            raise AccessError("Confirm PIN issuance first.")
        self._rate_limit(actor)
        with self.connection() as database:
            person = self._record(database, "people", payload.get("person_id", ""))
            if person["status"] != "active":
                raise AccessError("A disabled or archived person cannot receive an active credential.")
            self._revision(person, {"revision": payload.get("person_revision")})
            reservation_id = payload.get("reservation_id") or None
            reservation = self._record(database, "reservations", reservation_id) if reservation_id else None
            if person["role"] == "guest" and not reservation:
                raise AccessError("Guest PINs require a confirmed reservation.")
            if reservation and (reservation["person_id"] != person["id"] or reservation["status"] != "confirmed"):
                raise AccessError("This reservation is not confirmed for that person.")
            windows = [person] + ([reservation] if reservation else [])
            starts = [timestamp(item["start_at"], item["timezone"]) for item in windows if item.get("start_at")]
            ends = [timestamp(item["end_at"], item["timezone"]) for item in windows if item.get("end_at")]
            start, end = max(starts) if starts else None, min(ends) if ends else None
            if end is not None and (self.clock() >= end or start is not None and start >= end):
                raise AccessError("The permitted access window has ended or does not overlap the stay.")
            generate = payload.get("generate") is True
            pin = payload.get("pin", "")
            for _attempt in range(100 if generate else 1):
                if generate:
                    pin = f"{secrets.randbelow(1_000_000):06d}"
                if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{6,10}", pin):
                    raise AccessError("Use a PIN containing 6–10 digits.")
                common = len(set(pin)) == 1 or pin in ("123456", "654321", "1234567", "12345678", "123456789", "0123456789", "1234567890")
                fingerprint = hmac.new(self.pepper, pin.encode(), hashlib.sha256).hexdigest()
                exists = database.execute("SELECT id FROM credentials WHERE fingerprint=?", (fingerprint,)).fetchone()
                if not common and not exists:
                    break
                if not generate:
                    raise AccessError("Choose a less predictable PIN that has not already been used.")
            else:
                raise AccessError("Unable to generate a unique PIN. Please retry.", 503)
            replace_id = payload.get("replace_id")
            if replace_id:
                old = database.execute("SELECT * FROM credentials WHERE id=? AND person_id=?", (replace_id, person["id"])).fetchone()
                if old is None or old["reservation_id"] != reservation_id:
                    raise AccessError("The credential to replace does not belong to this person and stay.")
                self._revision(dict(old), payload)
                database.execute("UPDATE credentials SET state='revoked',salt=NULL,digest=NULL,revision=revision+1 WHERE id=?", (replace_id,))
            identifier = secrets.token_hex(16)
            salt = secrets.token_bytes(16)
            secret = hmac.new(self.pepper, pin.encode(), hashlib.sha256).digest()
            digest = hashlib.pbkdf2_hmac("sha256", secret, salt, PIN_ITERATIONS)
            label = clean_text(payload.get("label") or "Access PIN", "Credential label", 80)
            database.execute("INSERT INTO credentials VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (identifier, person["id"], reservation_id, label, fingerprint, salt, digest, len(pin), start, end, "active", 1, self.clock()))
            self._audit(database, actor, "credential.replaced" if replace_id else "credential.issued", identifier)
            row = database.execute("SELECT * FROM credentials WHERE id=?", (identifier,)).fetchone()
            return {"credential": self._credential(row), "pin": pin}

    def revoke_pin(self, payload, actor):
        if payload.get("confirmed") is not True:
            raise AccessError("Confirm credential removal first.")
        with self.connection() as database:
            row = database.execute("SELECT * FROM credentials WHERE id=?", (payload.get("id", ""),)).fetchone()
            if row is None:
                raise AccessError("Credential not found.", 404)
            self._revision(dict(row), payload)
            state = "deleted" if payload.get("delete") is True else "revoked"
            database.execute("UPDATE credentials SET state=?,salt=NULL,digest=NULL,revision=revision+1,label=? WHERE id=?",
                             (state, "Deleted PIN" if state == "deleted" else row["label"], row["id"]))
            self._audit(database, actor, "credential." + state, row["id"])

    def extension(self, payload, actor):
        if payload.get("confirmed") is not True:
            raise AccessError("Confirm the extension action first.")
        with self.connection() as database:
            action = payload.get("action", "request")
            if action == "request":
                reservation = self._record(database, "reservations", payload.get("reservation_id", ""))
                self._revision(reservation, payload)
                new_end = timestamp(payload.get("new_end"), reservation["timezone"], True)
                if reservation["status"] != "confirmed" or timestamp(reservation["end_at"], reservation["timezone"]) <= self.clock():
                    raise AccessError("Only an upcoming or active confirmed stay can be extended. Create a new stay after checkout.")
                if new_end <= timestamp(reservation["end_at"], reservation["timezone"]):
                    raise AccessError("The proposed checkout must be later than the current checkout.")
                identifier = secrets.token_hex(16)
                reason = clean_text(payload.get("reason"), "Extension reason", 300, True)
                database.execute("INSERT INTO extensions VALUES(?,?,?,?,?,'pending',?,NULL,?)",
                                 (identifier, reservation["id"], reservation["revision"], new_end, reason, actor["id"], self.clock()))
                self._audit(database, actor, "extension.requested", identifier, f"Checkout {reservation['end_at']} → {iso_time(new_end)}")
                return {"id": identifier, "state": "pending"}
            if action not in ("approve", "reject"):
                raise AccessError("Unknown extension action.")
            extension = database.execute("SELECT * FROM extensions WHERE id=?", (payload.get("id", ""),)).fetchone()
            if extension is None or extension["state"] != "pending":
                raise AccessError("This extension is no longer pending.", 409)
            reservation = self._record(database, "reservations", extension["reservation_id"])
            old_checkout = reservation["end_at"]
            if action == "approve":
                if reservation["revision"] != extension["base_revision"] or reservation["status"] != "confirmed":
                    raise AccessError("The stay changed after this request. Reject it and request a new extension.", 409)
                old_end = timestamp(reservation["end_at"], reservation["timezone"])
                if old_end <= self.clock():
                    raise AccessError("Checkout has passed. Expired access cannot be reactivated by extension.", 409)
                self._check_availability(database, reservation["rooms"], timestamp(reservation["start_at"], reservation["timezone"]), extension["new_end"], reservation["id"])
                reservation["end_at"] = iso_time(extension["new_end"])
                self._put(database, "reservations", reservation, reservation["id"], reservation["revision"])
                person = self._record(database, "people", reservation["person_id"])
                person_end = timestamp(person.get("end_at"), person["timezone"])
                end = min(extension["new_end"], person_end) if person_end is not None else extension["new_end"]
                database.execute("UPDATE credentials SET end_at=?,revision=revision+1 WHERE reservation_id=? AND state='active' AND end_at>?",
                                 (end, reservation["id"], self.clock()))
            state = "approved" if action == "approve" else "rejected"
            database.execute("UPDATE extensions SET state=?,reviewed_by=? WHERE id=?", (state, actor["id"], extension["id"]))
            self._audit(database, actor, "extension." + state, extension["id"], f"Checkout {old_checkout} → {iso_time(extension['new_end'])}")
            return {"state": state}

    def list_records(self, collection, search="", offset=0):
        if collection not in COLLECTIONS | {"activity"}:
            raise AccessError("Unknown Users collection.", 404)
        try:
            offset = max(0, int(offset))
        except (ValueError, TypeError):
            raise AccessError("Invalid list position.") from None
        search = clean_text(search, "Search", 100)
        with self.connection() as database:
            if collection == "activity":
                rows = database.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100 OFFSET ?", (offset,)).fetchall()
                items = [{**dict(row), "created": iso_time(row["created"])} for row in rows]
                for item in items:
                    subject_type = item["action"].split(".")[0]
                    subject = None
                    if subject_type in COLLECTIONS:
                        subject = database.execute(f"SELECT name FROM {subject_type} WHERE id=? AND property_id='home'", (item["subject"],)).fetchone()
                    elif subject_type == "credential":
                        subject = database.execute("SELECT people.name FROM credentials JOIN people ON people.id=credentials.person_id WHERE credentials.id=?", (item["subject"],)).fetchone()
                    elif subject_type == "extension":
                        subject = database.execute("SELECT reservations.name FROM extensions JOIN reservations ON reservations.id=extensions.reservation_id WHERE extensions.id=?", (item["subject"],)).fetchone()
                    item["subject_name"] = subject[0] if subject else "Removed or unknown record"
                total = database.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            else:
                condition = "property_id='home' AND instr(lower(name),lower(?))>0"
                if collection == "people":
                    condition += " AND json_extract(data,'$.status')!='deleted'"
                total = database.execute(f"SELECT COUNT(*) FROM {collection} WHERE {condition}", (search,)).fetchone()[0]
                rows = database.execute(f"SELECT * FROM {collection} WHERE {condition} ORDER BY name COLLATE NOCASE,id LIMIT 100 OFFSET ?", (search, offset)).fetchall()
                items = [{**json.loads(row["data"]), "id": row["id"], "revision": row["revision"]} for row in rows]
                if collection == "reservations":
                    for item in items:
                        now = self.clock()
                        item["display_status"] = item["status"] if item["status"] != "confirmed" else (
                            "completed" if now >= timestamp(item["end_at"], item["timezone"]) else
                            "upcoming" if now < timestamp(item["start_at"], item["timezone"]) else "in stay")
                        item["guest_name"] = self._record(database, "people", item["person_id"])["name"]
            return {"items": items, "total": total, "next_offset": offset + 100 if offset + 100 < total else None}

    def detail(self, collection, identifier):
        with self.connection() as database:
            result = self._record(database, collection, identifier)
            if collection in ("people", "reservations"):
                field = "person_id" if collection == "people" else "reservation_id"
                result["credentials"] = [self._credential(row) for row in database.execute(f"SELECT * FROM credentials WHERE {field}=? AND state!='deleted' ORDER BY created DESC", (identifier,))]
            if collection == "reservations":
                result["extensions"] = [{**dict(row), "new_end": iso_time(row["new_end"]), "created": iso_time(row["created"])} for row in database.execute("SELECT * FROM extensions WHERE reservation_id=? ORDER BY created DESC", (identifier,))]
            return result

    def verify_pin(self, payload, actor):
        self._rate_limit(actor)
        with self.connection() as database:
            row = database.execute("SELECT * FROM credentials WHERE id=?", (payload.get("id", ""),)).fetchone()
            pin = payload.get("pin", "")
            allowed = row is not None and row["digest"] is not None and self._credential(row)["state"] == "active"
            allowed = allowed and isinstance(pin, str) and bool(re.fullmatch(r"[0-9]{6,10}", pin))
            if allowed:
                secret = hmac.new(self.pepper, pin.encode(), hashlib.sha256).digest()
                digest = hashlib.pbkdf2_hmac("sha256", secret, row["salt"], PIN_ITERATIONS)
                allowed = hmac.compare_digest(digest, row["digest"])
            if allowed:
                person = self._record(database, "people", row["person_id"])
                reservation = self._record(database, "reservations", row["reservation_id"]) if row["reservation_id"] else None
                now = self.clock()
                allowed = person["status"] == "active" and (reservation is None or reservation["status"] == "confirmed")
                allowed = allowed and (person["role"] != "guest" or reservation is not None)
                allowed = allowed and now >= row["created"]
                for item in [person] + ([reservation] if reservation else []):
                    start = timestamp(item.get("start_at"), item["timezone"])
                    end = timestamp(item.get("end_at"), item["timezone"])
                    allowed = allowed and (start is None or now >= start) and (end is None or now < end)
                schedule = person.get("staff_schedule", {})
                if schedule.get("days"):
                    local = datetime.fromtimestamp(now, ZoneInfo(person["timezone"]))
                    allowed = allowed and str(local.weekday()) in schedule["days"] and schedule["start"] <= local.strftime("%H:%M") < schedule["end"]
                if allowed and payload.get("permission"):
                    permission = payload["permission"]
                    group_ids = reservation["groups"] if reservation else person["groups"]
                    groups = [self._record(database, "groups", identifier) for identifier in group_ids]
                    if payload.get("resource"):
                        allowed = allowed and permission in person["permissions"] and any(payload["resource"] in group["resources"] and permission in group["permissions"] for group in groups)
                    else:
                        allowed = allowed and permission in person["permissions"] and permission not in ("unlock", "disarm")
                    allowed = allowed and permission in CAPABILITIES
            self._audit(database, actor, "credential.test_allowed" if allowed else "credential.test_denied", row["id"] if row else "unknown")
            return {"allowed": bool(allowed), "simulation_only": True, "command_sent": False,
                    "message": "PIN and access window accepted for this test. No device command sent." if allowed else "PIN or access policy not accepted."}
