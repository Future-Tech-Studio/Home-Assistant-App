"""Protect existing assignments while repairing verified references."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("repair", Path(__file__).resolve().parents[1] / "future_homes_tech_app/repair_references.py")
REPAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPAIR)
OLD = "binary_sensor.pantry_pantry_door_sensor_opening"
NEW = "binary_sensor.pantry_door_sensor_opening"


class ReferenceRepairTests(unittest.TestCase):
    def test_retired_bathroom_group_moves_to_all_lights(self):
        old = "light.fht_bathroom_1_all_bathroom_lights"
        new = "light.fht_bathroom_1_all_lights"
        registry = [{"entity_id": entity_id, "platform": "group", "unique_id": entity_id.split(".")[1]} for entity_id in [old, new]]
        self.assertEqual(REPAIR.verified_mapping(registry, {new: {"state": "off"}}), {old: new})
        self.assertEqual(REPAIR.verified_mapping(registry, {}), {})

    def test_current_settings_win_in_either_order(self):
        for payload in ({OLD: {"night": 25}, NEW: {"night": 28}},
                        {NEW: {"night": 28}, OLD: {"night": 25}}):
            conflicts = []
            self.assertEqual(REPAIR.rewrite(payload, {OLD: NEW}, True, conflicts),
                             {NEW: {"night": 28}})
            self.assertEqual(conflicts, [{"archived_key": OLD, "retained_key": NEW}])

    def test_multiple_legacy_values_without_current_still_reject(self):
        with self.assertRaises(ValueError):
            REPAIR.rewrite({OLD: 25, "light.old": 28},
                           {OLD: NEW, "light.old": NEW}, prefer_current=True)

    def test_current_policy_archives_original_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            payload = {OLD: {"night": 25}, NEW: {"night": 28}}
            name = "presence_mode_settings.json"
            (data / name).write_text(json.dumps(payload))
            manifest = REPAIR.migrate(data, [{"entity_id": NEW}],
                                      {NEW: {"state": "off"}}, prefer_current=True)
            self.assertEqual(json.loads((data / name).read_text()), {NEW: {"night": 28}})
            self.assertEqual(json.loads((data / f"reference-repair-{REPAIR.VERSION}" / name).read_text()), payload)
            self.assertEqual(len(manifest["archived_conflicts"][name]), 1)
            self.assertEqual(manifest["status"], "complete")

    def test_reviewed_batch_and_live_guards(self):
        self.assertEqual(len(REPAIR.RENAMES), 18)
        registry = [{"entity_id": NEW}]
        states = {NEW: {"state": "off"}}
        self.assertEqual(REPAIR.verified_mapping(registry, states), {OLD: NEW})
        self.assertEqual(REPAIR.verified_mapping(registry, {}), {})
        self.assertEqual(REPAIR.verified_mapping(registry + [{"entity_id": OLD}], states), {})
        self.assertEqual(REPAIR.verified_mapping(registry, {**states, OLD: {}}), {})
        registry[0]["disabled_by"] = "user"
        self.assertEqual(REPAIR.verified_mapping(registry, states), {})

    def group_fixture(self):
        groups = ["light.pantry_lights", "light.fht_pantry_all_lights"]
        registry = [{"entity_id": entity, "platform": "group", "unique_id": entity.split(".")[1]} for entity in groups]
        states = {entity: {"state": "on", "attributes": {"entity_id": ["light.one", "light.two"]}} for entity in groups}
        states.update({entity: {"state": "on"} for entity in ("light.one", "light.two")})
        return registry, states

    def test_groups_require_exact_live_membership(self):
        registry, states = self.group_fixture()
        self.assertEqual(REPAIR.verified_mapping(registry, states), {"light.pantry_lights": "light.fht_pantry_all_lights"})
        states["light.pantry_lights"]["attributes"]["entity_id"] = ["light.one"]
        self.assertEqual(REPAIR.verified_mapping(registry, states), {})

    def test_offline_cycles_empty_and_missing_members_not_merged(self):
        for children in ([], ["light.missing"], ["light.pantry_lights"]):
            registry, states = self.group_fixture()
            states["light.pantry_lights"]["attributes"]["entity_id"] = children
            self.assertEqual(REPAIR.verified_mapping(registry, states), {})
        registry, states = self.group_fixture()
        states["light.one"]["state"] = "unavailable"
        self.assertEqual(REPAIR.verified_mapping(registry, states), {})

    def test_encoded_keys_lists_and_text(self):
        payload = {f"door:{OLD}|night": [OLD, NEW], "url": "https://example.org/" + OLD, "name": OLD, "message": "Use " + OLD}
        rewritten = REPAIR.rewrite(payload, {OLD: NEW})
        self.assertEqual(rewritten[f"door:{NEW}|night"], [NEW])
        for field in ("url", "name", "message"):
            self.assertEqual(payload[field], rewritten[field])
        self.assertEqual(REPAIR.replace_atom("light_group:light.old", {"light.old": "light.new"}), "light_group:light.new")

    def test_conflicts_never_overwrite(self):
        with self.assertRaises(ValueError):
            REPAIR.rewrite({OLD: "light.one", NEW: "light.two"}, {OLD: NEW})
        self.assertEqual(REPAIR.rewrite({OLD: "light.one", NEW: "light.one"}, {OLD: NEW}), {NEW: "light.one"})

    def test_backups_persistence_and_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / REPAIR.FILES[0]
            original = json.dumps({OLD: "light.one"}).encode()
            settings.write_bytes(original)
            report = REPAIR.migrate(root, [{"entity_id": NEW}], {NEW: {"state": "off"}})
            self.assertEqual(json.loads(settings.read_text()), {NEW: "light.one"})
            backup = root / f"reference-repair-{REPAIR.VERSION}"
            self.assertEqual((backup / settings.name).read_bytes(), original)
            self.assertEqual(report["registry_entities_deleted"], 0)
            self.assertEqual(REPAIR.migrate(root, [], {}), report)

    def test_conflict_preflights_entire_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = [root / name for name in REPAIR.FILES[:2]]
            first.write_text(json.dumps({OLD: "light.one"}))
            second.write_text(json.dumps({OLD: "light.one", NEW: "light.two"}))
            original = first.read_bytes()
            with self.assertRaises(ValueError):
                REPAIR.migrate(root, [{"entity_id": NEW}], {NEW: {"state": "off"}})
            self.assertEqual(first.read_bytes(), original)
            self.assertFalse((root / f"reference-repair-{REPAIR.VERSION}/manifest.json").exists())

    def test_write_failure_restores_original_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / REPAIR.FILES[0]
            original = json.dumps({OLD: "light.one"}).encode()
            settings.write_bytes(original)
            atomic = REPAIR.atomic_write
            failed = []

            def fail_once(path, content):
                if path == settings and not failed:
                    failed.append(True)
                    raise OSError("simulated disk failure")
                atomic(path, content)

            with patch.object(REPAIR, "atomic_write", side_effect=fail_once):
                with self.assertRaises(OSError):
                    REPAIR.migrate(root, [{"entity_id": NEW}], {NEW: {"state": "off"}})
            self.assertEqual(settings.read_bytes(), original)
            with self.assertRaises(RuntimeError):
                REPAIR.migrate(root, [], {})
            self.assertEqual(settings.read_bytes(), original)

    def test_repair_runs_before_generators(self):
        root = Path(__file__).resolve().parents[1]
        startup = (root / "future_homes_tech_app/run.sh").read_text()
        self.assertLess(startup.index("if future-homes-tech-repair-references"), startup.index("if ! future-homes-tech-configure"))


if __name__ == "__main__":
    unittest.main()
