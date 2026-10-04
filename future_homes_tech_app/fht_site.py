#!/usr/bin/env python3
"""Site profile: the values that differ from one Future Homes Tech home to the next.

``site_profile.json`` beside this file holds the shipped defaults. Another home
changes any of them in ``/data/site_profile.json``; keys it leaves out keep
their defaults. Each process reads the profile once when it starts, so a change
takes effect after the App restarts. docs/SITE_PROFILE.md describes every key.

Run as ``future-homes-tech-site`` it answers run.sh and the Terminal:
``show``, ``get <key>``, ``protect-webhook <name>`` and ``check``.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULTS_PATH = Path(__file__).with_name("site_profile.json")
OVERRIDE_FILENAME = "site_profile.json"
PROTECT_WEBHOOK_PATH = "alarm-manager/webhook"
_MISSING = object()


class SiteProfileError(Exception):
    """The shipped site profile is unusable; the App cannot start without it."""


def default_override_path() -> Path:
    """Return the per-installation override file (FHT_SITE_PROFILE_PATH wins)."""
    explicit = os.environ.get("FHT_SITE_PROFILE_PATH", "").strip()
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("FHT_DATA_DIR", "/data")) / OVERRIDE_FILENAME


def _text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be text.")
    return value.strip()


def _word_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{key} must be a list of words.")
    words: list[str] = []
    for item in value:
        word = " ".join(item.split()).casefold()
        if word not in words:
            words.append(word)
    return words


def _entity_list(domain: str) -> Callable[[Any, str], list[str]]:
    def validate(value: Any, key: str) -> list[str]:
        words = _word_list(value, key)
        if not all(re.fullmatch(rf"{domain}\.[a-z0-9_]+", word) for word in words):
            raise ValueError(f"{key} must list {domain}.* entity IDs.")
        return words

    return validate


def _entity_id(domain: str) -> Callable[[Any, str], str]:
    def validate(value: Any, key: str) -> str:
        text = _text(value, key).casefold()
        if not re.fullmatch(rf"{domain}\.[a-z0-9_]+", text):
            raise ValueError(f"{key} must be a {domain}.* entity ID.")
        return text

    return validate


def _credential_free(parsed: Any, text: str) -> bool:
    return bool(
        parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
        and not any(character.isspace() for character in text)
    )


def _protect_base_url(value: Any, key: str) -> str:
    text = _text(value, key).rstrip("/")
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not _credential_free(parsed, text)
        or parsed.query
        or not parsed.path.endswith("/integration/v1")
    ):
        raise ValueError(
            f"{key} must be the console's HTTPS Protect integration address, "
            "ending in /integration/v1, with no sign-in details."
        )
    return text


def _webhook(value: Any, key: str) -> str:
    text = _text(value, key)
    if "://" in text:
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not _credential_free(parsed, text):
            raise ValueError(
                f"{key} must be an alarm name or a credential-free HTTP(S) address."
            )
        return text
    if re.search(r"[/?#]", text):
        raise ValueError(
            f"{key} must be an alarm name without / ? or #, or a full address."
        )
    return text


def _timezone(value: Any, key: str) -> str:
    text = _text(value, key)
    try:
        ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError, OSError) as err:
        raise ValueError(
            f"{key} is not a known time zone name such as America/Phoenix."
        ) from err
    return text


def _pattern(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text (empty turns it off).")
    try:
        re.compile(value)
    except re.error as err:
        raise ValueError(f"{key} is not a valid regular expression.") from err
    return value


# Every setting the profile may hold, with the check its value must pass.
SCHEMA: dict[str, Callable[[Any, str], Any]] = {
    "protect.base_url": _protect_base_url,
    "protect.webhooks.device_offline": _webhook,
    "protect.webhooks.armed_siren": _webhook,
    "protect.webhooks.device_alarm": _webhook,
    "timezone": _timezone,
    "weather_entity": _entity_id("weather"),
    "rooms.hidden_areas": _word_list,
    "rooms.device_alarm_room_names": _word_list,
    "rooms.sleep_source_excluded_words": _word_list,
    "doors.exterior_area_words": _word_list,
    "doors.exterior_door_name_words": _word_list,
    "catalog.retired_unavailable_lights": _entity_list("light"),
    "catalog.indicator_light_pattern": _pattern,
}
BRANCHES = {key.rsplit(".", 1)[0] for key in SCHEMA if "." in key}


def _nested_get(data: dict[str, Any], key: str, default: Any = None) -> Any:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _nested_set(data: dict[str, Any], key: str, value: Any) -> None:
    node = data
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _flatten(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Return (dotted key, value) pairs, descending only into known branches."""
    items: list[tuple[str, Any]] = []
    for name, value in data.items():
        key = f"{prefix}{name}"
        if isinstance(value, dict) and key in BRANCHES:
            items.extend(_flatten(value, f"{key}."))
        else:
            items.append((key, value))
    return items


