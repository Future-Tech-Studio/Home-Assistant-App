"""Find and remove App helpers that nothing defines or uses any more."""

import json
import os
from pathlib import Path
import re
import threading


HELPERS = {"input_select", "input_text", "input_boolean", "input_number", "input_datetime", "automation", "script"}


class MaintenanceError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class Maintenance:
    def __init__(self, inventory, commands, config_directory, data_directory):
        self.inventory = inventory
        self.commands = commands
        self.config = Path(config_directory).resolve()
        self.data = Path(data_directory)
        self.write_lock = threading.Lock()
    def _inputs(self):
        registry, states = self.commands([{"type": "config/entity_registry/list"}, {"type": "get_states"}])
        if not isinstance(registry, list) or not isinstance(states, list):
            raise MaintenanceError("A complete live inventory is required. Nothing was changed.", 503)
        return registry, {item["entity_id"]: item for item in states if isinstance(item, dict) and item.get("entity_id")}

    def _references(self):
        paths = set()
        for root, directories, filenames in os.walk(self.config, followlinks=False):
            directories[:] = [name for name in directories if not name.startswith(".") and name not in {"custom_components", "www", "tts", "backups", "deps", "node_modules", "esphome", "zigbee2mqtt"}]
            linked = next((name for name in directories if (Path(root) / name).is_symlink()), None)
            if linked:
                raise MaintenanceError(f"Linked configuration directory {self._label(Path(root) / linked)} requires manual review.", 409)
            paths.update(Path(root) / name for name in filenames if Path(name).suffix in {".yaml", ".yml"})
        paths |= set((self.config / "packages").rglob("*.json"))
        paths |= set((self.config / ".storage").glob("lovelace*")) | set((self.config / ".storage").glob("input_*"))
        entries = self.config / ".storage/core.config_entries"
        if entries.is_file():
            paths.add(entries)
        paths |= set(self.data.parent.glob("*.json"))
        scanned_paths = set()
        explicit_paths = set()
        pending = sorted(paths)
        texts = []
        while pending:
            path = pending.pop(0)
            if path.resolve() in scanned_paths:
                continue
            if path not in explicit_paths and any(part.startswith(".") and part != ".storage" for part in path.relative_to(self.config if path.is_relative_to(self.config) else self.data.parent).parts):
                continue
            if path.name in {"entity_inventory.json"} or path.name.endswith(".bak"):
                if path in explicit_paths:
                    raise MaintenanceError(f"Included configuration source {self._label(path)} requires manual review. Nothing was changed.", 409)
                continue
            try:
                if path.is_symlink() or path.stat().st_size > 10 * 1024 * 1024:
                    raise MaintenanceError(f"Configuration source {self._label(path)} cannot be safely scanned. Review it manually.", 409)
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as err:
                raise MaintenanceError(f"Configuration source {self._label(path)} could not be read ({err.__class__.__name__}). Nothing was changed.", 409) from err
            scanned_paths.add(path.resolve())
            # Commented-out lines include nothing, so drop comments first.
            active = "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())
            for target in re.findall(r"!include\w*\s+([^\s#]+)", active):
                raw_target = path.parent / target.strip("\"'")
                if raw_target.is_symlink() or any(parent.is_symlink() for parent in raw_target.parents if parent.is_relative_to(self.config)):
                    raise MaintenanceError(f"Linked configuration source {target} in {self._label(path)} requires manual review.", 409)
                target_path = raw_target.resolve()
                if not target_path.is_relative_to(self.config.resolve()):
                    raise MaintenanceError(f"{self._label(path)} includes {target}, outside the configuration folder. Nothing was changed.", 409)
                if not target_path.exists():
                    continue  # A missing include cannot define or reference anything.
                # Like Home Assistant's !include_dir_*: files only, skipping
                # hidden files and folders (such as packages/.fht-backups).
                included_paths = {
                    item for item in target_path.rglob("*")
                    if item.suffix in {".yaml", ".yml"} and item.is_file()
                    and not any(part.startswith(".") for part in item.relative_to(target_path).parts)
                } if target_path.is_dir() else {target_path}
                for included in sorted(included_paths):
                    if included.is_symlink() or not included.resolve().is_relative_to(self.config.resolve()):
                        raise MaintenanceError(f"{self._label(path)} includes {self._label(included)}, which is linked or outside the configuration folder. Nothing was changed.", 409)
                    if included.resolve() not in scanned_paths:
                        explicit_paths.add(included)
                        pending.append(included)
            if path.suffix == ".json" or path.parent.name == ".storage":
                try:
                    json.loads(text)
                except ValueError as err:
                    raise MaintenanceError(f"Configuration source {self._label(path)} is not valid JSON. Nothing was changed.", 409) from err
            texts.append((str(path.relative_to(self.config if path.is_relative_to(self.config) else self.data.parent)), text))
        if not (self.config / "configuration.yaml").is_file():
            raise MaintenanceError("Home Assistant configuration is not mounted. Review is unavailable.", 503)
        return texts

    def _label(self, path):
        path = Path(path)
        for base in (self.config, self.data.parent):
            if path.is_relative_to(base):
                return str(path.relative_to(base))
        return path.name

    def find_unused_helpers(self):
        """Return registry entries of App helpers that nothing defines or uses.

        An App helper has an fht_ entity ID, a verifiable unique ID and no
        device or integration. It is unused when Home Assistant restores it as
        unavailable (no configuration provides it) and no scanned source
        mentions it. Helpers an earlier Safe Cleanup archived (disabled and
        hidden) count too. Any source that cannot be read safely raises
        MaintenanceError, so nothing is removed on a partial scan.
        """
        registry, states = self._inputs()
        archived = self._archived()
        candidates = []
        for entry in registry:
            if not isinstance(entry, dict):
                continue
            entity_id = str(entry.get("entity_id") or "")
            domain, _, suffix = entity_id.partition(".")
            unique_id = str(entry.get("unique_id") or "")
            if domain not in HELPERS or not suffix.startswith("fht_") or len(unique_id) < 6:
                continue
            if entry.get("device_id") or entry.get("config_entry_id"):
                continue
            state = states.get(entity_id)
            restored = (
                state is not None and state.get("state") == "unavailable"
                and (state.get("attributes") or {}).get("restored") is True
                and not entry.get("disabled_by") and not entry.get("hidden_by")
            )
            was_archived = (
                archived.get(entity_id) == unique_id
                and entry.get("disabled_by") == "user" and entry.get("hidden_by") == "user"
            )
            if restored or was_archived:
                candidates.append(entry)
        if not candidates:
            return []
        texts = [text for _, text in self._references()]
        return [
            entry for entry in candidates
            if not any(entry["entity_id"] in text or entry["unique_id"] in text for text in texts)
        ]

    def _archived(self):
        """Entity ID → unique ID of helpers an earlier Safe Cleanup archived."""
        archived = {}
        for path in sorted(self.data.glob("*.json")):
            try:
                archive = read_json(path)
            except (OSError, ValueError):
                continue
            if not isinstance(archive, dict) or archive.get("status") != "archived":
                continue
            for record in archive.get("records") or []:
                if isinstance(record, dict) and record.get("entity_id") and record.get("unique_id"):
                    archived[str(record["entity_id"])] = str(record["unique_id"])
        return archived

    def remove_unused_helpers(self, journal):
        """Delete unused App helpers; ``journal`` keeps their entries first."""
        with self.write_lock:
            unused = self.find_unused_helpers()
            if not unused:
                return []
            journal(unused)
            self.commands([
                {"type": "config/entity_registry/remove", "entity_id": entry["entity_id"]}
                for entry in unused
            ])
            return [str(entry["entity_id"]) for entry in unused]
