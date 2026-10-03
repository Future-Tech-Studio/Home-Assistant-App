"""Private, bounded diagnostics and reversible retirement of unused helpers."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading


ENTITY_ID = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
HELPERS = {"input_select", "input_text", "input_boolean", "input_number", "input_datetime", "automation", "script"}


class MaintenanceError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Maintenance:
    def __init__(self, inventory, commands, config_directory, data_directory):
        self.inventory = inventory
        self.commands = commands
        self.config = Path(config_directory).resolve()
        self.data = Path(data_directory)
        self.lock = threading.RLock()
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

    def review(self):
        registry, states = self._inputs()
        texts = self._references()
        candidates = []
        groups = {}
        for entity_id, state in states.items():
            attributes = state.get("attributes") or {}
            members = attributes.get("entity_id")
            if entity_id.startswith("light.") and isinstance(members, list) and members:
                group_key = tuple(sorted(set(member for member in members if isinstance(member, str))))
                if group_key:
                    groups.setdefault(group_key, []).append({"id": entity_id, "name": str(attributes.get("friendly_name") or entity_id)[:180]})
        for entry in registry:
            entity_id = str(entry.get("entity_id") or "")
            domain, _, suffix = entity_id.partition(".")
            state = states.get(entity_id, {})
            attributes = state.get("attributes") or {}
            if domain not in HELPERS or not suffix.startswith("fht_") or attributes.get("restored") is not True:
                continue
            reasons = []
            if entry.get("device_id") or entry.get("config_entry_id"):
                reasons.append("Linked to a device or integration")
            if state.get("state") != "unavailable":
                reasons.append("Not an unavailable restored helper")
            if entry.get("disabled_by") or entry.get("hidden_by"):
                reasons.append("Already disabled or hidden; retain current policy")
            unique_id = str(entry.get("unique_id") or "")
            if len(unique_id) < 6:
                reasons.append("Ownership identity cannot be verified")
            references = sorted({source for source, text in texts if entity_id in text or (unique_id and unique_id in text)})
            if references:
                reasons.append("Referenced or defined in current configuration")
            candidates.append({"id": entity_id, "name": str(attributes.get("friendly_name") or entity_id)[:180], "eligible": not reasons, "reasons": reasons, "references": references})
        leftovers = self._leftovers(registry, states)
        revision = digest({"registry": registry, "sources": texts, "candidates": candidates})
        return {"items": sorted(candidates, key=lambda item: (not item["eligible"], item["name"].casefold())), "duplicates": [{"groups": group, "members": list(members)} for members, group in groups.items() if len(group) > 1], "leftovers": leftovers, "revision": revision, "registry_revision": digest(registry), "limitations": "External systems and dynamically constructed references need installer review. Duplicate groups are suggestions only; this tool never merges active groups or deletes entity IDs."}

    @staticmethod
    def _leftovers(registry, states):
        """List registry entities nothing provides anymore that the App did not make.

        Read-only: the installer deletes them in Home Assistant after review.
        """
        leftovers = []
        for entry in registry:
            if not isinstance(entry, dict):
                continue
            entity_id = str(entry.get("entity_id") or "")
            unique_id = str(entry.get("unique_id") or "")
            object_id = entity_id.partition(".")[2]
            if not entity_id or entry.get("disabled_by"):
                continue
            if object_id.startswith("fht_") or unique_id.startswith("fht_") or (
                entry.get("platform") == "group" and unique_id == object_id
            ):
                continue  # Made by the App; its own start-up cleanup handles these.
            state = states.get(entity_id)
            if state is not None and (state.get("attributes") or {}).get("restored") is not True:
                continue
            attributes = (state or {}).get("attributes") or {}
            leftovers.append({
                "id": entity_id,
                "name": str(entry.get("name") or entry.get("original_name") or attributes.get("friendly_name") or entity_id)[:180],
                "integration": str(entry.get("platform") or "unknown"),
                "device_linked": bool(entry.get("device_id")),
            })
        return sorted(leftovers, key=lambda item: (item["integration"], item["id"]))

    def _save_archive(self, archive):
        self.data.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.data, 0o700)
        path = self.data / (archive["id"] + ".json")
        temporary = self.data / (archive["id"] + ".tmp")
        with open(temporary, "w", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, 0o600)) as handle:
            json.dump(archive, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

    def archives(self):
        items = []
        for path in sorted(self.data.glob("*.json"), reverse=True)[:100]:
            archive = read_json(path)
            items.append({key: archive.get(key) for key in ("id", "created_at", "status", "entities", "restored_at")})
        return {"items": items[:100]}

    def archive(self, payload, actor):
        identifiers = payload.get("entities")
        if payload.get("confirmed") is not True or payload.get("external_reviewed") is not True:
            raise MaintenanceError("Confirm the exact selection and external-reference review.")
        if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 10 or any(not isinstance(value, str) or not ENTITY_ID.fullmatch(value) for value in identifiers) or len(set(identifiers)) != len(identifiers):
            raise MaintenanceError("Select between one and ten distinct helpers.")
        with self.write_lock:
            review = self.review()
            if payload.get("revision") != review["revision"]:
                raise MaintenanceError("Configuration changed. Review the fresh plan before archiving.", 409)
            eligible = {item["id"] for item in review["items"] if item["eligible"]}
            if not set(identifiers) <= eligible:
                raise MaintenanceError("One or more items are active, referenced, or protected.", 409)
            registry, states = self._inputs()
            if digest(registry) != review["registry_revision"]:
                raise MaintenanceError("Registry changed during review. Nothing was changed.", 409)
            entries = {entry["entity_id"]: entry for entry in registry}
            archive = {"id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(8), "created_at": stamp(), "actor": str(actor.get("id") or ""), "status": "prepared", "entities": identifiers, "records": [{key: entries[entity_id].get(key) for key in ("entity_id", "unique_id", "platform", "disabled_by", "hidden_by")} for entity_id in identifiers], "applied": []}
            if any((states.get(entity_id, {}).get("attributes") or {}).get("restored") is not True or states.get(entity_id, {}).get("state") != "unavailable" or any(entries[entity_id].get(key) for key in ("device_id", "config_entry_id", "disabled_by", "hidden_by")) for entity_id in identifiers):
                raise MaintenanceError("An entity is now active. Nothing was changed.", 409)
            self._save_archive(archive)
            try:
                for entity_id in identifiers:
                    self.commands([{"type": "config/entity_registry/update", "entity_id": entity_id, "disabled_by": "user", "hidden_by": "user"}])
                    archive["applied"].append(entity_id)
                    self._save_archive(archive)
                verified, _ = self._inputs()
                verified = {entry["entity_id"]: entry for entry in verified}
                if any(verified.get(entity_id, {}).get("disabled_by") != "user" or verified.get(entity_id, {}).get("hidden_by") != "user" for entity_id in identifiers):
                    raise MaintenanceError("Registry did not confirm the archive.", 503)
                archive["status"] = "archived"
            except Exception as err:
                archive["status"] = "partial-review-required"
                self._save_archive(archive)
                raise MaintenanceError("Archiving stopped. Open Recovery to inspect or restore this batch; do not retry blindly.", 503) from err
            self._save_archive(archive)
            return {"archive_id": archive["id"], "count": len(identifiers)}

    def restore(self, payload):
        identifier = str(payload.get("archive_id") or "")
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[a-f0-9]{16}", identifier) or payload.get("confirmed") is not True:
            raise MaintenanceError("Confirm a valid recovery batch.")
        with self.write_lock:
            path = self.data / (identifier + ".json")
            if not path.is_file():
                raise MaintenanceError("Recovery batch not found.", 404)
            archive = read_json(path)
            if archive["status"] == "restored":
                return {"count": 0, "already_restored": True}
            registry, _ = self._inputs()
            entries = {entry["entity_id"]: entry for entry in registry}
            for record in archive["records"]:
                current = entries.get(record["entity_id"])
                if not current or any(current.get(key) != record.get(key) for key in ("unique_id", "platform")) or current.get("disabled_by") not in (None, "user") or current.get("hidden_by") not in (None, "user"):
                    raise MaintenanceError("Entity identity or protection changed. Manual recovery is required.", 409)
            try:
                for record in archive["records"]:
                    self.commands([{"type": "config/entity_registry/update", "entity_id": record["entity_id"], "disabled_by": record["disabled_by"], "hidden_by": record["hidden_by"]}])
                verified, _ = self._inputs()
                verified = {entry["entity_id"]: entry for entry in verified}
                if any(any(verified.get(record["entity_id"], {}).get(key) != record[key] for key in ("disabled_by", "hidden_by")) for record in archive["records"]):
                    raise MaintenanceError("Registry did not confirm recovery.", 503)
            except Exception as err:
                archive["status"] = "partial-restore-review-required"
                self._save_archive(archive)
                raise MaintenanceError("Recovery stopped. Inspect this batch before retrying.", 503) from err
            archive.update(status="restored", restored_at=stamp())
            self._save_archive(archive)
            return {"count": len(archive["records"])}
