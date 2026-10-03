import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from test_server import SERVER


class ExhaustTimerTests(unittest.TestCase):
    def test_storage_validation_and_disable(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.SwitchControlSettings(Path(directory) / "controls.json")
            settings.save_exhaust_timer("switch.toilet", 5)
            self.assertEqual(settings.read()["exhaust_timers"], {"switch.toilet": 5})
            for value in [-1, 121, 1.5, True, "5"]:
                with self.assertRaises(ValueError):
                    settings.save_exhaust_timer("switch.toilet", value)
            settings.save_exhaust_timer("switch.toilet", 0)
            self.assertEqual(settings.read()["exhaust_timers"], {})

    def test_wired_fan_timer_and_cancel(self):
        entities = [{"entity_id": "switch.toilet", "wired_load_names": {"fan.toilet": "Toilet Exhaust Fan"}}]
        automations = SERVER.ExhaustFanTimer.render({"switch.toilet": 5, "switch.light": 10}, entities)
        self.assertEqual(len(automations), 1)
        timer = automations[0]
        self.assertEqual(timer["mode"], "restart")
        self.assertEqual(timer["triggers"][1]["to"], "off")
        self.assertEqual(timer["actions"][1], {"delay": {"minutes": 5}})
        self.assertEqual(timer["actions"][-1]["target"]["entity_id"], "switch.toilet")

    def test_package_contains_timer_without_action_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            manager.sync({}, [{"entity_id": "switch.fan", "friendly_name": "Exhaust Fan"}], exhaust_timers={"switch.fan": 5})
            self.assertIn('"minutes": 5', path.read_text())


class ExhaustHumidityTests(unittest.TestCase):
    FAN = {"entity_id": "switch.bathroom_fan", "friendly_name": "Bathroom Exhaust Fan", "area": "Bathroom"}
    SENSOR = {"entity_id": "sensor.bathroom_humidity", "friendly_name": "Bathroom Humidity", "device_class": "humidity", "area": "Bathroom", "state": "71.4"}

    def test_storage_validation_defaults_and_disable(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.SwitchControlSettings(Path(directory) / "controls.json")
            settings.save_exhaust_humidity("switch.bathroom_fan", "sensor.bathroom_humidity", None, None)
            self.assertEqual(settings.read()["exhaust_humidity"], {"switch.bathroom_fan": {"sensor": "sensor.bathroom_humidity", "start_above": 65, "stop_below": 55}})
            settings.save_exhaust_humidity("switch.bathroom_fan", "sensor.bathroom_humidity", 70, 60)
            self.assertEqual(settings.read()["exhaust_humidity"]["switch.bathroom_fan"], {"sensor": "sensor.bathroom_humidity", "start_above": 70, "stop_below": 60})
            for sensor, start, stop in [("sensor.x", 49, 45), ("sensor.x", 91, 45), ("sensor.x", 65, 39), ("sensor.x", 65, 81), ("sensor.x", 60, 60), ("sensor.x", 60, 65),
                                        ("sensor.x", 65.0, 55), ("sensor.x", True, 55), ("sensor.x", "65", 55), ("binary_sensor.x", 65, 55)]:
                with self.assertRaises(ValueError):
                    settings.save_exhaust_humidity("switch.bathroom_fan", sensor, start, stop)
            with self.assertRaises(ValueError):
                settings.save_exhaust_humidity("light.bathroom", "sensor.x", 65, 55)
            self.assertEqual(settings.read()["exhaust_humidity"]["switch.bathroom_fan"]["start_above"], 70)
            settings.save_exhaust_humidity("switch.bathroom_fan", "", 70, 60)
            self.assertEqual(settings.read()["exhaust_humidity"], {})

    def test_normalization_drops_malformed_saved_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controls.json"
            path.write_text(json.dumps({"exhaust_humidity": {
                "switch.good": {"sensor": "sensor.h", "start_above": 65, "stop_below": 55},
                "switch.defaults_missing": {"sensor": "sensor.h"},
                "switch.swapped": {"sensor": "sensor.h", "start_above": 55, "stop_below": 65},
                "switch.float": {"sensor": "sensor.h", "start_above": 65.5, "stop_below": 55},
                "switch.no_sensor": {"start_above": 65, "stop_below": 55},
                "switch.string": "sensor.h",
                "light.wrong_domain": {"sensor": "sensor.h", "start_above": 65, "stop_below": 55},
            }}))
            self.assertEqual(SERVER.SwitchControlSettings(path).read()["exhaust_humidity"], {
                "switch.good": {"sensor": "sensor.h", "start_above": 65, "stop_below": 55},
                "switch.defaults_missing": {"sensor": "sensor.h", "start_above": 65, "stop_below": 55},
            })
            path.write_text(json.dumps({"exhaust_humidity": ["switch.good"]}))
            self.assertEqual(SERVER.SwitchControlSettings(path).read()["exhaust_humidity"], {})

    def test_room_sensor_catalog(self):
        entities = [
            self.SENSOR,
            {"entity_id": "sensor.bathroom_moisture", "friendly_name": "Bathroom Air Humidity", "unit_of_measurement": "%", "area": "Bathroom", "state": "60"},
            {"entity_id": "sensor.bathroom_battery", "friendly_name": "Bathroom Sensor Battery", "unit_of_measurement": "%", "area": "Bathroom", "state": "80"},
            {"entity_id": "sensor.hall_humidity", "friendly_name": "Hall Humidity", "device_class": "humidity", "area": "Hall", "state": "50"},
            {"entity_id": "binary_sensor.bathroom_humidity_alert", "friendly_name": "Bathroom Humidity Alert", "device_class": "humidity", "area": "Bathroom"},
            {"entity_id": "sensor.aliased", "friendly_name": "Spa Humidity", "device_class": "humidity", "area": "Mum's Bathroom", "original_area": "Bathroom", "state": "unavailable"},
        ]
        sensors = SERVER.ExhaustFanHumidity.sensors(entities, "Bathroom")
        self.assertEqual([sensor["entity_id"] for sensor in sensors], ["sensor.bathroom_moisture", "sensor.bathroom_humidity", "sensor.aliased"])
        self.assertEqual(sensors[1], {"entity_id": "sensor.bathroom_humidity", "friendly_name": "Bathroom Humidity", "state": "71.4", "room": "Bathroom"})
        self.assertEqual(SERVER.ExhaustFanHumidity.sensors(entities, "Hall")[0]["friendly_name"], "Hall Humidity")
        self.assertEqual(SERVER.ExhaustFanHumidity.sensors(entities, ""), [])
        self.assertEqual([sensor["room"] for sensor in SERVER.ExhaustFanHumidity.sensors(entities)], ["Bathroom", "Bathroom", "Bathroom", "Hall"])

    def test_humidity_automation_rises_on_and_falls_off(self):
        settings = {"switch.bathroom_fan": {"sensor": "sensor.bathroom_humidity", "start_above": 65, "stop_below": 55},
                    "switch.lamp": {"sensor": "sensor.bathroom_humidity", "start_above": 65, "stop_below": 55}}
        automations = SERVER.ExhaustFanHumidity.render(settings, [self.FAN, {"entity_id": "switch.lamp", "friendly_name": "Lamp"}])
        self.assertEqual(len(automations), 1)
        automation = automations[0]
        self.assertRegex(automation["id"], r"^fht_exhaust_humidity_[0-9a-f]{16}$")
        self.assertEqual(automation["alias"], "FHT - Exhaust Fan Humidity switch.bathroom_fan")
        self.assertEqual(automation["mode"], "restart")
        rise, start, fall = automation["triggers"]
        self.assertEqual(rise, {"trigger": "numeric_state", "entity_id": "sensor.bathroom_humidity", "above": 65, "id": "humid"})
        self.assertEqual(start, {"trigger": "homeassistant", "event": "start", "id": "start"})
        self.assertEqual(fall, {"trigger": "numeric_state", "entity_id": "sensor.bathroom_humidity", "below": 55, "for": {"minutes": 2}, "id": "dry"})
        dry, humid = automation["actions"][0]["choose"]
        self.assertEqual(dry["conditions"], [{"condition": "trigger", "id": "dry"}])
        self.assertEqual(dry["sequence"], [{"action": "switch.turn_off", "target": {"entity_id": "switch.bathroom_fan"}}])
        self.assertEqual(humid["conditions"], [{"condition": "numeric_state", "entity_id": "sensor.bathroom_humidity", "above": 65}])
        self.assertEqual(humid["sequence"], [{"action": "switch.turn_on", "target": {"entity_id": "switch.bathroom_fan"}}])

    def test_manual_timer_only_changes_for_fans_with_a_sensor(self):
        entities = [self.FAN, {"entity_id": "switch.toilet_fan", "friendly_name": "Toilet Exhaust Fan"}]
        timers = {"switch.bathroom_fan": 20, "switch.toilet_fan": 10}
        humidity = {"switch.bathroom_fan": {"sensor": "sensor.bathroom_humidity", "start_above": 65, "stop_below": 55}}
        plain = SERVER.ExhaustFanTimer.render(timers, entities)
        mixed = SERVER.ExhaustFanTimer.render(timers, entities, humidity)
        self.assertEqual(mixed[1], plain[1], "A fan without a sensor keeps its timer exactly as before")
        self.assertEqual(plain[0]["actions"], [
            {"condition": "state", "entity_id": "switch.bathroom_fan", "state": "on"},
            {"delay": {"minutes": 20}},
            {"condition": "state", "entity_id": "switch.bathroom_fan", "state": "on"},
            {"action": "switch.turn_off", "target": {"entity_id": "switch.bathroom_fan"}},
        ])
        self.assertEqual(mixed[0]["id"], plain[0]["id"])
        self.assertEqual(mixed[0]["triggers"], plain[0]["triggers"])
        actions = mixed[0]["actions"]
        self.assertEqual(len(actions), 6)
        self.assertEqual(actions[1], {"condition": "template", "value_template": "{{ trigger.to_state is not defined or trigger.to_state.context.parent_id is none }}"})
        self.assertEqual(actions[2], {"delay": {"minutes": 20}})
        self.assertEqual(actions[4], {"condition": "template", "value_template": "{{ states('sensor.bathroom_humidity') | float(0) < 55 }}"})
        self.assertEqual(actions[5]["action"], "switch.turn_off")

    def test_package_contains_humidity_automation_and_guarded_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            humidity = {"switch.bathroom_fan": {"sensor": "sensor.bathroom_humidity", "start_above": 65, "stop_below": 55}}
            manager.sync({}, [self.FAN], exhaust_timers={"switch.bathroom_fan": 20}, exhaust_humidity=humidity)
            lines = [line for line in path.read_text().splitlines() if line.startswith("  - {")]
            automations = [json.loads(line[4:]) for line in lines]
            self.assertEqual([item["alias"] for item in automations], ["FHT - Exhaust Fan Timer switch.bathroom_fan", "FHT - Exhaust Fan Humidity switch.bathroom_fan"])
            self.assertIn("parent_id is none", lines[0])
            self.assertEqual(automations[1]["triggers"][2]["for"], {"minutes": 2})
            manager.sync({}, [self.FAN], exhaust_timers={"switch.bathroom_fan": 20})
            self.assertNotIn("fht_exhaust_humidity_", path.read_text())
            self.assertNotIn("parent_id", path.read_text())
            manager.sync({}, [self.FAN], exhaust_humidity=humidity)
            content = path.read_text()
            self.assertIn("fht_exhaust_humidity_", content)
            self.assertNotIn("fht_exhaust_timer_", content)

    def route_handler(self, directory, entities, payload):
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = "/api/switch-light-groups"
        handler._read_json_object = Mock(return_value=payload)
        handler.inventory = Mock()
        handler.inventory.fetch.return_value = {"entities": entities}
        handler.switch_control_settings = SERVER.SwitchControlSettings(Path(directory) / "controls.json")
        handler.switch_assignments = Mock()
        handler.switch_assignments.read.return_value = {}
        handler.button_inventory = Mock()
        handler.button_inventory.fetch.return_value = []
        handler.control_automations = Mock()
        handler.control_automations.sync.return_value = []
        handler.registry_organizer = Mock()
        handler._send_json = Mock()
        return handler

    def test_route_saves_same_room_sensor_and_syncs_package(self):
        entities = [
            {**self.FAN, "original_area": "Bathroom", "area": "Mum's Bathroom"},
            {**self.SENSOR, "original_area": "Bathroom", "area": "Mum's Bathroom"},
            {"entity_id": "sensor.hall_humidity", "device_class": "humidity", "original_area": "Hall", "area": "Hall"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            handler = self.route_handler(directory, entities, {"setting": "exhaust_humidity", "assignment_id": "switch.bathroom_fan", "sensor": "sensor.bathroom_humidity", "start_above": 70, "stop_below": 60})
            handler._dispatch_POST()
            status, body = handler._send_json.call_args.args
            self.assertEqual(status, 200, body)
            self.assertEqual(body["exhaust_humidity"], {"switch.bathroom_fan": {"sensor": "sensor.bathroom_humidity", "start_above": 70, "stop_below": 60}})
            self.assertEqual(handler.control_automations.sync.call_args.kwargs["exhaust_humidity"], body["exhaust_humidity"])
            self.assertEqual(handler.inventory.fetch.call_args.kwargs.get("include_all"), True)

            handler = self.route_handler(directory, entities, {"setting": "exhaust_humidity", "assignment_id": "switch.bathroom_fan", "sensor": "sensor.hall_humidity"})
            handler._dispatch_POST()
            status, body = handler._send_json.call_args.args
            self.assertEqual(status, 400)
            self.assertIn("same room", body["error"])
            handler.control_automations.sync.assert_not_called()

            handler = self.route_handler(directory, entities, {"setting": "exhaust_humidity", "assignment_id": "switch.bathroom_fan", "sensor": "sensor.bathroom_humidity", "start_above": 60, "stop_below": 60})
            handler._dispatch_POST()
            self.assertEqual(handler._send_json.call_args.args[0], 400)
            self.assertEqual(handler.switch_control_settings.read()["exhaust_humidity"]["switch.bathroom_fan"]["start_above"], 70)

            handler = self.route_handler(directory, entities, {"setting": "exhaust_humidity", "assignment_id": "switch.bathroom_fan", "sensor": ""})
            handler._dispatch_POST()
            status, body = handler._send_json.call_args.args
            self.assertEqual(status, 200, body)
            self.assertEqual(body["exhaust_humidity"], {})

            handler = self.route_handler(directory, entities, {"setting": "exhaust_humidity", "assignment_id": "sensor.bathroom_humidity", "sensor": "sensor.bathroom_humidity"})
            handler._dispatch_POST()
            self.assertEqual(handler._send_json.call_args.args[0], 400)