def _read_json(path: Path) -> tuple[Any, str]:
    """Return (data, problem); the problem never repeats file content."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except json.JSONDecodeError as err:
        return None, f"{path} is not valid JSON ({err.msg} at line {err.lineno})."
    except (OSError, UnicodeDecodeError):
        return None, f"{path} could not be read."


class SiteProfile:
    """The merged, checked profile plus where each value came from."""

    def __init__(
        self,
        values: dict[str, Any],
        defaults_path: Path,
        override_path: Path,
        override_present: bool,
        overridden_keys: list[str],
        problems: list[str],
    ) -> None:
        self.values = values
        self.defaults_path = defaults_path
        self.override_path = override_path
        self.override_present = override_present
        self.overridden_keys = tuple(overridden_keys)
        self.problems = tuple(problems)

    def get(self, key: str, default: Any = None) -> Any:
        """Return a copy of one value by dotted key, such as ``rooms.hidden_areas``."""
        return copy.deepcopy(_nested_get(self.values, key, default))

    @property
    def timezone(self) -> str:
        return str(self.values["timezone"])

    def protect_webhook_url(self, name: str) -> str:
        """Return the full Protect Alarm Manager webhook address for one alarm."""
        webhook = _nested_get(self.values, f"protect.webhooks.{name}", _MISSING)
        if webhook is _MISSING:
            raise KeyError(name)
        if "://" in webhook:
            return str(webhook)
        base_url = str(self.values["protect"]["base_url"])
        return f"{base_url}/{PROTECT_WEBHOOK_PATH}/{quote(str(webhook), safe='%')}"

    def summary(self) -> str:
        """Return one plain-language line saying where the values came from."""
        if not self.override_present:
            return f"Built-in defaults; no {self.override_path} on this installation."
        count = len(self.overridden_keys)
        if not count:
            return f"{self.override_path} is present but changes no values."
        noun = "value" if count == 1 else "values"
        return f"{self.override_path} changes {count} {noun}: {', '.join(self.overridden_keys)}."

    def describe(self) -> dict[str, Any]:
        """Return the profile as JSON-safe data for the App interface."""
        return {
            "values": copy.deepcopy(self.values),
            "protect_webhook_urls": {
                name: self.protect_webhook_url(name)
                for name in self.values["protect"]["webhooks"]
            },
            "defaults_path": str(self.defaults_path),
            "override_path": str(self.override_path),
            "override_present": self.override_present,
            "overridden_keys": list(self.overridden_keys),
            "problems": list(self.problems),
            "summary": self.summary(),
        }


def load_site_profile(
    override_path: Path | None = None,
    defaults_path: Path = DEFAULTS_PATH,
) -> SiteProfile:
    """Merge the shipped defaults with the installation's override file.

    A missing override means the defaults apply. An override value that fails
    its check, or a key the profile does not know, is reported in ``problems``
    and ignored, so one mistake never takes the whole profile down.
    """
    defaults, problem = _read_json(defaults_path)
    if problem or not isinstance(defaults, dict):
        raise SiteProfileError(problem or f"{defaults_path} must contain a JSON object.")
    values: dict[str, Any] = {}
    for key, validator in SCHEMA.items():
        raw = _nested_get(defaults, key, _MISSING)
        if raw is _MISSING:
            raise SiteProfileError(f"{defaults_path} is missing {key}.")
        try:
            _nested_set(values, key, validator(raw, key))
        except ValueError as err:
            raise SiteProfileError(f"{defaults_path}: {err}") from err
    unknown = [key for key, _value in _flatten(defaults) if key not in SCHEMA]
    if unknown:
        raise SiteProfileError(f"{defaults_path} has unknown keys: {', '.join(unknown)}.")

    override_path = override_path or default_override_path()
    override_present = override_path.is_file()
    problems: list[str] = []
    overridden: list[str] = []
    if override_present:
        data, problem = _read_json(override_path)
        if problem:
            problems.append(f"{problem} The shipped defaults are in use.")
        elif not isinstance(data, dict):
            problems.append(
                f"{override_path} must contain a JSON object. The shipped defaults are in use."
            )
        else:
            for key, raw in _flatten(data):
                validator = SCHEMA.get(key)
                if validator is None:
                    problems.append(f"{key} is not a site profile setting; it was ignored.")
                    continue
                try:
                    cleaned = validator(raw, key)
                except ValueError as err:
                    problems.append(f"{err} The shipped default is in use.")
                    continue
                if cleaned != _nested_get(values, key):
                    overridden.append(key)
                _nested_set(values, key, cleaned)
    return SiteProfile(
        values, defaults_path, override_path, override_present, overridden, problems
    )


def main(argv: list[str] | None = None) -> int:
    """Print profile values for run.sh and the Terminal."""
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "show"
    try:
        profile = load_site_profile()
    except SiteProfileError as err:
        print(f"Site profile failed: {err}", file=sys.stderr, flush=True)
        return 1
    if command == "show" and len(args) == 1:
        print(json.dumps(profile.describe(), indent=2, sort_keys=True), flush=True)
        return 0
    if command == "get" and len(args) == 2:
        value = profile.get(args[1], _MISSING)
        if value is _MISSING:
            print(f"Unknown site profile key: {args[1]}", file=sys.stderr, flush=True)
            return 1
        print(value if isinstance(value, str) else json.dumps(value), flush=True)
        return 0
    if command == "protect-webhook" and len(args) == 2:
        try:
            print(profile.protect_webhook_url(args[1]), flush=True)
        except KeyError:
            print(f"Unknown Protect webhook: {args[1]}", file=sys.stderr, flush=True)
            return 1
        return 0
    if command == "check" and len(args) == 1:
        print(profile.summary(), flush=True)
        for problem in profile.problems:
            print(f"WARNING {problem}", flush=True)
        return 1 if profile.problems else 0
    print(
        "Usage: future-homes-tech-site [show | get <key> | protect-webhook <name> | check]",
        file=sys.stderr,
        flush=True,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
