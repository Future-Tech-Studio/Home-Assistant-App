#!/usr/bin/env python3
"""Move saved App settings from a local install to a repository install.

Home Assistant gives every App install its own private ``/data``. A local
install exports its saved settings into the shared Home Assistant
configuration directory on each start; a new install with no saved settings
imports them once on its first start and then deletes the transfer file.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import time

DEFAULT_DATA_DIR = Path("/data")
DEFAULT_TRANSFER_PATH = Path(
    "/homeassistant/.future_homes_tech_transfer/app-data.tar.gz"
)
OPTIONS_MEMBER = "transfer/options.json"
DATA_PREFIX = "data/"
IMPORTED_MARKER = ".transfer_imported"
# Supervisor owns options.json; Beta builds are re-downloaded when needed.
EXCLUDED = {"options.json", "beta", IMPORTED_MARKER}


class TransferError(RuntimeError):
    """Raised when saved settings cannot be exported or imported."""


def _saved_entries(data_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        return []
    return sorted(
        entry for entry in data_dir.iterdir() if entry.name not in EXCLUDED
    )


def export_settings(
    options: dict,
    data_dir: Path = DEFAULT_DATA_DIR,
    transfer_path: Path = DEFAULT_TRANSFER_PATH,
) -> int:
    """Write saved settings and App options to the transfer file."""
    entries = _saved_entries(data_dir)
    transfer_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    transfer_path.parent.chmod(0o700)
    temporary = transfer_path.with_name(f".{transfer_path.name}.{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle, tarfile.open(
            fileobj=handle, mode="w:gz"
        ) as bundle:
            content = json.dumps(options, indent=2).encode("utf-8")
            info = tarfile.TarInfo(OPTIONS_MEMBER)
            info.size = len(content)
            info.mtime = int(time.time())
            info.mode = 0o600
            bundle.addfile(info, io.BytesIO(content))
            for entry in entries:
                bundle.add(entry, arcname=DATA_PREFIX + entry.name)
        temporary.replace(transfer_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return len(entries)


def import_settings(
    data_dir: Path = DEFAULT_DATA_DIR,
    transfer_path: Path = DEFAULT_TRANSFER_PATH,
) -> dict | None:
    """Import saved settings into an empty install.

    Returns the exported App options, or None when nothing was imported.
    """
    if not transfer_path.is_file():
        return None
    if (data_dir / IMPORTED_MARKER).exists() or _saved_entries(data_dir):
        return None
    staging = data_dir / f".transfer-staging-{os.getpid()}"
    options = None
    try:
        staging.mkdir(parents=True)
        with tarfile.open(transfer_path, mode="r:gz") as bundle:
            for member in bundle.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise TransferError(f"Unsafe path in transfer file: {member.name}")
                if member.name == OPTIONS_MEMBER and member.isfile():
                    source = bundle.extractfile(member)
                    options = json.loads(source.read().decode("utf-8")) if source else None
                    continue
                if not member.name.startswith(DATA_PREFIX):
                    continue
                relative = PurePosixPath(member.name[len(DATA_PREFIX):])
                if not relative.parts or relative.parts[0] in EXCLUDED:
                    continue
                target = staging.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(member)
                    if source is None:
                        continue
                    with source, target.open("wb") as handle:
                        shutil.copyfileobj(source, handle)
                    target.chmod(member.mode & 0o777 or 0o600)
        for entry in staging.iterdir():
            entry.replace(data_dir / entry.name)
    except (OSError, tarfile.TarError, ValueError) as err:
        raise TransferError(f"Unable to import saved settings: {err}") from err
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    (data_dir / IMPORTED_MARKER).write_text(
        json.dumps({"imported_at": int(time.time())}) + "\n", encoding="utf-8"
    )
    transfer_path.unlink()
    try:
        transfer_path.parent.rmdir()
    except OSError:
        pass
    return options if isinstance(options, dict) else {}


def main(argv: list[str]) -> int:
    """Run ``export`` (options JSON on stdin) or ``import``.

    ``import`` prints the exported options JSON and exits 0 after importing,
    or exits 3 when there was nothing to import.
    """
    data_dir = Path(os.environ.get("FHT_DATA_DIR", DEFAULT_DATA_DIR))
    transfer_path = Path(os.environ.get("FHT_TRANSFER_PATH", DEFAULT_TRANSFER_PATH))
    command = argv[1] if len(argv) == 2 else ""
    try:
        if command == "export":
            options = json.loads(sys.stdin.read() or "{}")
            print(export_settings(options, data_dir, transfer_path))
            return 0
        if command == "import":
            options = import_settings(data_dir, transfer_path)
            if options is None:
                return 3
            print(json.dumps(options))
            return 0
    except (TransferError, OSError, ValueError) as err:
        print(str(err), file=sys.stderr)
        return 1
    print("usage: future-homes-tech-transfer export|import", file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
