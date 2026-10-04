#!/usr/bin/env python3
"""Install and activate Beta channel builds for the Future Homes Tech App.

Home Assistant builds the App from the Stable (``main``) branch. When the
``beta_mode`` option is on, this module downloads the ``beta`` build into the
App's private ``/data`` volume and, on the next App start, copies it over the
Stable files named by the Beta ``Dockerfile`` ``COPY`` lines. Turning Beta mode
off, or installing a Stable version at least as new, starts Stable again.

A Beta build is described by ``RELEASE.json`` (see
scripts/build_release_manifest.py): every file with its SHA-256 and what the
build needs from Stable. Only files that differ from what is already installed
are downloaded, each one pinned to the offered commit and checked against its
hash.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
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
# The branch list git itself reads (git ls-remote): never cached, and not
# counted against GitHub's REST API limit.
DEFAULT_BETA_REFS_URL = "https://github.com/fht-ha/FHT-HA.git/info/refs?service=git-upload-pack"
MAX_REFS_BYTES = 1024 * 1024
BETA_CONFIG_AT_COMMIT_URL = (
    "https://raw.githubusercontent.com/fht-ha/FHT-HA/{sha}/"
    "future_homes_tech_app/config.yaml"
)
BETA_ARCHIVE_AT_COMMIT_URL = "https://codeload.github.com/fht-ha/FHT-HA/tar.gz/{sha}"
BETA_FILE_AT_COMMIT_URL = (
    "https://raw.githubusercontent.com/fht-ha/FHT-HA/{sha}/"
    "future_homes_tech_app/{path}"
)
DEFAULT_APP_INFO_URL = "http://supervisor/addons/self/info"
GITHUB_HOSTS = {"api.github.com", "raw.githubusercontent.com", "codeload.github.com"}
MAX_RELEASE_BYTES = 60 * 1024 * 1024
MAX_RELEASE_FILES = 2000
DEFAULT_RESTART_URL = "http://supervisor/addons/self/restart"
APP_DIRECTORY = "future_homes_tech_app"
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024
# In Beta mode the App looks for a new Beta every minute. Without a GitHub
# access token it reads the git branch list (DEFAULT_BETA_REFS_URL), because
# GitHub's REST API allows only 60 requests an hour from one home and counts
# unchanged (304) answers too; with a token it asks the REST API, where
# unchanged answers are free.
LATEST_CACHE_TTL_SECONDS = 60
# Opening the App checks again once the last check is half a minute old.
FORCED_CHECK_SECONDS = 30
# A 429 without Retry-After waits this long; no wait is longer than an hour.
RATE_LIMIT_WAIT_SECONDS = 300
MAX_BACKOFF_SECONDS = 3600
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


def branch_commit_from_refs(data: bytes, branch: str = "beta") -> str:
    """Return a branch's commit from a git ref advertisement (pkt-line format)."""
    wanted = f"refs/heads/{branch}".encode()
    position = 0
    while position + 4 <= len(data):
        try:
            length = int(data[position:position + 4], 16)
        except ValueError:
            return ""
        if length == 0:  # flush packet
            position += 4
            continue
        if length < 4:
            return ""
        line = data[position + 4:position + length].split(b"\0", 1)[0].strip()
        position += length
        sha, _, ref = line.partition(b" ")
        if ref == wanted and re.fullmatch(rb"[0-9a-f]{40}", sha):
            return sha.decode("ascii")
    return ""


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
        github_token: str = "",
        refs_url: str = "",
        info_url: str = DEFAULT_APP_INFO_URL,
        filesystem_root: Path = Path("/"),
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
        self._checked_at: float | None = None
        self._last_error = ""
        # After GitHub refuses a request for its rate limit, nothing goes to
        # GitHub before this time.monotonic() value.
        self._blocked_until = 0.0
        # Checking the branch's newest commit avoids GitHub's five-minute raw
        # file cache. Unchanged (304) answers are free of GitHub's rate limit
        # only with a GitHub access token; without one they count.
        self.commit_url = commit_url
        # Needed only when the repository is private.
        self.github_token = github_token
        self.refs_url = refs_url
        self.info_url = info_url
        self.filesystem_root = Path(filesystem_root)
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
        """Return the version published on the beta branch.

        GitHub is asked at most every cache_ttl seconds (FORCED_CHECK_SECONDS
        when forced), and not at all while it has asked the App to wait.
        Between checks, and when a check fails, the last version found is
        returned; with none found yet, the last error is raised again.
        """
        with self._lock:
            now = time.monotonic()
            wait = min(FORCED_CHECK_SECONDS, self.cache_ttl) if force else self.cache_ttl
            blocked = now < self._blocked_until
            if blocked or (self._checked_at is not None and now - self._checked_at < wait):
                if self._latest is not None:
                    return self._latest
                if blocked or self._last_error:
                    raise BetaChannelError(self._last_error or self._wait_message())
            self._checked_at = now
            try:
                version = self._check_latest()
            except BetaChannelError as err:
                if str(err) != self._last_error:
                    print(f"[Beta] WARNING Unable to check for a new Beta: {err}", flush=True)
                self._last_error = str(err)
                if self._latest is not None:
                    return self._latest
                raise
            if self._last_error:
                print("[Beta] Checking for a new Beta works again.", flush=True)
            self._last_error = ""
            return version

    def _check_latest(self) -> str:
        sha = self._latest_commit()
        if sha and sha == self._commit_sha and self._latest is not None:
            return self._latest
        if not sha and time.monotonic() < self._blocked_until:
            # The branch file is no way round the limit: GitHub caches it for
            # five minutes and limits it the same way.
            raise BetaChannelError(self._wait_message())
        url = BETA_CONFIG_AT_COMMIT_URL.format(sha=sha) if sha else self.config_url
        text = self._download(url, 256 * 1024).decode("utf-8")
        self._latest = config_version(text)
        self._commit_sha = sha
        return self._latest

    def _wait_message(self) -> str:
        minutes = max(1, round((self._blocked_until - time.monotonic()) / 60))
        if self.github_token:
            return f"GitHub asked the App to wait; checking again in about {minutes} min."
        return (
            f"GitHub's limit on checks without a GitHub access token is used up; checking again in about {minutes} min."
        )

    def _back_off(self, err: HTTPError) -> None:
        """Wait as long as GitHub asks when it refuses a request for its rate limit."""
        if err.code not in {403, 429}:
            return
        headers = err.headers or {}
        delay = 0.0
        try:
            if str(headers.get("X-RateLimit-Remaining", "")).strip() == "0":
                delay = float(headers.get("X-RateLimit-Reset", 0)) - time.time()
            elif headers.get("Retry-After"):
                delay = float(headers.get("Retry-After"))
        except (TypeError, ValueError):
            delay = 0.0
        if delay <= 0 and err.code == 429:
            delay = RATE_LIMIT_WAIT_SECONDS
        if delay > 0:
            self._blocked_until = max(self._blocked_until, time.monotonic() + min(delay, MAX_BACKOFF_SECONDS))

    def _latest_commit(self) -> str:
        """Return the beta branch's newest commit, or "" to use the branch URL."""
        if time.monotonic() < self._blocked_until:
            return ""
        if self.refs_url and not self.github_token:
            sha = self._latest_commit_from_refs()
            if sha or time.monotonic() < self._blocked_until:
                return sha
        if not self.commit_url:
            return ""
        headers = {
            **self._github_headers(self.commit_url),
            "Accept": "application/vnd.github.sha",
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
            self._back_off(err)
            return ""
        except (URLError, OSError):
            return ""
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return ""
        self._commit_etag = etag
        self._etag_sha = sha
        return sha

    def _latest_commit_from_refs(self) -> str:
        """Read the beta branch's commit from GitHub's git branch list."""
        request = Request(self.refs_url, headers={"User-Agent": "future-homes-tech-app"})
        try:
            with urlopen(request, timeout=15) as response:
                data = response.read(MAX_REFS_BYTES)
        except HTTPError as err:
            self._back_off(err)
            return ""
        except (URLError, OSError):
            return ""
        return branch_commit_from_refs(data)

    def status(self, force: bool = False) -> dict[str, Any]:
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
            latest = self.latest_version(force=force)
        except BetaChannelError as err:
            payload["beta_error"] = str(err)
            return payload
        # A Beta already found stays offered while GitHub can't be asked.
        waiting = time.monotonic() < self._blocked_until
        payload["beta_error"] = (self._wait_message() if waiting else self._last_error) or None
        payload["beta_available_version"] = latest
        payload["beta_update_available"] = is_newer(latest, running)
        return payload

    def install_latest(self) -> str:
        """Download the Beta build, verify it, and select it for next start."""
        with self._lock:
            sha = self._latest_commit() or self._commit_sha
        if not sha:
            raise BetaChannelError("Unable to find the newest Beta build on GitHub.")
        self.releases.mkdir(parents=True, exist_ok=True)
        staging = self.releases / f".staging-{os.getpid()}-{time.time_ns()}"
        try:
            try:
                manifest_bytes = self._download(
                    BETA_FILE_AT_COMMIT_URL.format(sha=sha, path="RELEASE.json"), 4 * 1024 * 1024
                )
            except BetaChannelError:
                manifest_bytes = b""
            if manifest_bytes:
                self._install_from_manifest(sha, manifest_bytes, staging)
            else:
                # Builds from before RELEASE.json: the whole branch archive.
                archive = self._download(BETA_ARCHIVE_AT_COMMIT_URL.format(sha=sha), MAX_ARCHIVE_BYTES)
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
            self._checked_at = time.monotonic()
        return version

    def _install_from_manifest(self, sha: str, manifest_bytes: bytes, staging: Path) -> None:
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            files = manifest["files"]
            if not isinstance(files, dict):
                raise TypeError("files")
        except (ValueError, KeyError, TypeError) as err:
            raise BetaChannelError("Beta RELEASE.json is not valid.") from err
        if len(files) > MAX_RELEASE_FILES or sum(int(item.get("size", 0)) for item in files.values()) > MAX_RELEASE_BYTES:
            raise BetaChannelError("Beta build is larger than allowed.")
        self.check_requirements(manifest.get("requires") or {}, str(manifest.get("version") or ""))
        staging.mkdir(parents=True)
        # The Dockerfile says where Stable already keeps each file.
        dockerfile = self._fetch_file(sha, "Dockerfile", files["Dockerfile"], staging, [])
        copies = dockerfile_copies(dockerfile.decode("utf-8"))
        previous = self.releases / self.installed_version() if self.installed_version() else None
        downloaded = 0
        for relative, meta in sorted(files.items()):
            if relative == "Dockerfile":
                continue
            local = [previous / relative] if previous else []
            for source, destination in copies:
                target = self.filesystem_root / destination.lstrip("/")
                if relative == source:
                    local.append(target)
                elif relative.startswith(source.rstrip("/") + "/"):
                    local.append(target / relative[len(source.rstrip("/")) + 1:])
            if self._fetch_file(sha, relative, meta, staging, local, count_download=True) is None:
                downloaded += 1
        print(f"[Beta] Downloaded {downloaded} of {len(files)} files for Beta {manifest.get('version')}.", flush=True)

    def _fetch_file(self, sha: str, relative: str, meta: Any, staging: Path, local: list[Path],
                    count_download: bool = False) -> bytes | None:
        """Place one verified file in staging, reusing a matching local copy.

        Returns the file bytes, or None when it had to be downloaded and
        count_download is set.
        """
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise BetaChannelError(f"Unsafe path in Beta RELEASE.json: {relative}")
        expected = str((meta or {}).get("sha256") or "")
        size = int((meta or {}).get("size") or 0)
        data = None
        for candidate in local:
            try:
                if candidate.is_file() and candidate.stat().st_size == size:
                    content = candidate.read_bytes()
                    if hashlib.sha256(content).hexdigest() == expected:
                        data = content
                        break
            except OSError:
                continue
        fetched = data is None
        if fetched:
            data = self._download(BETA_FILE_AT_COMMIT_URL.format(sha=sha, path=quote(relative)), size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
                raise BetaChannelError(f"Beta file {relative} does not match RELEASE.json.")
        target = staging.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return None if (fetched and count_download) else data

    def check_requirements(self, requires: dict[str, Any], version: str) -> None:
        """Refuse a Beta that needs options or packages Stable lacks."""
        missing_options = []
        options = [str(name) for name in requires.get("options") or []]
        if options and self.token:
            request = Request(self.info_url, headers={"Authorization": f"Bearer {self.token}"})
            try:
                with urlopen(request, timeout=15) as response:
                    info = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, OSError, ValueError) as err:
                raise BetaChannelError(f"Unable to read the installed App options: {err}") from err
            installed = set(((info.get("data") or info).get("options") or {}).keys())
            missing_options = [name for name in options if name not in installed]
        missing_packages = [
            package for package in requires.get("apk_packages") or []
            if not self._apk_installed(str(package))
        ]
        if missing_options or missing_packages:
            needs = [
                *([f"options {', '.join(missing_options)}"] if missing_options else []),
                *([f"packages {', '.join(missing_packages)}"] if missing_packages else []),
            ]
            raise BetaChannelError(
                f"Beta {version} needs {' and '.join(needs)}, which only a Stable update can add. "
                "Install that Stable update first."
            )

    @staticmethod
    def _apk_installed(package: str) -> bool:
        if not shutil.which("apk"):
            return True  # Not an Alpine container (tests); nothing to check.
        return subprocess.run(["apk", "info", "-e", package], capture_output=True).returncode == 0

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

    def _github_headers(self, url: str) -> dict[str, str]:
        headers = {"User-Agent": "future-homes-tech-app"}
        if self.github_token and urlsplit(url).hostname in GITHUB_HOSTS:
            headers["Authorization"] = f"token {self.github_token}"
        return headers

    def _download(self, url: str, limit: int) -> bytes:
        request = Request(url, headers=self._github_headers(url))
        try:
            with urlopen(request, timeout=120) as response:
                data = response.read(limit + 1)
        except HTTPError as err:
            self._back_off(err)
            hint = (
                " If the repository is private, set the GitHub access token in the App configuration."
                if err.code in {401, 403, 404} and urlsplit(url).hostname in GITHUB_HOSTS
                else ""
            )
            raise BetaChannelError(f"Unable to reach the Beta channel: {err}.{hint}") from err
        except (URLError, OSError) as err:
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
