#!/usr/bin/env python3
"""Write or check future_homes_tech_app/RELEASE.json for Beta updates.

The manifest lists every App file with its SHA-256 so the Beta updater can
download only changed files and verify each one. It also records what the
build needs from the installed Stable App: configuration options and Alpine
packages, which a Beta update cannot add.

Usage: build_release_manifest.py [--check]
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "future_homes_tech_app"
MANIFEST = APP / "RELEASE.json"
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def app_files() -> list[Path]:
    return sorted(
        path for path in APP.rglob("*")
        if path.is_file()
        and path != MANIFEST
        and not EXCLUDED_PARTS & set(path.relative_to(APP).parts)
        and not path.name.startswith(".")
    )


def schema_options(config: str) -> tuple[list[str], list[str]]:
    """Return (required, optional) option names from config.yaml's schema."""
    required, optional = [], []
    block = re.search(r"^schema:\n((?:  .*\n?)*)", config, re.MULTILINE)
    for line in (block.group(1) if block else "").splitlines():
        match = re.match(r"^  ([a-z0-9_]+):\s*(.*)$", line)
        if not match:
            continue
        name, kind = match.groups()
        (optional if kind.strip().strip("\"'").endswith("?") else required).append(name)
    return sorted(required), sorted(optional)


def apk_packages(dockerfile: str) -> list[str]:
    packages: set[str] = set()
    for match in re.finditer(r"^RUN apk add (?:--no-cache )?(.+)$", dockerfile, re.MULTILINE):
        packages.update(token for token in match.group(1).split() if not token.startswith("-"))
    return sorted(packages)


def build() -> dict:
    config = (APP / "config.yaml").read_text(encoding="utf-8")
    version = re.search(r"^version:\s*(\S+)", config, re.MULTILINE).group(1)
    required, optional = schema_options(config)
    files = {}
    for path in app_files():
        data = path.read_bytes()
        files[path.relative_to(APP).as_posix()] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
    return {
        "version": version,
        "requires": {
            "options": required,
            "optional_options": optional,
            "apk_packages": apk_packages((APP / "Dockerfile").read_text(encoding="utf-8")),
        },
        "files": files,
    }


def render(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    content = render(build())
    if argv[1:] == ["--check"]:
        current = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
        if current != content:
            print("RELEASE.json is out of date. Run scripts/build_release_manifest.py.", file=sys.stderr)
            return 1
        return 0
    MANIFEST.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
