#!/usr/bin/env python3
"""Create an immutable candidate bundle without advancing STABLE.json."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = ROOT / "future_homes_tech_app"
STABLE_POINTER = ROOT / "stable_releases" / "STABLE.json"
CANDIDATE_ROOT = ROOT / "candidate_releases"
SOURCE_MEMBERS = (
    ".gitignore",
    "README.md",
    "custom_components",
    "design",
    "docs",
    "future_homes_tech_app",
    "repository.yaml",
    "scripts",
    "tests",
)
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ARCHIVE_EXCLUDED_FILES = {
    "design/background-options/infinite-vertical-warp.png",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def include_archive_member(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    parts = Path(info.name).parts
    relative_name = Path(info.name).as_posix().removeprefix("./")
    if any(
        part in {".git", "__pycache__", ".pytest_cache", ".ruff_cache"}
        or part.startswith("._")
        or part == ".DS_Store"
        for part in parts
    ) or relative_name in ARCHIVE_EXCLUDED_FILES:
        return None
    return info


def file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and not path.name.startswith("._")
        and path.name != ".DS_Store"
    }


def tree_digest(files: dict[str, str]) -> str:
    payload = "".join(f"{name}\0{digest}\n" for name, digest in files.items())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def configured_version() -> str:
    config = (APP_SOURCE / "config.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([^\s]+)", config, re.MULTILINE)
    if not match:
        raise ValueError("config.yaml has no version")
    return match.group(1)


def assert_client_version(version: str) -> None:
    html = (APP_SOURCE / "web/index.html").read_text(encoding="utf-8")
    for expected in (
        f'<div class="brand-version">V {version}</div>',
        f'const CLIENT_VERSION = "{version}"',
    ):
        if expected not in html:
            raise ValueError(f"browser version is not synchronized: {expected}")


def create_source_archive(path: Path) -> None:
    with tarfile.open(path, "w:gz", compresslevel=9) as archive:
        for relative in SOURCE_MEMBERS:
            member = ROOT / relative
            if member.exists():
                archive.add(
                    member,
                    arcname=f"./{relative}",
                    recursive=True,
                    filter=include_archive_member,
                )


def create_mounted_archive(path: Path, mounted_root: Path) -> None:
    with tarfile.open(path, "w:gz", compresslevel=9) as archive:
        archive.add(
            mounted_root,
            arcname=".",
            recursive=True,
            filter=include_archive_member,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--local-only", action="store_true", help="Package local source explicitly as not mounted or installed.")
    parser.add_argument(
        "--mounted-root",
        type=Path,
        default=Path("/Volumes/addons/future_homes_tech_app"),
    )
    args = parser.parse_args()
    version = args.version.strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise SystemExit("Version must use the form 0.0.0.")
    if configured_version() != version:
        raise SystemExit("Requested version does not match config.yaml.")
    assert_client_version(version)

    stable: dict[str, Any] = json.loads(STABLE_POINTER.read_text(encoding="utf-8"))
    stable_version = str(stable.get("stable_version") or "")
    retired_version = str(stable.get("archived_stable_version") or "")
    if not stable_version and not (retired_version and stable.get("status") == "stable-hold-retired-by-user"):
        raise SystemExit("STABLE.json has no stable version.")
    if version == stable_version:
        raise SystemExit("A candidate version must not overwrite the stable version.")

    mounted_root = APP_SOURCE.resolve() if args.local_only else args.mounted_root.resolve()
    if not mounted_root.is_dir():
        raise SystemExit(f"Mounted add-on source is unavailable: {mounted_root}")
    source_files = file_hashes(APP_SOURCE)
    mounted_files = file_hashes(mounted_root)
    if source_files != mounted_files:
        missing = sorted(set(source_files) - set(mounted_files))
        extra = sorted(set(mounted_files) - set(source_files))
        changed = sorted(
            name
            for name in set(source_files) & set(mounted_files)
            if source_files[name] != mounted_files[name]
        )
        raise SystemExit(
            "Mounted source does not match the candidate: "
            f"missing={missing[:5]} extra={extra[:5]} changed={changed[:5]}"
        )

    candidate_directory = CANDIDATE_ROOT / version
    if candidate_directory.exists():
        raise SystemExit(f"Candidate already exists: {candidate_directory}")
    candidate_directory.mkdir(parents=True)

    source_archive = candidate_directory / f"future-homes-tech-app-source-{version}.tar.gz"
    archive_kind = "local-runtime" if args.local_only else "mounted"
    mounted_archive = candidate_directory / f"future_homes_tech_app-{archive_kind}-{version}.tar.gz"
    create_source_archive(source_archive)
    create_mounted_archive(mounted_archive, mounted_root)

    manifest = {
        "candidate_version": version,
        "status": "candidate-awaiting-user-stability-approval",
        "stable_version_unchanged": stable_version,
        "retired_stable_archive_version": retired_version,
        "promote_only_on_explicit_user_approval": True,
        "release_gate": "scripts/release_gate.sh",
        "source_tree_sha256": tree_digest(source_files),
        "mounted_tree_sha256": tree_digest(mounted_files),
        "source_archive": source_archive.name,
        "source_archive_sha256": sha256(source_archive),
        "mounted_archive": mounted_archive.name,
        "mounted_archive_sha256": sha256(mounted_archive),
    }
    if args.local_only:
        manifest["status"] = "local-candidate-not-mounted-or-installed"
        for key in ("tree_sha256", "archive", "archive_sha256"):
            manifest[f"local_runtime_{key}"] = manifest.pop(f"mounted_{key}")
    (candidate_directory / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (candidate_directory / "README.md").write_text(
        f"# Candidate release {version}\n\n" +
        ("This local candidate is not mounted, published or installed. Run `scripts/release_gate.sh` before installation. " if args.local_only else
         "This candidate passed `scripts/release_gate.sh` and exactly matched the mounted add-on source when packaged. ")
        + (f"Stable remains `{stable_version}`.\n\n" if stable_version else
           f"The `{retired_version}` stable hold is retired; its recovery archives remain intact.\n\n") +
        "Do not update `stable_releases/STABLE.json` until the homeowner explicitly "
        "declares this candidate stable after Home Assistant runtime testing.\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
