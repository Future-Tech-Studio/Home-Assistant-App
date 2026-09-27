"""Users and scheduled credential regression tests without live device actions."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("access_test", ROOT / "future_homes_tech_app/fht_access.py")
ACCESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCESS)
ACTOR = {"id": "a" * 32, "name": "Owner"}
CATALOG = {"rooms": [{"id": "bedroom2", "name": "Bailey's Bedroom"}, {"id": "bedroom6", "name": "Chloe's Bedroom"}],
           "resources": [{"id": "lock.front", "name": "Front Entry"}, {"id": "lock.bedroom2", "name": "Bedroom Door"}]}


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = ACCESS.timestamp("2026-09-12T12:00:00-07:00", "America/Phoenix")
        self.store = ACCESS.AccessStore(Path(self.directory.name) / "private", lambda: self.now)

    def tearDown(self):
        self.directory.cleanup()

    def person(self, **changes):
        return self.store.save("people", {"name": "Alex", "role": "resident", "rooms": ["bedroom2"], "confirmed": True, **changes}, ACTOR, CATALOG)

    def reservation(self, person, **changes):
        return self.store.save("reservations", {
            "name": "Alex's stay", "person_id": person["id"], "rooms": ["bedroom2"],
            "start_at": "2026-09-12T13:00", "end_at": "2026-09-14T10:00", "confirmed": True, **changes,
        }, ACTOR, CATALOG)

    def pin(self, person, reservation=None, **changes):
        return self.store.issue_pin({"person_id": person["id"], "person_revision": person["revision"],
                                     "reservation_id": reservation["id"] if reservation else None,
                                     "generate": False, "pin": "029481", "confirmed": True, **changes}, ACTOR)

    def verify(self, issued, **changes):
        return self.store.verify_pin({"id": issued["credential"]["id"], "pin": issued["pin"], **changes}, ACTOR)["allowed"]

    def test_storage_is_lazy_private_and_restart_persistent(self):
        self.assertFalse(self.store.path.exists())
        person = self.person()
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)
        restarted = ACCESS.AccessStore(self.store.directory, lambda: self.now)
        self.assertEqual(restarted.detail("people", person["id"])["name"], "Alex")

    def test_disabled_person_can_be_configured_but_not_issued_pin(self):
        person = self.person(status="disabled", permissions=["room_modes"])
        self.assertEqual(person["permissions"], ["room_modes"])
        with self.assertRaises(ACCESS.AccessError):
            self.pin(person)

    def test_generate_and_manual_pin_are_never_in_detail_database_or_audit(self):
        person = self.person()
        issued = self.pin(person)
        self.assertEqual(issued["pin"], "029481")
        self.assertTrue(self.verify(issued))
        self.assertFalse(self.verify(issued, pin="839254"))
        details = json.dumps(self.store.detail("people", person["id"]))
        self.assertNotIn(issued["pin"], details)
        self.assertNotIn("fingerprint", details)
        self.assertNotIn("digest", details)
        self.assertNotIn(issued["pin"], self.store.path.read_bytes().decode("latin1"))
        self.assertNotIn(issued["pin"], json.dumps(self.store.list_records("activity")))
        generated = self.pin(person, generate=True)
        self.assertRegex(generated["pin"], r"^\d{6}$")
        self.assertFalse(generated["credential"]["physical_access_installed"])

    def test_common_duplicate_and_numeric_pins_are_rejected(self):
        person = self.person()
        for value in ("123456", "111111", 123456, "1245", "abcdef"):
            with self.assertRaises(ACCESS.AccessError):
                self.pin(person, pin=value)
        self.pin(person)
        with self.assertRaises(ACCESS.AccessError):
            self.pin(person)

    def test_guest_requires_own_confirmed_reservation(self):
        guest = self.person(role="guest")
        with self.assertRaises(ACCESS.AccessError):
            self.pin(guest)
        other = self.person(name="Other")
        stay = self.reservation(other)
        with self.assertRaises(ACCESS.AccessError):
            self.pin(guest, stay)

    def test_changing_resident_to_guest_revokes_permanent_pin(self):
        person = self.person()
        issued = self.pin(person)
        self.person(**{**person, "role": "guest"})
        self.assertFalse(self.verify(issued))
        self.assertEqual(self.store.detail("people", person["id"])["credentials"][0]["state"], "revoked")

    def test_used_access_group_is_protected_but_cancelled_stay_does_not_trap_it(self):
        group = self.store.save("groups", {"name": "Guest doors", "resources": ["lock.front"], "permissions": ["unlock"], "confirmed": True}, ACTOR, CATALOG)
        person = self.person(role="guest", permissions=["unlock"])
        stay = self.reservation(person, groups=[group["id"]])
        with self.assertRaises(ACCESS.AccessError):
            self.store.remove("groups", {**group, "confirmed": True}, ACTOR)
        self.store.remove("reservations", {**stay, "confirmed": True}, ACTOR)
        self.store.remove("groups", {**group, "confirmed": True}, ACTOR)
        self.assertEqual(self.store.list_records("groups")["items"], [])

    def test_group_permission_cannot_override_person_denial(self):
        group = self.store.save("groups", {"name": "Owner doors", "resources": ["lock.front"], "permissions": ["unlock"], "confirmed": True}, ACTOR, CATALOG)
        issued = self.pin(self.person(role="child", groups=[group["id"]]))
        self.assertFalse(self.verify(issued, permission="unlock", resource="lock.front"))

    def test_window_start_inclusive_end_exclusive_even_after_restart(self):
        guest = self.person(role="guest")
        stay = self.reservation(guest)
        issued = self.pin(guest, stay)
        self.assertFalse(self.verify(issued))
        self.now = ACCESS.timestamp(stay["start_at"], stay["timezone"])
        self.assertTrue(self.verify(issued))
        self.now = ACCESS.timestamp(stay["end_at"], stay["timezone"])
        self.store = ACCESS.AccessStore(self.store.directory, lambda: self.now)
        self.assertFalse(self.verify(issued))
        self.assertEqual(self.store.detail("people", guest["id"])["credentials"][0]["state"], "expired")

    def test_disabled_and_deleted_people_revoke_secrets_without_ha_changes(self):
        person = self.person(contact="private@example.com")
        issued = self.pin(person)
        disabled = self.person(**{**person, "status": "disabled"})
        self.assertFalse(self.verify(issued))
        active = self.person(**{**disabled, "status": "active"})
        self.assertFalse(self.verify(issued))
        self.store.remove("people", {**active, "confirmed": True}, ACTOR)
        self.assertEqual(self.store.list_records("people")["items"], [])
        self.assertEqual(self.store.detail("people", active["id"])["contact"], "")
        with sqlite3.connect(self.store.path) as database:
            self.assertIsNone(database.execute("SELECT digest FROM credentials").fetchone()[0])

    def test_replacing_pin_retires_old_and_revocation_never_reveals_secret(self):
        person = self.person()
        issued = self.pin(person)
        replacement = self.pin(person, replace_id=issued["credential"]["id"], revision=1, pin="829471")
        self.assertFalse(self.verify(issued))
        self.assertTrue(self.verify(replacement))
        self.store.revoke_pin({"id": replacement["credential"]["id"], "revision": 1, "delete": True, "confirmed": True}, ACTOR)
        self.assertFalse(self.verify(replacement))

    def test_extension_is_pending_until_approved_and_records_actor(self):
        guest = self.person(role="guest")
        stay = self.reservation(guest)
        issued = self.pin(guest, stay)
        request = self.store.extension({"reservation_id": stay["id"], "revision": stay["revision"], "new_end": "2026-09-14T12:00", "reason": "Late checkout approved by owner", "confirmed": True}, ACTOR)
        self.assertEqual(self.store.detail("reservations", stay["id"])["end_at"], stay["end_at"])
        self.store.extension({"id": request["id"], "action": "approve", "confirmed": True}, ACTOR)
        self.now = ACCESS.timestamp("2026-09-14T11:00", "America/Phoenix")
        self.assertTrue(self.verify(issued))
        detail = self.store.detail("reservations", stay["id"])
        self.assertEqual(detail["extensions"][0]["reviewed_by"], ACTOR["id"])
        audit = next(item for item in self.store.list_records("activity")["items"] if item["action"] == "extension.approved")
        self.assertIn(stay["end_at"], audit["detail"])
        self.assertIn(detail["end_at"], audit["detail"])
        self.assertEqual(audit["subject_name"], stay["name"])

    def test_expired_revoked_credentials_are_not_resurrected_by_extension(self):
        guest = self.person(role="guest")
        stay = self.reservation(guest)
        issued = self.pin(guest, stay)
        self.store.revoke_pin({"id": issued["credential"]["id"], "revision": 1, "confirmed": True}, ACTOR)
        request = self.store.extension({"reservation_id": stay["id"], "revision": stay["revision"], "new_end": "2026-09-14T12:00", "reason": "Late checkout", "confirmed": True}, ACTOR)
        self.store.extension({"id": request["id"], "action": "approve", "confirmed": True}, ACTOR)
        self.assertFalse(self.verify(issued))
        self.now = ACCESS.timestamp("2026-09-14T13:00", "America/Phoenix")
        with self.assertRaises(ACCESS.AccessError):
            self.store.extension({"reservation_id": stay["id"], "revision": 2, "new_end": "2026-09-15T12:00", "reason": "Too late", "confirmed": True}, ACTOR)

    def test_direct_edit_cannot_bypass_extension_approval(self):
        stay = self.reservation(self.person())
        with self.assertRaises(ACCESS.AccessError):
            self.reservation(self.store.detail("people", stay["person_id"]), **{**stay, "end_at": "2026-09-15T10:00"})

    def test_overlaps_and_stale_extensions_are_rejected(self):
        guest = self.person()
        stay = self.reservation(guest)
        with self.assertRaises(ACCESS.AccessError):
            self.reservation(guest)
        self.reservation(guest, rooms=["bedroom6"])
        self.reservation(guest, start_at="2026-09-14T10:00", end_at="2026-09-15T10:00")
        request = self.store.extension({"reservation_id": stay["id"], "revision": 1, "new_end": "2026-09-14T12:00", "reason": "Overlap", "confirmed": True}, ACTOR)
        with self.assertRaises(ACCESS.AccessError):
            self.store.extension({"id": request["id"], "action": "approve", "confirmed": True}, ACTOR)
        self.store.remove("reservations", {**stay, "confirmed": True}, ACTOR)
        with self.assertRaises(ACCESS.AccessError):
            self.store.extension({"id": request["id"], "action": "approve", "confirmed": True}, ACTOR)

    def test_cancellation_revokes_stay_only_and_keeps_resident_credential(self):
        resident = self.person()
        permanent = self.pin(resident)
        stay = self.reservation(resident)
        temporary = self.pin(resident, stay, pin="834926")
        self.store.remove("reservations", {**stay, "confirmed": True}, ACTOR)
        self.assertTrue(self.verify(permanent))
        self.assertFalse(self.verify(temporary))

    def test_room_assignment_does_not_grant_unlock_or_disarm(self):
        issued = self.pin(self.person(role="child"))
        self.assertFalse(self.verify(issued, permission="unlock", resource="lock.bedroom2"))
        self.assertFalse(self.verify(issued, permission="disarm"))

    def test_explicit_resource_permissions_and_no_execution(self):
        group = self.store.save("groups", {"name": "Bedroom 2 guest", "resources": ["lock.bedroom2"], "permissions": ["unlock"], "confirmed": True}, ACTOR, CATALOG)
        person = self.person(groups=[group["id"]], permissions=["unlock"])
        issued = self.pin(person)
        self.assertTrue(self.verify(issued, permission="unlock", resource="lock.bedroom2"))
        self.assertFalse(self.verify(issued, permission="unlock", resource="lock.front"))
        result = self.store.verify_pin({"id": issued["credential"]["id"], "pin": issued["pin"]}, ACTOR)
        self.assertFalse(result["command_sent"])
        self.assertTrue(result["simulation_only"])

    def test_recurring_staff_hours_and_person_time_limit(self):
        person = self.person(role="staff", staff_schedule={"days": ["5"], "start": "13:00", "end": "15:00"}, end_at="2026-09-13T12:00")
        issued = self.pin(person)
        self.assertFalse(self.verify(issued))
        self.now += 3600
        self.assertTrue(self.verify(issued))
        self.now += 7200
        self.assertFalse(self.verify(issued))

    def test_foreign_unknown_ids_permissions_and_stale_revision_rejected(self):
        for changes in ({"rooms": ["another-property"]}, {"groups": ["other-group"]}, {"permissions": ["manage_ha_admin"]}):
            with self.assertRaises(ACCESS.AccessError):
                self.person(**changes)
        person = self.person()
        self.person(**{**person, "name": "Alex Updated"})
        with self.assertRaises(ACCESS.AccessError):
            self.person(**person)

    def test_timezone_dst_gap_and_ambiguity_rejected(self):
        for value in ("2026-03-08T02:30", "2026-11-01T01:30"):
            with self.assertRaises(ACCESS.AccessError):
                ACCESS.timestamp(value, "America/New_York")
        self.assertIsInstance(ACCESS.timestamp("2026-11-01T01:30-04:00", "America/New_York"), float)

    def test_pin_rate_limit_survives_restart(self):
        for attempt in range(10):
            self.store.verify_pin({"id": "missing", "pin": "439027"}, ACTOR)
        self.store = ACCESS.AccessStore(self.store.directory, lambda: self.now)
        with self.assertRaises(ACCESS.AccessError) as error:
            self.store.verify_pin({"id": "missing", "pin": "439027"}, ACTOR)
        self.assertEqual(error.exception.status, 429)

    def test_missing_key_and_future_schema_fail_closed(self):
        self.person()
        with sqlite3.connect(self.store.path) as database:
            database.execute("PRAGMA user_version=999")
        with self.assertRaises(ACCESS.AccessError):
            ACCESS.AccessStore(self.store.directory).list_records("people")
        self.store.directory.joinpath("pin-verification.key").unlink()
        with self.assertRaises(ACCESS.AccessError):
            ACCESS.AccessStore(self.store.directory).list_records("people")

    def test_pagination_and_panel_configuration_do_not_enroll_hardware(self):
        for number in range(105):
            self.person(name=f"Person {number:03}")
        self.assertEqual(len(self.store.list_records("people")["items"]), 100)
        self.assertEqual(len(self.store.list_records("people", offset=100)["items"]), 5)
        panel = self.store.save("panels", {"name": "Bedroom display", "rooms": ["bedroom2"], "modules": ["lights"], "confirmed": True}, ACTOR, CATALOG)
        self.assertEqual(panel["device_access"], "not_enrolled")


class AccessAdminTests(unittest.TestCase):
    def setUp(self):
        self.users = Mock(return_value=[{**ACTOR, "is_active": True, "is_owner": True, "group_ids": []}])
        self.admin = ACCESS.AccessAdmin(self.users)
        self.headers = {"X-Remote-User-Id": ACTOR["id"]}

    def test_only_trusted_proxy_active_admin_is_accepted(self):
        self.assertEqual(self.admin.authenticate("172.30.32.2", "172.30.32.2", self.headers)["id"], ACTOR["id"])
        for peer, headers in (("10.1.0.20", self.headers), ("172.30.32.2", {}), ("172.30.32.2", {"X-Remote-User-Id": "b" * 32})):
            with self.assertRaises(ACCESS.AccessError):
                self.admin.authenticate(peer, "172.30.32.2", headers)

    def test_write_rechecks_admin_and_fails_when_upstream_unavailable(self):
        self.admin.authenticate("proxy", "proxy", self.headers)
        self.users.return_value = [{**ACTOR, "is_active": True, "is_owner": False, "group_ids": []}]
        with self.assertRaises(ACCESS.AccessError):
            self.admin.authenticate("proxy", "proxy", self.headers, fresh=True)
        self.users.side_effect = RuntimeError("upstream disconnected")
        with self.assertRaises(ACCESS.AccessError):
            self.admin.authenticate("proxy", "proxy", self.headers, fresh=True)

    def test_csrf_bound_to_actor_and_same_site_json(self):
        headers = {"Content-Type": "application/json", "X-FHT-Access-CSRF": self.admin.csrf(ACTOR)}
        self.admin.check_csrf(ACTOR, headers)
        for invalid in ({}, {**headers, "Sec-Fetch-Site": "cross-site"}, {**headers, "Content-Type": "text/plain"}):
            with self.assertRaises(ACCESS.AccessError):
                self.admin.check_csrf(ACTOR, invalid)
        with self.assertRaises(ACCESS.AccessError):
            self.admin.check_csrf({"id": "b" * 32}, headers)


if __name__ == "__main__":
    unittest.main()
