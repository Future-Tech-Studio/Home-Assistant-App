"""Keep reference auditing conservative, read-only, and reviewable."""

import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("reference_audit", Path(__file__).resolve().parents[1] / "scripts/audit_entity_references.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ReferenceAuditTests(unittest.TestCase):
    def reference(self, entity_id, path="target/entity_id"):
        return {"entity_id":entity_id, "path":path, "source":"dashboard", "kind":"json"}

    def test_disabled_missing_and_historical_are_distinct(self):
        report = AUDIT.audit([{"entity_id":"light.disabled", "disabled_by":"user"}, {"entity_id":"light.current"}], [{"entity_id":"light.old"}], [self.reference(value) for value in ("light.disabled", "light.current", "light.old", "light.missing")])
        self.assertEqual(report["issue_counts"], {"disabled":1, "historical_only":1, "unresolved":1})

    def test_service_calls_are_not_entity_references(self):
        report = AUDIT.audit([], [], [self.reference("light.turn_on", "action"), self.reference("light.turn_off", "service")])
        self.assertEqual(report["issues"], [])

    def test_suffix_overlap_is_only_a_review_candidate(self):
        registry = [{"entity_id":"light.pantry_all_lights", "platform":"group"}, {"entity_id":"light.fht_pantry_all_lights", "platform":"group"}]
        report = AUDIT.audit(registry, [], [self.reference("light.pantry_all_lights")])
        self.assertEqual(len(report["group_overlap_candidates"]), 1)
        self.assertIn("not been compared", report["group_overlap_candidates"][0]["evidence"])
        self.assertEqual(registry[0]["entity_id"], "light.pantry_all_lights")

    def test_never_suggests_disabled_replacement(self):
        report = AUDIT.audit([{"entity_id":"light.fht_pantry_all_lights", "disabled_by":"user"}], [], [self.reference("light.pantry_all_lights")])
        self.assertEqual(report["issues"][0]["candidates"], [])

    def test_same_names_in_different_rooms_are_not_duplicates(self):
        registry = [{"entity_id":f"light.room_{number}", "platform":"group", "name":"All Lights", "area_id":str(number)} for number in (1, 2)]
        self.assertEqual(AUDIT.audit(registry, [], [])["group_overlap_candidates"], [])

    def test_yaml_services_and_template_prefixes_are_not_missing_devices(self):
        report = AUDIT.audit([], [], [{"entity_id":"light.turn_on", "path":"line:10", "source":"automations.yaml", "kind":"yaml_candidate"}, self.reference("input_number.fht_delta_")])
        self.assertEqual(report["issue_counts"], {"dynamic_prefix":1})

    def test_managed_definitions_do_not_imply_legacy_group_deletion(self):
        definitions = AUDIT.group_definitions(["light:", "  - platform: group", "    unique_id: fht_pantry_all_lights", "    entities:", "      - light.pantry_1", "      - light.pantry_2"])
        registry = [{"entity_id":"light.fht_pantry_all_lights", "unique_id":"fht_pantry_all_lights", "platform":"group"}, {"entity_id":"light.pantry_all_lights", "unique_id":"pantry_all_lights", "platform":"group"}]
        report = AUDIT.audit(registry, [], [], definitions=definitions)
        self.assertEqual(report["managed_group_definition_review"][0]["members"], ["light.pantry_1", "light.pantry_2"])
        self.assertFalse(report["managed_group_definition_review"][1]["in_managed_package"])
        self.assertEqual(report["scope"]["distinct_referenced_ids"], 0)

    def test_repeated_prefix_proposes_only_an_existing_enabled_entity(self):
        registry = [{"entity_id":"binary_sensor.pantry_door_sensor_opening"}]
        old = "binary_sensor.pantry_pantry_door_sensor_opening"
        report = AUDIT.audit(registry, [], [self.reference(old)])
        self.assertEqual(report["issues"][0]["candidates"][0]["entity_id"], registry[0]["entity_id"])
        self.assertEqual(report["issues"][0]["entity_id"], old)
        registry[0]["disabled_by"] = "user"
        self.assertEqual(AUDIT.audit(registry, [], [self.reference(old)])["issues"][0]["candidates"], [])
