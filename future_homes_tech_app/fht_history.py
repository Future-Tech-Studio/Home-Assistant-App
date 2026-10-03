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
SUMMARY_ITEM_LIMIT = 3
# Rewritten by the App on every start, so it is not a setting a person changed.
UNTRACKED_FILES = frozenset({"cleanup_pending.json"})

# The settings files each page can undo. Three pages share the switch controls
# store because doors, switches and buttons all save their actions into it.
PAGE_STORES: dict[str, tuple[str, ...]] = {
    "doors": ("switch_control_settings.json",),
    "switches": ("switch_control_settings.json",),
    "buttons": ("switch_control_settings.json",),
    "presence": (
        "presence_light_group_assignments.json",
        "presence_light_group_timings.json",
        "presence_mode_settings.json",
    ),
    "room-modes": ("room_modes.json",),
    "scenes": ("light_schedules.json", "room_scenes.json"),
    "alarm": ("alarm_door_settings.json", "fridge_alarm_settings.json"),
    "rooms": ("room_aliases.json",),
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
    "room-modes": "Room Modes",
    "scenes": "Scenes",
    "alarm": "Alarm",
    "rooms": "Home Configurator",
    "homekit": "Apple HomeKit",
}
STORE_PAGE = {
    store: page
    for page, stores in PAGE_STORES.items()
    for store in stores
    if page not in {"doors", "buttons"}
}

STORE_LABELS = {
    "switch_control_settings.json": "Switch, door and button actions",
    "presence_light_group_assignments.json": "Presence lights",
    "presence_light_group_timings.json": "Presence delays",
    "presence_mode_settings.json": "Presence mode settings",
    "room_modes.json": "Room modes",
    "light_schedules.json": "Light automations",
    "room_scenes.json": "Room scenes",
    "alarm_door_settings.json": "Alarm door sensors",
    "fridge_alarm_settings.json": "Device alarms",
    "room_aliases.json": "Room names",
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
    """Name the settings that differ between two versions, in a short line."""
    changes = _changed_entries(before, after, depth=2)
    if not changes:
        return ""
    text = ", ".join(f"{verb} {name}" for verb, name in changes[:SUMMARY_ITEM_LIMIT])
    remaining = len(changes) - SUMMARY_ITEM_LIMIT
    if remaining > 0:
        text += f" and {remaining} more"
    return text


def _changed_entries(before: Any, after: Any, depth: int) -> list[tuple[str, str]]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[tuple[str, str]] = []
        for key in sorted(set(before) | set(after), key=str):
            name = str(key)
            if key not in before:
                changes.append(("Added", name))
            elif key not in after:
                changes.append(("Removed", name))
            elif before[key] != after[key]:
                nested = _changed_entries(before[key], after[key], depth - 1) if depth > 1 else []
                if nested and len(nested) <= SUMMARY_ITEM_LIMIT:
                    changes.extend((verb, f"{name} › {inner}") for verb, inner in nested)
                else:
                    changes.append(("Changed", name))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        changes = [("Added", str(item)) for item in after if item not in before]
        changes.extend(("Removed", str(item)) for item in before if item not in after)
        return changes
    return [] if before == after else [("Changed", "settings")]


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
