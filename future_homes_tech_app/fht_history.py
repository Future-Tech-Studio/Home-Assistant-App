"""Keep recent versions of the App's saved settings so one change can be undone.

Every settings file under /data is written through ``atomic_write_text`` in
server.py, which hands the content being replaced to ``SettingsHistory.record``.
That version lands in ``/data/history/<store file name>/<UTC timestamp>.json``
and the newest twenty per store are kept. An empty version file means the
store did not exist before that write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import threading
from typing import Any, Callable, Iterable
import json

HISTORY_DIRECTORY_NAME = "history"
HISTORY_LIMIT = 20
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
TIMESTAMP_PATTERN = re.compile(r"\d{8}T\d{12}Z(?:-\d+)?")
SUMMARY_ITEM_LIMIT = 4
# Rewritten by the App on every start, so it is not a setting a person changed.
UNTRACKED_FILES = frozenset({"cleanup_pending.json"})
# The Revert card also lists what the App deleted on its own.
CLEANUP_PAGE = "cleanup"
CLEANUP_PAGE_LABEL = "App"
CLEANUP_LABEL = "Removed automatically"

# The settings files each page can undo. Three pages share the switch controls
# store because doors, switches and buttons all save their actions into it.
# Light Automations are edited on Room Configurator's Schedule card, so their
# file belongs there; the retired Schedule page keeps it until it is removed.
PAGE_STORES: dict[str, tuple[str, ...]] = {
    "doors": ("switch_control_settings.json",),
    "switches": ("switch_control_settings.json",),
    "buttons": ("switch_control_settings.json",),
    "presence": (
        "presence_light_group_assignments.json",
        "presence_light_group_timings.json",
        "presence_mode_settings.json",
    ),
    "room-config": ("room_modes.json", "room_scenes.json", "light_schedules.json", "room_mode_schedules.json"),
    "alarm": ("fridge_alarm_settings.json", "door_open_alert_settings.json"),
    "rooms": ("room_aliases.json",),
    "schedule": ("light_schedules.json",),
    "portal": ("future_tech_portal_settings.json",),
    "homekit": (
        "homekit_light_groups.json",
        "homekit_climate_entities.json",
        "homekit_security_entities.json",
    ),
}

# Where a change is made from. The switch controls store is shared by three pages.
PAGE_LABELS = {
    "switches": "Switches, Doors and Buttons",
    "presence": "Presence",
    "room-config": "Room Configurator",
    "alarm": "Alarm",
    "rooms": "Home Configurator",
    "schedule": "Schedule",
    "portal": "Portal Configurator",
    "homekit": "Apple HomeKit",
}
STORE_PAGE = {
    store: page
    for page, stores in PAGE_STORES.items()
    for store in stores
    if page not in {"doors", "buttons", "schedule"}
}

STORE_LABELS = {
    "switch_control_settings.json": "Switch, door and button actions",
    "presence_light_group_assignments.json": "Presence lights",
    "presence_light_group_timings.json": "Presence delays",
    "presence_mode_settings.json": "Presence mode settings",
    "room_modes.json": "Room modes",
    "room_mode_schedules.json": "Room mode schedules",
    "light_schedules.json": "Light automations",
    "room_scenes.json": "Room scenes",
    "fridge_alarm_settings.json": "Device alarms",
    "door_open_alert_settings.json": "Door Left Open reminders",
    "room_aliases.json": "Room names",
    "future_tech_portal_settings.json": "Portal reporting",
    "homekit_light_groups.json": "HomeKit lights",
    "homekit_climate_entities.json": "HomeKit climate",
    "homekit_security_entities.json": "HomeKit security",
}


def history_directory(store_path: Path) -> Path:
    """Return the folder that holds the saved versions of one store."""
    return store_path.parent / HISTORY_DIRECTORY_NAME / store_path.name


def page_stores(page: str) -> tuple[str, ...]:
    """Return the store file names one settings page owns."""
    stores = PAGE_STORES.get(page)
    if not stores:
        raise ValueError("Choose a settings page with a change history.")
    return stores


def describe_change(before: Any, after: Any) -> str:
    """Say what changed between two versions in one short line."""
    lines = change_lines(before, after)
    if not lines:
        return ""
    text = "; ".join(lines[:SUMMARY_ITEM_LIMIT])
    remaining = len(lines) - SUMMARY_ITEM_LIMIT
    if remaining > 0:
        text += f" and {remaining} more"
    return text


def change_lines(before: Any, after: Any) -> list[str]:
    """Describe each setting that differs, with its old and new value.

    For example "Kitchen › Delay changed from 5 to 9 minutes",
    "Porch Evening automation turned on" or "Added Bedroom 6".
    """
    if before is None or after is None:
        return [] if before == after else ["Changed settings"]
    return [_describe(*change) for change in _changes(before, after, [])]


# Keys that only group other settings; they add nothing to a change's name.
_CONTAINER_KEYS = frozenset({
    "settings", "schedules", "rooms", "groups", "assignments", "timings", "entries",
    "items", "data", "config", "options", "values", "mode_settings", "action_settings",
    "action_assignments", "mode_assignments",
})
_UNIT_SUFFIXES = (
    ("_minutes", "minutes"), ("_seconds", "seconds"), ("_ms", "ms"),
    ("_pct", "%"), ("_percent", "%"),
)
_ON_OFF_KEYS = frozenset({"enabled", "enable", "active", "on"})
_MAX_DEPTH = 6


def _changes(before: Any, after: Any, path: list[str]) -> list[tuple[str, list[str], Any, Any]]:
    """List (kind, path, old, new) for every leaf that differs."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict) and len(path) < _MAX_DEPTH:
        changes = []
        for key in sorted(set(before) | set(after), key=str):
            name = str(key)
            if key not in before:
                changes.append(("added", [*path, name], None, after[key]))
            elif key not in after:
                changes.append(("removed", [*path, name], before[key], None))
            else:
                changes.extend(_changes(before[key], after[key], [*path, name]))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        if all(_is_scalar(item) for item in [*before, *after]):
            changes = [("added_item", path, None, item) for item in after if item not in before]
            changes.extend(("removed_item", path, item, None) for item in before if item not in after)
            if changes:
                return changes
        return [("changed", path, before, after)]
    return [("changed", path, before, after)]


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _describe(kind: str, path: list[str], old: Any, new: Any) -> str:
    unit = ""
    leaf = path[-1] if path else ""
    for suffix, suffix_unit in _UNIT_SUFFIXES:
        if leaf.endswith(suffix):
            unit = suffix_unit
            break
    name = _path_name(path)
    if kind == "added_item":
        return f"Added {_value(new)} to {name}" if name else f"Added {_value(new)}"
    if kind == "removed_item":
        return f"Removed {_value(old)} from {name}" if name else f"Removed {_value(old)}"
    if kind == "added":
        if _is_scalar(new) and not isinstance(new, bool) and new not in ("", None):
            return f"{name} set to {_value(new, unit)}"
        if isinstance(new, bool) and leaf in _ON_OFF_KEYS:
            return f"{_path_name(path[:-1]) or name} turned {'on' if new else 'off'}"
        return f"Added {name}"
    if kind == "removed":
        return f"Removed {name}"
    if isinstance(old, bool) and isinstance(new, bool):
        if leaf in _ON_OFF_KEYS:
            owner = _path_name(path[:-1])
            return f"{owner} turned {'on' if new else 'off'}" if owner else f"Turned {'on' if new else 'off'}"
        return f"{name} turned {'on' if new else 'off'}"
    if _is_scalar(old) and _is_scalar(new):
        if old in ("", None):
            return f"{name or 'Setting'} set to {_value(new, unit)}"
        if new in ("", None):
            return f"{name or 'Setting'} cleared (was {_value(old, unit)})"
        old_text = _value(old, unit) if unit == "%" else _value(old)
        return f"{name or 'Setting'} changed from {old_text} to {_value(new, unit)}"
    return f"Changed {name}" if name else "Changed settings"


