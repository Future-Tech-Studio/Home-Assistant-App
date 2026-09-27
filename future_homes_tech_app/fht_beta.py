#!/usr/bin/env python3
"""Install and activate Beta channel builds for the Future Homes Tech App.

Home Assistant builds the App from the Stable (``main``) branch. When the
``beta_mode`` option is on, this module downloads the ``beta`` branch into the
App's private ``/data`` volume and, on the next App start, copies it over the
Stable files named by the Beta ``Dockerfile`` ``COPY`` lines. Turning Beta mode
off, or installing a Stable version at least as new, starts Stable again.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BETA_ROOT = Path("/data/beta")
DEFAULT_BETA_CONFIG_URL = (
    "https://raw.githubusercontent.com/fht-ha/FHT-HA/beta/"
    "future_homes_tech_app/config.yaml"
)
DEFAULT_BETA_ARCHIVE_URL = (
    "https://codeload.github.com/fht-ha/FHT-HA/tar.gz/refs/heads/beta"
)
DEFAULT_BETA_COMMIT_URL = "https://api.github.com/repos/fht-ha/FHT-HA/commits/beta"
BETA_CONFIG_AT_COMMIT_URL = (
    "https://raw.githubusercontent.com/fht-ha/FHT-HA/{sha}/"
    "future_homes_tech_app/config.yaml"
)
BETA_ARCHIVE_AT_COMMIT_URL = "https://codeload.github.com/fht-ha/FHT-HA/tar.gz/{sha}"
DEFAULT_RESTART_URL = "http://supervisor/addons/self/restart"
APP_DIRECTORY = "future_homes_tech_app"
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024
LATEST_CACHE_TTL_SECONDS = 15
MAX_UNCONFIRMED_STARTS = 3
REQUIRED_FILES = (
    "config.yaml",
    "Dockerfile",
    "run.sh",
    "server.py",
    "web/index.html",
)
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
COPY_PATTERN = re.compile(r"^COPY\s+(\S+)\s+(\S+)\s*$")


class BetaChannelError(RuntimeError):
    """Raised when a Beta build cannot be checked or installed."""


def beta_mode_enabled() -> bool:
    """Return whether the Beta mode App option is enabled."""
    return os.environ.get("FHT_BETA_MODE", "0") == "1"


def version_key(version: str) -> tuple[int, int, int]:
    """Return a comparable key for a 0.0.0 version string."""
    if not VERSION_PATTERN.fullmatch(version or ""):
        raise ValueError(f"Invalid version: {version!r}")
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def is_newer(candidate: str, current: str) -> bool:
    """Return whether candidate is a newer valid version than current."""
    try:
        return version_key(candidate) > version_key(current)
    except ValueError:
        return False


def config_version(text: str) -> str:
    """Read the version from config.yaml text."""
    match = re.search(r"^version:\s*[\"']?([^\s\"']+)", text, re.MULTILINE)
    if not match or not VERSION_PATTERN.fullmatch(match.group(1)):
        raise BetaChannelError("Beta config.yaml has no valid version.")
    return match.group(1)


def dockerfile_copies(text: str) -> list[tuple[str, str]]:
    """Return (source, destination) pairs from simple Dockerfile COPY lines."""
    copies = []
    for line in text.splitlines():
        match = COPY_PATTERN.match(line.strip())
        if not match:
            continue
        source, destination = match.groups()
        source_path = PurePosixPath(source)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise BetaChannelError(f"Unsafe Dockerfile source: {source}")
        if not destination.startswith("/"):
            raise BetaChannelError(f"Dockerfile destination must be absolute: {destination}")
        copies.append((source, destination))
    if not copies:
        raise BetaChannelError("Beta Dockerfile has no COPY instructions.")
    return copies


class BetaChannel:
    """Check, download, and select Beta builds kept in private App storage."""

    def __init__(
        self,
        root: Path = DEFAULT_BETA_ROOT,
        stable_version: str = "",
        config_url: str = DEFAULT_BETA_CONFIG_URL,
        archive_url: str = DEFAULT_BETA_ARCHIVE_URL,
        token: str = "",
        restart_url: str = DEFAULT_RESTART_URL,
        cache_ttl: float = LATEST_CACHE_TTL_SECONDS,
        commit_url: str = "",
    ) -> None:
        self.root = Path(root)
        self.stable_version = stable_version
        self.config_url = config_url
        self.archive_url = archive_url
        self.token = token
        self.restart_url = restart_url
        self.cache_ttl = max(0.0, float(cache_ttl))
        self._lock = threading.Lock()
        self._latest: str | None = None
        self._latest_at = 0.0
        # Checking the branch's newest commit avoids GitHub's five-minute raw
        # file cache, and unchanged (304) answers do not use the rate limit.
        self.commit_url = commit_url
        self._commit_sha = ""
        self._commit_etag = ""
        self._etag_sha = ""

    @property
    def releases(self) -> Path:
        return self.root / "releases"

    @property
    def pointer(self) -> Path:
        return self.root / "current.json"

    @property
    def start_attempts_path(self) -> Path:
        return self.root / "start_attempts"

    def start_attempts(self) -> int:
        """Return Beta starts not yet confirmed by a running interface."""
        try:
            return int(self.start_attempts_path.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            return 0

    def record_start_attempt(self) -> int:
        attempts = self.start_attempts() + 1
        self.root.mkdir(parents=True, exist_ok=True)
        self.start_attempts_path.write_text(f"{attempts}\n", encoding="utf-8")
        return attempts

    def confirm_started(self) -> None:
        """Mark the running build as healthy."""
        try:
            self.start_attempts_path.unlink()
        except FileNotFoundError:
            pass

    def installed_version(self) -> str:
        """Return the selected downloaded Beta version, if it is complete."""
        try:
            data = json.loads(self.pointer.read_text(encoding="utf-8"))
            version = str(data.get("version") or "")
            version_key(version)
        except (OSError, ValueError, AttributeError):
            return ""
        release = self.releases / version
        if not all((release / name).is_file() for name in REQUIRED_FILES):
            return ""
        return version

    def active_release(self) -> Path | None:
        """Return the Beta release to run, or None to run Stable."""
        version = self.installed_version()
        if not version:
            return None
        if self.stable_version and not is_newer(version, self.stable_version):
            return None
        return self.releases / version

    def latest_version(self, force: bool = False) -> str:
        """Return the version published on the beta branch."""
        with self._lock:
            if (
                not force
                and self._latest is not None
                and time.monotonic() - self._latest_at < self.cache_ttl
            ):
                return self._latest
            sha = self._latest_commit()
            if sha and sha == self._commit_sha and self._latest is not None:
                self._latest_at = time.monotonic()
                return self._latest
            url = BETA_CONFIG_AT_COMMIT_URL.format(sha=sha) if sha else self.config_url
            text = self._download(url, 256 * 1024).decode("utf-8")
            self._latest = config_version(text)
            self._commit_sha = sha
            self._latest_at = time.monotonic()
            return self._latest

    def _latest_commit(self) -> str:
        """Return the beta branch's newest commit, or "" to use the branch URL."""
        if not self.commit_url:
            return ""
        headers = {
            "Accept": "application/vnd.github.sha",
            "User-Agent": "future-homes-tech-app",
        }
        if self._commit_etag and self._etag_sha:
            headers["If-None-Match"] = self._commit_etag
        try:
            with urlopen(Request(self.commit_url, headers=headers), timeout=15) as response:
                sha = response.read(100).decode("ascii", "replace").strip()
                etag = response.headers.get("ETag", "")
        except HTTPError as err:
            if err.code == 304 and self._etag_sha:
                return self._etag_sha
            return ""
        except (URLError, OSError):
            return ""
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return ""
        self._commit_etag = etag
        self._etag_sha = sha
        return sha

    def status(self) -> dict[str, Any]:
        """Return Beta channel details for the interface."""
        installed = self.installed_version()
        running = os.environ.get("FHT_RUNNING_VERSION", "") or self.stable_version
        payload: dict[str, Any] = {
            "beta_mode": beta_mode_enabled(),
            "beta_installed_version": installed,
            "running_version": running,
            "beta_available_version": "",
            "beta_update_available": False,
            "beta_error": None,
        }
        if not payload["beta_mode"]:
            return payload
        try:
            latest = self.latest_version()
        except BetaChannelError as err:
            payload["beta_error"] = str(err)
            return payload
        payload["beta_available_version"] = latest
        payload["beta_update_available"] = is_newer(latest, running)
        return payload

    def install_latest(self) -> str:
        """Download the beta branch, verify it, and select it for next start."""
        with self._lock:
            sha = self._latest_commit() or self._commit_sha
        archive_url = BETA_ARCHIVE_AT_COMMIT_URL.format(sha=sha) if sha else self.archive_url
        archive = self._download(archive_url, MAX_ARCHIVE_BYTES)
        self.releases.mkdir(parents=True, exist_ok=True)
        staging = self.releases / f".staging-{os.getpid()}-{time.time_ns()}"
        try:
            self._extract_app(archive, staging)
            for name in REQUIRED_FILES:
                if not (staging / name).is_file():
                    raise BetaChannelError(f"Beta build is missing {name}.")
            version = config_version((staging / "config.yaml").read_text(encoding="utf-8"))
            dockerfile_copies((staging / "Dockerfile").read_text(encoding="utf-8"))
            if self.stable_version and not is_newer(version, self.stable_version):
                raise BetaChannelError(
                    f"Beta {version} is not newer than installed Stable {self.stable_version}."
                )
            release = self.releases / version
            if release.exists():
                shutil.rmtree(release)
            staging.rename(release)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        temporary = self.pointer.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": version}) + "\n", encoding="utf-8")
        temporary.replace(self.pointer)
        self.confirm_started()
        self._prune(keep={version})
        with self._lock:
            self._latest = version
            self._latest_at = time.monotonic()
        return version

    def restart_app(self, delay: float = 1.0) -> None:
        """Ask Supervisor to restart only this App after a short delay."""
        if not self.token:
            raise BetaChannelError("Home Assistant App API access is unavailable.")

        def restart() -> None:
            time.sleep(delay)
            request = Request(
                self.restart_url,
                data=b"",
                method="POST",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            print("[Beta] Asking Home Assistant to restart the App.", flush=True)
            try:
                with urlopen(request, timeout=60):
                    pass
            except HTTPError as err:
                detail = err.read(500).decode("utf-8", "replace")
                print(f"[Beta] WARNING Home Assistant refused the App restart: {err} {detail}", flush=True)
            except (URLError, OSError) as err:
                print(f"[Beta] WARNING Unable to restart the App: {err}", flush=True)

        threading.Thread(target=restart, name="fht-beta-restart", daemon=True).start()

    def _download(self, url: str, limit: int) -> bytes:
        request = Request(url, headers={"User-Agent": "future-homes-tech-app"})
        try:
            with urlopen(request, timeout=120) as response:
                data = response.read(limit + 1)
        except (HTTPError, URLError, OSError) as err:
            raise BetaChannelError(f"Unable to reach the Beta channel: {err}") from err
        if len(data) > limit:
            raise BetaChannelError("Beta download is larger than allowed.")
        return data

    @staticmethod
    def _extract_app(archive: bytes, destination: Path) -> None:
        destination.mkdir(parents=True)
        try:
            bundle = tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz")
        except tarfile.TarError as err:
            raise BetaChannelError(f"Beta download is not a valid archive: {err}") from err
        with bundle:
            found = False
            for member in bundle.getmembers():
                parts = PurePosixPath(member.name).parts
                if len(parts) < 3 or parts[1] != APP_DIRECTORY:
                    continue
                relative = PurePosixPath(*parts[2:])
                if relative.is_absolute() or ".." in relative.parts:
                    raise BetaChannelError(f"Unsafe path in Beta archive: {member.name}")
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    continue
                with source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
                found = True
        if not found:
            raise BetaChannelError("Beta download does not contain the App.")

    def _prune(self, keep: set[str]) -> None:
        for entry in self.releases.iterdir():
            if entry.name not in keep:
                shutil.rmtree(entry, ignore_errors=True)


def apply_release(release: Path, filesystem_root: Path = Path("/")) -> list[Path]:
    """Copy a Beta release over the Stable files its Dockerfile installs."""
    copies = dockerfile_copies((release / "Dockerfile").read_text(encoding="utf-8"))
    missing = [source for source, _ in copies if not (release / source).exists()]
    if missing:
        raise BetaChannelError(f"Beta build is missing {', '.join(missing)}.")
    applied = []
    for source, destination in copies:
        source_path = release / source
        target = filesystem_root / destination.lstrip("/")
        if source_path.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source_path, target)
        elif source_path.is_file():
            # Replace through a new file so the running /run.sh keeps reading
            # the Stable copy it already opened.
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.beta-{os.getpid()}")
            shutil.copyfile(source_path, temporary)
            if destination.startswith("/usr/local/bin/") or destination == "/run.sh":
                temporary.chmod(0o755)
            temporary.replace(target)
        else:
            raise BetaChannelError(f"Beta build is missing {source}.")
        applied.append(target)
    return applied


def main(argv: list[str]) -> int:
    """Apply the selected Beta build at App startup.

    Prints the Beta version and exits 0 when it was applied; exits 3 when
    Stable should run, and 2 when the Beta build has failed to start
    repeatedly.
    """
    if argv[1:2] != ["apply"] or len(argv) != 3:
        print("usage: future-homes-tech-beta apply STABLE_VERSION", file=sys.stderr)
        return 64
    channel = BetaChannel(
        root=Path(os.environ.get("FHT_BETA_ROOT", DEFAULT_BETA_ROOT)),
        stable_version=argv[2],
    )
    release = channel.active_release()
    if release is None:
        return 3
    if channel.start_attempts() >= MAX_UNCONFIRMED_STARTS:
        return 2
    channel.record_start_attempt()
    try:
        apply_release(release)
    except (BetaChannelError, OSError) as err:
        print(f"Unable to apply Beta build: {err}", file=sys.stderr)
        return 1
    print(release.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
