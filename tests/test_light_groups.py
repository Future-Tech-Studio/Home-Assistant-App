"""Tests for Future Homes Tech light-group generation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = (
    Path(__file__).parents[1]
    / "future_homes_tech_app"
    / "generate_light_groups.py"
)
SPEC = importlib.util.spec_from_file_location(
    "generate_light_groups",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class LightGroupGeneratorTests(unittest.TestCase):
    """Verify deterministic, non-destructive generated light groups."""

    def _write_registry(
        self,
        config_directory: Path,
        filename: str,
        key: str,
        values: list[dict[str, object]],
    ) -> None:
        """Write one minimal Home Assistant storage registry."""
        storage_directory = config_directory / ".storage"
        storage_directory.mkdir(parents=True, exist_ok=True)
        storage_directory.joinpath(filename).write_text(
            json.dumps({"data": {key: values}}),
            encoding="utf-8",
        )

    def _create_registries(self, config_directory: Path) -> None:
        """Create representative area, device, and entity registries."""
        self._write_registry(
            config_directory,
            "core.area_registry",
            "areas",
            [
                {"area_id": "kitchen", "name": "Kitchen"},
                {"area_id": "bathroom_1", "name": "Bathroom 1"},
            ],
        )
        self._write_registry(
            config_directory,
            "core.device_registry",
            "devices",
            [
                {"id": "device-kitchen", "area_id": "kitchen"},
                {"id": "device-bathroom", "area_id": "bathroom_1"},
            ],
        )
        self._write_registry(
            config_directory,
            "core.entity_registry",
            "entities",
            [
                {
                    "entity_id": "light.kitchen_kitchen_bar_light_1",
                    "device_id": "device-kitchen",
                    "platform": "hue",
                    "original_name": "Kitchen Bar Light 1",
                },
                {
                    "entity_id": "light.kitchen_kitchen_bar_light_2",
                    "device_id": "device-kitchen",
                    "platform": "hue",
                    "original_name": "Kitchen Bar Light 2",
                },
                {
                    "entity_id": "light.kitchen_all_lights",
                    "area_id": "kitchen",
                    "platform": "group",
                    "original_name": "Kitchen All Lights",
                },
                {
                    "entity_id": (
                        "light.bathroom_1_bathroom_1_"
                        "vanity_light_1"
                    ),
                    "device_id": "device-bathroom",
                    "platform": "hue",
                    "original_name": "Bathroom 1 Vanity Light 1",
                },
                {
                    "entity_id": (
                        "light.bathroom_1_bathroom_1_"
                        "toilet_light_1"
                    ),
                    "device_id": "device-bathroom",
                    "platform": "hue",
                    "original_name": "Bathroom 1 Toilet Light 1",
                },
            ],
        )

    def test_switch_rgb_indicator_is_not_room_lighting(self) -> None:
        self.assertTrue(GENERATOR._is_excluded("light.kitchen_switch_rgb_light", "Kitchen Switch", "matter"))
        self.assertTrue(GENERATOR._is_excluded("light.kitchen_switch_1g_rgb_indicator_light", "Kitchen Switch", "matter"))
        self.assertFalse(GENERATOR._is_excluded("light.kitchen_switch_under_cabinet_light_1", "Kitchen Switch", "matter"))
        self.assertFalse(GENERATOR._is_excluded("light.kitchen_rgb_strip", "Kitchen RGB Strip", "matter"))

    def test_generates_prefixed_entities_with_clean_names(self) -> None:
        """Create FHT entities with unprefixed friendly names."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._create_registries(config_directory)

            content, count = GENERATOR.render_light_groups(
                config_directory
            )

        # Kitchen All Lights and Bathroom 1 All Lights; single lights get no group.
        self.assertEqual(count, 2)
        self.assertIn('name: "FHT - Kitchen All Lights"', content)
        self.assertNotIn('name: "FHT - Kitchen Bar Lights"', content)
        self.assertNotIn(
            'friendly_name: "FHT - Kitchen All Lights"',
            content,
        )
        self.assertIn("unique_id: fht_kitchen_all_lights", content)
        self.assertNotIn("unique_id: fht_kitchen_bar_lights", content)
        self.assertIn(
            "    light.fht_kitchen_all_lights:\n"
            '      friendly_name: "Kitchen All Lights"\n'
            '      fht_area: "Kitchen"',
            content,
        )
        self.assertNotIn(
            "      - light.kitchen_all_lights",
            content,
        )

    def test_bathroom_uses_all_lights_including_toilet(self) -> None:
        """Keep one aggregate bathroom group including toilet lights."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._create_registries(config_directory)

            content, _ = GENERATOR.render_light_groups(
                config_directory
            )

        bathroom_group = content.split(
            'name: "FHT - Bathroom 1 All Lights"',
            1,
        )[1].split("- platform: group", 1)[0]
        self.assertIn("vanity_light_1", bathroom_group)
        self.assertIn("toilet_light_1", bathroom_group)
        self.assertNotIn("All Bathroom Lights", content)
        self.assertNotIn('name: "FHT - Bathroom 1 Toilet Light"', content)
        self.assertIn(
            "# fht_replaced_group: light.fht_bathroom_1_toilet_lights -> light.bathroom_1_bathroom_1_toilet_light_1\n",
            content,
        )

    def test_single_light_joins_all_lights_without_its_own_group(self) -> None:
        """Fan Lights, the lamp itself, and All Lights covering both."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._write_registry(config_directory, "core.area_registry", "areas",
                                 [{"area_id": "bedroom_4", "name": "Bedroom 4"}])
            self._write_registry(config_directory, "core.device_registry", "devices", [
                {"id": f"device-{index}", "area_id": "bedroom_4", "name": name}
                for index, name in enumerate(("Bedroom 4 Fan Light 1", "Bedroom 4 Fan Light 2", "Bedroom 4 Lamp"))])
            self._write_registry(config_directory, "core.entity_registry", "entities", [
                {"entity_id": entity_id, "device_id": f"device-{index}", "platform": "hue"}
                for index, entity_id in enumerate(("light.bedroom_4_fan_light_1", "light.bedroom_4_fan_light_2", "light.bedroom_4_lamp"))])

            content, _ = GENERATOR.render_light_groups(config_directory)

        self.assertIn('name: "FHT - Bedroom 4 Fan Lights"', content)
        self.assertIn('name: "FHT - Bedroom 4 All Lights"', content)
        self.assertNotIn("Bedroom 4 Lamp", content.split("light:\n", 1)[1])
        all_lights = content.split('name: "FHT - Bedroom 4 All Lights"', 1)[1].split("\n\n", 1)[0]
        self.assertIn("- light.bedroom_4_lamp", all_lights)
        self.assertIn("- light.bedroom_4_fan_light_2", all_lights)

    def test_combined_groups_keep_location_words(self) -> None:
        """Her and his vanities combine as Bathroom Vanity Lights; no duplicate toilet group."""
        names = ["Master Bedroom Bathroom Her Vanity Light 1", "Master Bedroom Bathroom Her Vanity Light 2",
                 "Master Bedroom Bathroom His Vanity Light 1", "Master Bedroom Bathroom His Vanity Light 2",
                 "Master Bedroom Bathroom Toilet Light 1", "Master Bedroom Bathroom Toilet Light 2"]
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._write_registry(config_directory, "core.area_registry", "areas",
                                 [{"area_id": "master", "name": "Master Bedroom"}])
            self._write_registry(config_directory, "core.device_registry", "devices", [
                {"id": f"device-{index}", "area_id": "master", "name": name} for index, name in enumerate(names)])
            self._write_registry(config_directory, "core.entity_registry", "entities", [
                {"entity_id": "light." + name.lower().replace(" ", "_"), "device_id": f"device-{index}", "platform": "hue"}
                for index, name in enumerate(names)])

            content, _ = GENERATOR.render_light_groups(config_directory)

        self.assertIn('name: "FHT - Master Bedroom Bathroom Vanity Lights"', content)
        self.assertNotIn('name: "FHT - Master Bedroom Vanity Lights"', content)
        self.assertNotIn('name: "FHT - Master Bedroom Toilet Lights"', content)
        self.assertIn('name: "FHT - Master Bedroom Bathroom Toilet Lights"', content)
        self.assertIn("# fht_replaced_group: light.fht_master_bedroom_vanity_lights -> "
                      "light.fht_master_bedroom_bathroom_vanity_lights\n", content)
        self.assertIn("# fht_replaced_group: light.fht_master_bedroom_toilet_lights -> "
                      "light.fht_master_bedroom_bathroom_toilet_lights\n", content)

    def _bedroom_6(self, config_directory: Path) -> None:
        names = ["Bedroom 6 Fan Light 1", "Bedroom 6 Fan Light 2", "Bedroom 6 Desk Light"]
        self._write_registry(config_directory, "core.area_registry", "areas", [{"area_id": "b6", "name": "Bedroom 6"}])
        self._write_registry(config_directory, "core.device_registry", "devices", [
            {"id": f"device-{index}", "area_id": "b6", "name": name} for index, name in enumerate(names)])
        self._write_registry(config_directory, "core.entity_registry", "entities", [
            {"entity_id": "light." + name.lower().replace(" ", "_"), "device_id": f"device-{index}", "platform": "hue"}
            for index, name in enumerate(names)])

    def test_plan_explains_each_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._bedroom_6(config_directory)
            plan: list = []
            GENERATOR.render_light_groups(config_directory, overrides={}, plan=plan)
        room = plan[0]
        self.assertEqual(room["area"], "Bedroom 6")
        self.assertEqual([(group["name"], group["reason"]) for group in room["groups"]], [
            ("Bedroom 6 All Lights", "Every light in the room."),
            ("Bedroom 6 Fan Lights", "Lights whose names include “Fan”."),
        ])
        self.assertIn("Only one light matches “Desk”, so it is offered as the light itself.", room["notes"])
        self.assertEqual(len(room["lights"]), 3)

    def test_overrides_rename_groups_and_keep_lights_out(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._bedroom_6(config_directory)
            overrides = {"excluded_lights": {"light.bedroom_6_desk_light"},
                         "names": {"fht_bedroom_6_fan_lights": "Chloe's Fan"}}
            content, _ = GENERATOR.render_light_groups(config_directory, overrides=overrides)
            path = config_directory / "overrides.json"
            path.write_text(json.dumps({"excluded_lights": ["light.x"], "names": {"fht_a": " Name ", "fht_b": ""}}))
            loaded = GENERATOR.load_overrides(path)
        # Without the desk light, the fan bulbs are the whole room: Fan Lights only.
        self.assertIn('name: "FHT - Chloe\'s Fan"', content)
        self.assertIn('friendly_name: "Chloe\'s Fan"', content)
        self.assertIn("unique_id: fht_bedroom_6_fan_lights", content)
        self.assertNotIn("All Lights", content)
        self.assertNotIn("- light.bedroom_6_desk_light", content)
        self.assertEqual(loaded, {"excluded_lights": {"light.x"}, "names": {"fht_a": "Name"}})

    def test_single_light_area_does_not_create_all_lights_group(self) -> None:
        """A single light needs no redundant area helper."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._write_registry(
                config_directory,
                "core.area_registry",
                "areas",
                [{"area_id": "closet", "name": "Closet"}],
            )
            self._write_registry(
                config_directory,
                "core.device_registry",
                "devices",
                [{"id": "closet-light", "area_id": "closet"}],
            )
            self._write_registry(
                config_directory,
                "core.entity_registry",
                "entities",
                [
                    {
                        "entity_id": "light.closet_light_1",
                        "device_id": "closet-light",
                        "platform": "hue",
                        "original_name": "Closet Light 1",
                    }
                ],
            )

            content, count = GENERATOR.render_light_groups(
                config_directory
            )

        self.assertEqual(count, 0)
        self.assertNotIn('name: "FHT - Closet All Lights"', content)
        self.assertNotIn("unique_id: fht_closet_all_lights", content)
        self.assertNotIn('name: "FHT - Closet Lights"', content)

    def test_groups_directional_coach_lights_together(self) -> None:
        """Create a shared fixture group for paired left and right lights."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._write_registry(
                config_directory,
                "core.area_registry",
                "areas",
                [{"area_id": "outside", "name": "Outside Perimeter"}],
            )
            self._write_registry(
                config_directory,
                "core.device_registry",
                "devices",
                [
                    {"id": "coach-left", "area_id": "outside"},
                    {"id": "coach-right", "area_id": "outside"},
                    {"id": "porch", "area_id": "outside"},
                ],
            )
            self._write_registry(
                config_directory,
                "core.entity_registry",
                "entities",
                [
                    {
                        "entity_id": "light.outside_perimeter_coach_light_left",
                        "device_id": "coach-left",
                        "platform": "hue",
                        "original_name": "Outside Perimeter Coach Left Light",
                    },
                    {
                        "entity_id": "light.outside_perimeter_coach_light_right",
                        "device_id": "coach-right",
                        "platform": "hue",
                        "original_name": "Outside Perimeter Coach Right Light",
                    },
                    {
                        "entity_id": "light.outside_perimeter_porch_light_1",
                        "device_id": "porch",
                        "platform": "hue",
                        "original_name": "Outside Perimeter Porch Light 1",
                    },
                ],
            )

            content, _ = GENERATOR.render_light_groups(config_directory)

        coach_group = content.split(
            'name: "FHT - Outside Perimeter Coach Lights"', 1
        )[1].split("- platform: group", 1)[0]
        self.assertIn("light.outside_perimeter_coach_light_left", coach_group)
        self.assertIn("light.outside_perimeter_coach_light_right", coach_group)

    def test_includes_integration_hidden_lights(self) -> None:
        """Keep valid Matter lights that Home Assistant hides by default."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._write_registry(
                config_directory,
                "core.area_registry",
                "areas",
                [{"area_id": "bedroom_2", "name": "Bedroom 2"}],
            )
            self._write_registry(
                config_directory,
                "core.device_registry",
                "devices",
                [{"id": "closet-light", "area_id": "bedroom_2"}],
            )
            self._write_registry(
                config_directory,
                "core.entity_registry",
                "entities",
                [
                    {
                        "entity_id": "light.bedroom_2_closet_light_1",
                        "device_id": "closet-light",
                        "platform": "matter",
                        "hidden_by": "integration",
                        "original_name": "Bedroom 2 Closet Light 1",
                    }
                ],
            )

            content, count = GENERATOR.render_light_groups(config_directory)

        self.assertEqual(count, 0)
        self.assertNotIn('name: "FHT - Bedroom 2 All Lights"', content)
        self.assertIn("light.bedroom_2_closet_light_1", content)

    def test_writes_separate_package_and_preserves_existing_yaml(self) -> None:
        """Never overwrite the installation's current generated groups."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._create_registries(config_directory)
            existing_path = (
                config_directory
                / "fht"
                / "lights"
                / "generated_light_groups.yaml"
            )
            existing_path.parent.mkdir(parents=True)
            existing_path.write_text(
                "existing: light groups\n",
                encoding="utf-8",
            )

            count, changed = GENERATOR.generate_light_groups(
                config_directory
            )
            output_path = (
                config_directory
                / "packages"
                / GENERATOR.OUTPUT_FILENAME
            )

            self.assertEqual(count, 2)
            self.assertTrue(changed)
            self.assertTrue(output_path.exists())
            self.assertEqual(
                existing_path.read_text(encoding="utf-8"),
                "existing: light groups\n",
            )

    def test_identical_generation_does_not_rewrite(self) -> None:
        """Report unchanged output on repeated startup generation."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._create_registries(config_directory)

            first_count, first_changed = (
                GENERATOR.generate_light_groups(config_directory)
            )
            second_count, second_changed = (
                GENERATOR.generate_light_groups(config_directory)
            )

        self.assertEqual(first_count, second_count)
        self.assertTrue(first_changed)
        self.assertFalse(second_changed)


    def test_renamed_light_rebuilds_named_subgroup(self) -> None:
        """Use a current friendly name when its entity ID stays unchanged."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._create_registries(config_directory)
            device_registry_path = (
                config_directory / ".storage" / "core.device_registry"
            )
            device_payload = json.loads(
                device_registry_path.read_text(encoding="utf-8")
            )
            device_payload["data"]["devices"].append({
                "id": "device-shower",
                "area_id": "bathroom_1",
                "name_by_user": "Bathroom 1 Shower Light",
                "name": "Smart Bulb",
            })
            device_registry_path.write_text(
                json.dumps(device_payload),
                encoding="utf-8",
            )
            registry_path = (
                config_directory / ".storage" / "core.entity_registry"
            )
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            payload["data"]["entities"].append({
                "entity_id": "light.bathroom_1_light_3",
                "device_id": "device-shower",
                "platform": "hue",
                "name": None,
                "original_name": None,
            })
            registry_path.write_text(json.dumps(payload), encoding="utf-8")
            content, _ = GENERATOR.render_light_groups(config_directory)
            payload["data"]["entities"].append({
                "entity_id": "light.bathroom_1_shower_light_2",
                "device_id": "device-shower",
                "platform": "hue",
                "name": "Bathroom 1 Shower Light 2",
            })
            registry_path.write_text(json.dumps(payload), encoding="utf-8")
            multiple_content, _ = GENERATOR.render_light_groups(config_directory)

        # One renamed shower light is offered as itself, not as a group.
        self.assertNotIn("Shower Light", content.split("light:\n", 1)[1])
        self.assertIn("# fht_replaced_group: light.fht_bathroom_1_shower_lights -> light.bathroom_1_light_3\n", content)
        self.assertIn('name: "FHT - Bathroom 1 Shower Lights"', multiple_content)
        self.assertIn('unique_id: fht_bathroom_1_shower_lights', multiple_content)
        shower_group = multiple_content.split(
            'name: "FHT - Bathroom 1 Shower Lights"',
            1,
        )[1].split("\n\n", 1)[0]
        self.assertIn("- light.bathroom_1_light_3", shower_group)

    def test_removes_fixture_group_when_it_matches_area_all_lights(self) -> None:
        """Name the only group Fan Lights when every light is a fan bulb."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self._write_registry(
                config_directory,
                "core.area_registry",
                "areas",
                [{"area_id": "bedroom_1", "name": "Bedroom 1"}],
            )
            self._write_registry(
                config_directory,
                "core.device_registry",
                "devices",
                [
                    {
                        "id": "fan-1",
                        "area_id": "bedroom_1",
                        "name_by_user": "Bedroom 1 Fan Light 1",
                    },
                    {
                        "id": "fan-2",
                        "area_id": "bedroom_1",
                        "name_by_user": "Bedroom 1 Fan Light 2",
                    },
                ],
            )
            self._write_registry(
                config_directory,
                "core.entity_registry",
                "entities",
                [
                    {
                        "entity_id": "light.bedroom_1_fan_light_1",
                        "device_id": "fan-1",
                        "platform": "matter",
                    },
                    {
                        "entity_id": "light.bedroom_1_fan_light_2",
                        "device_id": "fan-2",
                        "platform": "matter",
                    },
                ],
            )

            content, count = GENERATOR.render_light_groups(config_directory)

        self.assertEqual(count, 1)
        self.assertIn('name: "FHT - Bedroom 1 Fan Lights"', content)
        self.assertNotIn('name: "FHT - Bedroom 1 All Lights"', content)


if __name__ == "__main__":
    unittest.main()