def _path_name(path: list[str]) -> str:
    parts = [part for part in path if part not in _CONTAINER_KEYS]
    if not parts and path:
        parts = path[-1:]
    return " › ".join(_words(part) for part in parts)


def _words(key: str) -> str:
    """Turn a stored key into words: light.fht_kitchen_lights → Kitchen Lights."""
    text = key
    if re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", text):
        text = text.split(".", 1)[1]
        if text.startswith("fht_"):
            text = text[4:]
        return " ".join(word.capitalize() for word in text.split("_") if word)
    for suffix, _unit in _UNIT_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    if "_" in text or text.islower():
        words = [word for word in text.replace("-", "_").split("_") if word]
        text = " ".join(words)
        return text[:1].upper() + text[1:]
    return text


def _value(value: Any, unit: str = "") -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str):
        text = _words(value) if re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", value) else value
    else:
        text = str(value)
    if not unit:
        return text
    return f"{text}{unit}" if unit == "%" else f"{text} {unit}"


def cleanup_entries(directory: Path, limit: int = HISTORY_LIMIT) -> list[dict[str, Any]]:
    """Describe the App's automatic deletions, newest first.

    They are listed for information only: ``revertible`` is false, because
    the App recreates an item itself whenever a setting needs it again.
    """
    entries = []
    for path in sorted(directory.glob("*.json"), reverse=True)[:limit]:
        if not TIMESTAMP_PATTERN.fullmatch(path.stem):
            continue
        removed = _parse_json(path.read_text(encoding="utf-8"))
        items = removed.get("entries") if isinstance(removed, dict) else None
        if not isinstance(items, list):
            continue
        names = [
            str(item.get("name") or item.get("original_name") or item.get("entity_id"))
            for item in items if isinstance(item, dict) and item.get("entity_id")
        ]
        if not names:
            continue
        summary = ", ".join(names[:SUMMARY_ITEM_LIMIT])
        if len(names) > SUMMARY_ITEM_LIMIT:
            summary += f" and {len(names) - SUMMARY_ITEM_LIMIT} more"
        saved_at = datetime.strptime(path.stem.split("-")[0], TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
        entries.append({
            "timestamp": path.stem,
            "saved_at": saved_at.isoformat(),
            "store": "",
            "page": CLEANUP_PAGE,
            "page_label": CLEANUP_PAGE_LABEL,
            "label": CLEANUP_LABEL,
            "summary": summary,
            "changes": names,
            "revertible": False,
        })
    return entries


def _parse_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


class SettingsHistory:
    """Record and restore saved versions of the settings files in /data."""

    def __init__(
        self,
        directories: Iterable[Path] = (Path("/data"),),
        limit: int = HISTORY_LIMIT,
    ) -> None:
        self._directories = {Path(directory) for directory in directories}
        self._limit = max(1, limit)
        self._lock = threading.Lock()

    def track(self, directory: Path) -> None:
        """Keep versions of the JSON files saved directly in this folder."""
        self._directories.add(Path(directory))

    def untrack(self, directory: Path) -> None:
        self._directories.discard(Path(directory))

    def tracks(self, path: Path) -> bool:
        """Return whether one file is a settings store with a history."""
        return (
            path.suffix == ".json"
            and path.name not in UNTRACKED_FILES
            and path.parent in self._directories
        )

    def record(self, path: Path, previous: str | None) -> Path | None:
        """Keep the content a settings write is about to replace."""
        if not self.tracks(path):
            return None
        directory = history_directory(path)
        with self._lock:
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)
            version = directory / f"{stamp}.json"
            counter = 1
            while version.exists():
                version = directory / f"{stamp}-{counter}.json"
                counter += 1
            version.write_text(previous or "", encoding="utf-8")
            for obsolete in self._versions(directory)[self._limit:]:
                obsolete.unlink(missing_ok=True)
        return version

    @staticmethod
    def _versions(directory: Path) -> list[Path]:
        """Return the saved versions of one store, newest first."""
        return sorted(
            (
                candidate
                for candidate in directory.glob("*.json")
                if candidate.is_file() and TIMESTAMP_PATTERN.fullmatch(candidate.stem)
            ),
            key=lambda candidate: candidate.stem,
            reverse=True,
        )

    def entries(self, store: str, store_path: Path) -> list[dict[str, Any]]:
        """Describe the saved versions of one store, newest first."""
        directory = history_directory(store_path)
        if not directory.is_dir():
            return []
        versions = self._versions(directory)
        if not versions:
            return []
        try:
            newer_text: str | None = store_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            newer_text = None
        newer = _parse_json(newer_text)
        entries = []
        for version in versions:
            text = version.read_text(encoding="utf-8")
            current = _parse_json(text)
            saved_at = datetime.strptime(version.stem.split("-")[0], TIMESTAMP_FORMAT)
            entries.append(
                {
                    "timestamp": version.stem,
                    "saved_at": saved_at.replace(tzinfo=timezone.utc).isoformat(),
                    "store": store,
                    "label": STORE_LABELS.get(store, store),
                    "summary": describe_change(current, newer),
                    "changes": change_lines(current, newer),
                }
            )
            newer = current
        return entries

    def page_entries(self, page: str, store_paths: dict[str, Path]) -> list[dict[str, Any]]:
        """List the recent versions of every store one page owns, newest first."""
        entries = []
        for store in page_stores(page):
            path = store_paths.get(store)
            if path is not None:
                entries.extend(self.entries(store, path))
        entries.sort(key=lambda entry: entry["timestamp"], reverse=True)
        return entries[: self._limit]

    def all_entries(self, store_paths: dict[str, Path]) -> list[dict[str, Any]]:
        """List the recent versions of every settings store, newest first."""
        entries = []
        for store, page in STORE_PAGE.items():
            path = store_paths.get(store)
            if path is None:
                continue
            for entry in self.entries(store, path):
                entries.append({**entry, "page": page, "page_label": PAGE_LABELS.get(page, page)})
        entries.sort(key=lambda entry: entry["timestamp"], reverse=True)
        return entries[: self._limit]

    def page_store_path(self, page: str, store: str, store_paths: dict[str, Path]) -> Path:
        """Return the store path one page may restore, or explain why not."""
        if store not in page_stores(page) or store not in store_paths:
            raise ValueError("That settings file does not belong to this page.")
        return store_paths[store]

    def restore(
        self,
        store_path: Path,
        timestamp: str,
        write_text: Callable[[Path, str], bool],
    ) -> bool:
        """Put one store back to a saved version; return whether it changed.

        ``write_text`` is the App's atomic writer, so the content being
        replaced is itself kept and the undo can be undone.
        """
        if not TIMESTAMP_PATTERN.fullmatch(timestamp):
            raise ValueError("Choose a saved version to restore.")
        version = history_directory(store_path) / f"{timestamp}.json"
        if not version.is_file():
            raise ValueError("That saved version is no longer available.")
        content = version.read_text(encoding="utf-8")
        if content:
            return write_text(store_path, content)
        # The store did not exist before that change, so undoing removes it.
        try:
            previous = store_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        self.record(store_path, previous)
        store_path.unlink()
        return True
