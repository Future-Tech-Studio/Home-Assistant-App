import copy
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace

from access_preview import create_preview, SERVER


def main():
    with tempfile.TemporaryDirectory(prefix="fht-maintenance-preview-") as directory:
        root = Path(directory)
        config = root / "config"
        config.mkdir()
        (config / "configuration.yaml").write_text("default_config:\n")
        registry = [{"entity_id": "input_select.fht_retired", "unique_id": "fht_retired_helper", "platform": "input_select", "disabled_by": None, "hidden_by": None}, {"entity_id": "automation.pantry", "unique_id": "pantry_automation"}]
        states = [{"entity_id": "input_select.fht_retired", "state": "unavailable", "attributes": {"restored": True, "friendly_name": "Retired Pantry Helper"}}]

        def commands(items):
            results = []
            for item in items:
                if item["type"] == "config/entity_registry/list":
                    results.append(copy.deepcopy(registry))
                elif item["type"] == "get_states":
                    results.append(copy.deepcopy(states))
                elif item["type"] == "config/entity_registry/update":
                    entry = next(entry for entry in registry if entry["entity_id"] == item["entity_id"])
                    entry.update({key: item[key] for key in ("disabled_by", "hidden_by")})
                    results.append(copy.deepcopy(entry))
                elif item["type"] == "trace/list":
                    results.append([{"run_id": "fixture", "state": "stopped", "script_execution": "finished", "timestamp": {"start": "2026-09-14T01:00:00Z"}}])
                else:
                    raise ValueError("Physical device operations are forbidden in this fixture")
            return results

        inventory = SimpleNamespace(peek=lambda **kwargs: {"entities": [
            {"entity_id": "sensor.bedroom_battery", "state": "8", "device_id": "button", "device_name": "Chloe's Bedroom Button", "friendly_name": "Button battery", "device_class": "battery", "area": "Chloe's Bedroom"},
            {"entity_id": "light.pantry", "state": "unavailable", "device_id": "bulb", "device_name": "Pantry Light 1", "area": "Pantry", "last_changed": "2026-09-14T01:00:00Z"},
        ], "stale": False, "live_connected": True})
        service = SERVER.MAINTENANCE.Maintenance(inventory, commands, config, root / "data/maintenance")
        server = create_preview(directory)
        server.RequestHandlerClass.maintenance = service
        retired = [{"entity_id": "light.fht_old_group", "unique_id": "fht_old_group", "platform": "group", "original_name": "Old Pantry Group"}]
        server.RequestHandlerClass.retired_approvals = SERVER.RetiredEntityApprovals(root / "data")
        server.RequestHandlerClass.inventory = SimpleNamespace(fetch=lambda **kwargs: {"entities": []})
        server.RequestHandlerClass.registry_organizer = SimpleNamespace(
            find_retired_managed_entities=lambda entities, config: copy.deepcopy(retired),
            cleanup_retired_managed_entities=lambda entities, config, approved: [
                retired.pop(0)["entity_id"] for _ in list(retired) if retired[0]["entity_id"] in approved],
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run([os.environ["FHT_NODE_BINARY"], str(Path(__file__).with_name("maintenance_browser.cjs"))], env={**os.environ, "FHT_MAINTENANCE_PREVIEW_URL": f"http://127.0.0.1:{server.server_address[1]}/"}, timeout=180)
            return result.returncode
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    raise SystemExit(main())
