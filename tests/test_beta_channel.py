"""Tests for the Beta channel installer."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "future_homes_tech_app" / "fht_beta.py"
SPEC = importlib.util.spec_from_file_location("fht_beta", MODULE_PATH)
BETA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BETA)

DOCKERFILE = """FROM base
COPY server.py /usr/local/bin/future-homes-tech-server
COPY run.sh /run.sh
COPY web /opt/future-homes-tech/web
"""


def archive(version: str, extra: dict[str, bytes] | None = None) -> bytes:
    files = {
        "FHT-HA-beta/future_homes_tech_app/config.yaml": f"name: App\nversion: {version}\n".encode(),
        "FHT-HA-beta/future_homes_tech_app/Dockerfile": DOCKERFILE.encode(),
        "FHT-HA-beta/future_homes_tech_app/run.sh": b"#!/bin/sh\n",
        "FHT-HA-beta/future_homes_tech_app/server.py": b"print('beta')\n",
        "FHT-HA-beta/future_homes_tech_app/web/index.html": b"<html></html>",
        "FHT-HA-beta/README.md": b"not part of the App",
    }
    files.update(extra or {})
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def pkt(line: bytes) -> bytes:
    """One git pkt-line: four hex digits of length, then the line."""
    return b"%04x" % (len(line) + 4) + line


class BetaChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.channel = BETA.BetaChannel(root=self.root / "beta", stable_version="0.6.1")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def install(self, payload: bytes) -> str:
        """Install a build that predates RELEASE.json (branch archive)."""
        def download(url, limit):
            if url.endswith("/RELEASE.json"):
                raise BETA.BetaChannelError("404")
            return payload
        with patch.object(self.channel, "_latest_commit", return_value="a" * 40), \
                patch.object(self.channel, "_download", side_effect=download):
            return self.channel.install_latest()

    def manifest_install(self, version: str, files: dict[str, bytes], requires: dict | None = None):
        """Install from RELEASE.json; return the relative paths that were downloaded."""
        import hashlib
        manifest = {"version": version, "requires": requires or {}, "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in files.items()}}
        downloaded = []
        def download(url, limit):
            relative = url.split("/future_homes_tech_app/", 1)[1]
            if relative == "RELEASE.json":
                return json.dumps(manifest).encode()
            downloaded.append(relative)
            return files[relative]
        with patch.object(self.channel, "_latest_commit", return_value="b" * 40), \
                patch.object(self.channel, "_download", side_effect=download):
            self.channel.install_latest()
        return downloaded

    def app_files(self, version: str, server: bytes = b"print('beta')\n") -> dict[str, bytes]:
        return {
            "config.yaml": f"version: {version}\n".encode(),
            "Dockerfile": DOCKERFILE.encode(),
            "run.sh": b"#!/bin/sh\n",
            "server.py": server,
            "web/index.html": b"<html></html>",
        }

    def test_manifest_install_downloads_only_changed_files(self) -> None:
        self.assertEqual(len(self.manifest_install("0.6.2", self.app_files("0.6.2"))), 5)
        downloaded = self.manifest_install("0.6.3", {**self.app_files("0.6.3"), "server.py": b"print('newer')\n"})
        self.assertEqual(sorted(downloaded), ["Dockerfile", "config.yaml", "server.py"])
        self.assertEqual((self.root / "beta/releases/0.6.3/server.py").read_bytes(), b"print('newer')\n")
        self.assertEqual(self.channel.installed_version(), "0.6.3")

    def test_manifest_install_rejects_tampered_files(self) -> None:
        import hashlib
        files = self.app_files("0.6.2")
        manifest = {"version": "0.6.2", "requires": {}, "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in files.items()}}
        def download(url, limit):
            relative = url.split("/future_homes_tech_app/", 1)[1]
            if relative == "RELEASE.json":
                return json.dumps(manifest).encode()
            return b"print('evil')\n" if relative == "server.py" else files[relative]
        with patch.object(self.channel, "_latest_commit", return_value="c" * 40), \
                patch.object(self.channel, "_download", side_effect=download), \
                self.assertRaisesRegex(BETA.BetaChannelError, "server.py does not match"):
            self.channel.install_latest()
        self.assertEqual(self.channel.installed_version(), "")

    def test_manifest_install_refuses_missing_stable_requirements(self) -> None:
        with patch.object(self.channel, "_apk_installed", side_effect=lambda package: package != "ffmpeg"), \
                self.assertRaisesRegex(BETA.BetaChannelError, "packages ffmpeg, which only a Stable update can add"):
            self.manifest_install("0.6.2", self.app_files("0.6.2"), {"apk_packages": ["python3", "ffmpeg"]})
        self.assertEqual(self.channel.installed_version(), "")

    def test_github_requests_carry_the_access_token(self) -> None:
        channel = BETA.BetaChannel(root=self.root / "beta", github_token="secret")
        self.assertEqual(channel._github_headers("https://raw.githubusercontent.com/x")["Authorization"], "token secret")
        self.assertNotIn("Authorization", channel._github_headers("http://supervisor/addons/self/info"))

    def test_installs_only_the_app_directory_and_selects_it(self) -> None:
        self.assertEqual(self.install(archive("0.6.2")), "0.6.2")
        release = self.root / "beta/releases/0.6.2"
        self.assertTrue((release / "server.py").is_file())
        self.assertFalse((release / "README.md").exists())
        self.assertEqual(self.channel.installed_version(), "0.6.2")
        self.assertEqual(self.channel.active_release(), release)

    def test_keeps_only_the_selected_release(self) -> None:
        self.install(archive("0.6.2"))
        self.install(archive("0.6.3"))
        releases = sorted(path.name for path in (self.root / "beta/releases").iterdir())
        self.assertEqual(releases, ["0.6.3"])

    def test_rejects_beta_not_newer_than_stable(self) -> None:
        with self.assertRaises(BETA.BetaChannelError):
            self.install(archive("0.6.1"))
        self.assertEqual(self.channel.installed_version(), "")

    def test_rejects_unsafe_archive_paths(self) -> None:
        payload = archive("0.6.2", {"FHT-HA-beta/future_homes_tech_app/../../evil": b"x"})
        with self.assertRaises(BETA.BetaChannelError):
            self.install(payload)
        self.assertFalse((self.root / "evil").exists())
        self.assertEqual(self.channel.installed_version(), "")

    def test_stable_catching_up_disables_the_beta_overlay(self) -> None:
        self.install(archive("0.6.2"))
        newer_stable = BETA.BetaChannel(root=self.root / "beta", stable_version="0.6.2")
        self.assertIsNone(newer_stable.active_release())

    def test_apply_copies_dockerfile_targets(self) -> None:
        self.install(archive("0.6.2"))
        filesystem = self.root / "fs"
        (filesystem / "opt/future-homes-tech/web").mkdir(parents=True)
        (filesystem / "opt/future-homes-tech/web/stale.js").write_text("old")
        BETA.apply_release(self.channel.active_release(), filesystem)
        self.assertEqual(
            (filesystem / "usr/local/bin/future-homes-tech-server").read_text(),
            "print('beta')\n",
        )
        self.assertTrue((filesystem / "run.sh").stat().st_mode & 0o100)
        self.assertTrue((filesystem / "opt/future-homes-tech/web/index.html").is_file())
        self.assertFalse((filesystem / "opt/future-homes-tech/web/stale.js").exists())

    def test_status_offers_newer_beta_only_in_beta_mode(self) -> None:
        with patch.object(self.channel, "_download", return_value=b"version: 0.6.2\n"):
            with patch.dict(BETA.os.environ, {"FHT_BETA_MODE": "0", "FHT_RUNNING_VERSION": "0.6.1"}):
                self.assertFalse(self.channel.status()["beta_update_available"])
            with patch.dict(BETA.os.environ, {"FHT_BETA_MODE": "1", "FHT_RUNNING_VERSION": "0.6.1"}):
                status = self.channel.status()
            self.assertTrue(status["beta_update_available"])
            self.assertEqual(status["beta_available_version"], "0.6.2")
            with patch.dict(BETA.os.environ, {"FHT_BETA_MODE": "1", "FHT_RUNNING_VERSION": "0.6.2"}):
                self.channel._latest = None
                self.assertFalse(self.channel.status()["beta_update_available"])

    def test_startup_command_reports_when_stable_should_run(self) -> None:
        with patch.dict(BETA.os.environ, {"FHT_BETA_ROOT": str(self.root / "beta")}):
            self.assertEqual(BETA.main(["fht_beta", "apply", "0.6.1"]), 3)

    def test_unconfirmed_beta_starts_fall_back_to_stable(self) -> None:
        self.install(archive("0.6.2"))
        environment = {"FHT_BETA_ROOT": str(self.root / "beta")}
        with patch.object(BETA, "apply_release"), patch.dict(BETA.os.environ, environment), patch("sys.stdout"):
            for _ in range(BETA.MAX_UNCONFIRMED_STARTS):
                self.assertEqual(BETA.main(["fht_beta", "apply", "0.6.1"]), 0)
            self.assertEqual(BETA.main(["fht_beta", "apply", "0.6.1"]), 2)
            self.channel.confirm_started()
            self.assertEqual(BETA.main(["fht_beta", "apply", "0.6.1"]), 0)

    def test_new_beta_install_clears_failed_starts(self) -> None:
        self.install(archive("0.6.2"))
        for _ in range(BETA.MAX_UNCONFIRMED_STARTS):
            self.channel.record_start_attempt()
        self.install(archive("0.6.3"))
        self.assertEqual(self.channel.start_attempts(), 0)

    def test_startup_script_keeps_beta_flag_when_switching(self) -> None:
        launcher = MODULE_PATH.with_name("run.sh").read_text(encoding="utf-8")
        self.assertIn("source /run.sh", launcher)
        self.assertNotIn("exec /run.sh", launcher)

    def test_commit_check_reuses_version_when_unchanged(self) -> None:
        from urllib.error import HTTPError
        sha = "a" * 40
        channel = BETA.BetaChannel(root=self.root / "beta", stable_version="0.6.1",
                                   commit_url="https://api.github.test/commits/beta", cache_ttl=0)

        class Response(io.BytesIO):
            headers = {"ETag": f'"{sha}"'}
            def __enter__(self): return self
            def __exit__(self, *args): return None

        calls = []
        def fake_urlopen(request, timeout=0):
            calls.append(request.get_header("If-none-match"))
            if len(calls) == 1:
                return Response(sha.encode())
            raise HTTPError(request.full_url, 304, "Not Modified", {}, None)

        with patch.object(BETA, "urlopen", fake_urlopen), \
                patch.object(channel, "_download", return_value=b"version: 0.6.9\n") as download:
            self.assertEqual(channel.latest_version(), "0.6.9")
            self.assertEqual(channel.latest_version(), "0.6.9")
        self.assertEqual(calls, [None, f'"{sha}"'])
        download.assert_called_once_with(BETA.BETA_CONFIG_AT_COMMIT_URL.format(sha=sha), 256 * 1024)

    def test_start_counts_as_healthy_only_after_running_a_while(self) -> None:
        import importlib.util as util
        spec = util.spec_from_file_location("fht_server_health", MODULE_PATH.with_name("server.py"))
        server = util.module_from_spec(spec)
        spec.loader.exec_module(server)
        self.channel.record_start_attempt()
        with patch.object(server.time, "sleep") as sleep:
            server.confirm_healthy_start(self.channel)
        sleep.assert_called_once_with(server.HEALTHY_START_SECONDS)
        self.assertGreaterEqual(server.HEALTHY_START_SECONDS, 120)
        self.assertEqual(self.channel.start_attempts(), 0)

    def test_pointer_ignores_incomplete_release(self) -> None:
        (self.root / "beta").mkdir()
        (self.root / "beta/current.json").write_text(json.dumps({"version": "0.6.9"}))
        self.assertEqual(self.channel.installed_version(), "")

    def commit_channel(self, cache_ttl: float = BETA.LATEST_CACHE_TTL_SECONDS):
        return BETA.BetaChannel(root=self.root / "beta", stable_version="0.6.1",
                                commit_url="https://api.github.test/commits/beta", cache_ttl=cache_ttl)

    @staticmethod
    def commit_response(sha: str):
        class Response(io.BytesIO):
            headers = {"ETag": f'"{sha}"'}
            def __enter__(self): return self
            def __exit__(self, *args): return None
        return Response(sha.encode())

    def test_checks_for_a_new_beta_every_minute_and_sooner_when_forced(self) -> None:
        from urllib.error import HTTPError
        sha = "a" * 40
        channel = self.commit_channel()
        calls = []
        def fake_urlopen(request, timeout=0):
            calls.append(request.full_url)
            if len(calls) == 1:
                return self.commit_response(sha)
            raise HTTPError(request.full_url, 304, "Not Modified", {}, None)

        with patch.object(BETA, "urlopen", fake_urlopen), \
                patch.object(channel, "_download", return_value=b"version: 0.6.9\n"):
            self.assertEqual(channel.latest_version(), "0.6.9")
            channel._checked_at -= 40
            self.assertEqual(channel.latest_version(), "0.6.9")
            self.assertEqual(len(calls), 1, "a regular poll within a minute reuses the last check")
            self.assertEqual(channel.latest_version(force=True), "0.6.9")
            self.assertEqual(len(calls), 2, "opening the App checks once the last check is half a minute old")
            self.assertEqual(channel.latest_version(force=True), "0.6.9")
            self.assertEqual(len(calls), 2)
            channel._checked_at -= 61
            channel.latest_version()
            self.assertEqual(len(calls), 3)
        self.assertEqual(BETA.LATEST_CACHE_TTL_SECONDS, 60, "Beta mode looks for a new Beta every minute")

    REFS = (b"001e# service=git-upload-pack\n0000"
            + pkt(b"0" * 40 + b" HEAD\0multi_ack thin-pack side-band side-band-64k ofs-delta shallow agent=git/github\n")
            + pkt(b"b" * 40 + b" refs/heads/beta\n")
            + pkt(b"c" * 40 + b" refs/heads/main\n") + b"0000")

    def test_reads_the_beta_commit_from_the_git_branch_list(self) -> None:
        self.assertEqual(BETA.branch_commit_from_refs(self.REFS), "b" * 40)
        self.assertEqual(BETA.branch_commit_from_refs(self.REFS, "main"), "c" * 40)
        self.assertEqual(BETA.branch_commit_from_refs(b"<html>Rate limited</html>"), "")
        self.assertEqual(BETA.branch_commit_from_refs(b"001e# service=git-upload-pack\n0000"), "")

    def test_without_a_token_checks_skip_the_rest_api(self) -> None:
        refs = self.REFS
        class Response(io.BytesIO):
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
        for token, expected_host in (("", "github.com"), ("github_pat_x", "api.github.test")):
            channel = BETA.BetaChannel(root=self.root / "beta", stable_version="0.6.1", cache_ttl=0, github_token=token,
                                       commit_url="https://api.github.test/commits/beta", refs_url=BETA.DEFAULT_BETA_REFS_URL)
            hosts = []
            def fake_urlopen(request, timeout=0):
                hosts.append(request.host)
                return Response(refs if request.host == "github.com" else b"b" * 40)
            with self.subTest(token=bool(token)), patch.object(BETA, "urlopen", fake_urlopen), \
                    patch.object(channel, "_download", return_value=b"version: 0.6.9\n") as download:
                for _ in range(3):
                    self.assertEqual(channel.latest_version(), "0.6.9")
                self.assertEqual(set(hosts), {expected_host}, "git branch list without a token, REST API with one")
                download.assert_called_once_with(BETA.BETA_CONFIG_AT_COMMIT_URL.format(sha="b" * 40), 256 * 1024)

    def test_rate_limit_waits_for_github_and_keeps_offering_the_beta_found(self) -> None:
        import time
        from urllib.error import HTTPError
        sha = "a" * 40
        channel = self.commit_channel(cache_ttl=0)
        calls = []
        def fake_urlopen(request, timeout=0):
            calls.append(request.full_url)
            if len(calls) == 1:
                return self.commit_response(sha)
            raise HTTPError(request.full_url, 403, "rate limit exceeded",
                            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(time.time()) + 1800)}, None)

        with patch.object(BETA, "urlopen", fake_urlopen), \
                patch.object(channel, "_download", return_value=b"version: 0.6.9\n") as download, \
                patch("builtins.print") as printed, \
                patch.dict(BETA.os.environ, {"FHT_BETA_MODE": "1", "FHT_RUNNING_VERSION": "0.6.1"}):
            self.assertEqual(channel.latest_version(), "0.6.9")
            status = channel.status()
            self.assertEqual(len(calls), 2)
            for _ in range(3):
                again = channel.status(force=True)
        self.assertEqual(len(calls), 2, "nothing goes to GitHub until its limit resets")
        download.assert_called_once()  # no fallback to the branch file either
        for payload in (status, again):
            self.assertTrue(payload["beta_update_available"])
            self.assertEqual(payload["beta_available_version"], "0.6.9")
            self.assertIn("GitHub's limit", payload["beta_error"])
        self.assertAlmostEqual(channel._blocked_until - time.monotonic(), 1800, delta=5)
        printed.assert_called_once()
        self.assertIn("Unable to check for a new Beta", printed.call_args.args[0])

    def test_429_waits_five_minutes_and_an_hour_at_most(self) -> None:
        import time
        from urllib.error import HTTPError
        channel = self.commit_channel()
        def refuse(headers):
            def fake_urlopen(request, timeout=0):
                raise HTTPError(request.full_url, 429, "Too Many Requests", headers, None)
            return fake_urlopen
        with patch.object(BETA, "urlopen", refuse({})):
            with self.assertRaises(BETA.BetaChannelError):
                channel._download(BETA.DEFAULT_BETA_CONFIG_URL, 1024)
        self.assertAlmostEqual(channel._blocked_until - time.monotonic(), BETA.RATE_LIMIT_WAIT_SECONDS, delta=5)
        channel._blocked_until = 0.0
        with patch.object(BETA, "urlopen", refuse({"Retry-After": "99999"})):
            with self.assertRaises(BETA.BetaChannelError):
                channel._download(BETA.DEFAULT_BETA_CONFIG_URL, 1024)
        self.assertAlmostEqual(channel._blocked_until - time.monotonic(), BETA.MAX_BACKOFF_SECONDS, delta=5)
        with patch.object(BETA, "urlopen", side_effect=AssertionError("GitHub was asked while waiting")):
            self.assertEqual(channel._latest_commit(), "")

    def test_failed_check_is_not_repeated_on_every_poll(self) -> None:
        from urllib.error import URLError
        channel = self.commit_channel()
        def offline(request, timeout=0):
            raise URLError("offline")
        with patch.object(BETA, "urlopen", offline) as _, \
                patch.object(channel, "_download", side_effect=BETA.BetaChannelError("Unable to reach the Beta channel: offline")) as download, \
                patch("builtins.print"):
            for _ in range(5):
                with self.assertRaises(BETA.BetaChannelError):
                    channel.latest_version()
        download.assert_called_once()

    def test_install_uses_the_offered_commit_while_github_waits(self) -> None:
        import time
        self.channel._commit_sha = "c" * 40
        self.channel.commit_url = "https://api.github.test/commits/beta"
        self.channel._blocked_until = time.monotonic() + 600
        files = self.app_files("0.6.4")
        import hashlib
        manifest = {"version": "0.6.4", "requires": {}, "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in files.items()}}
        urls = []
        def download(url, limit):
            urls.append(url)
            relative = url.split("/future_homes_tech_app/", 1)[1]
            return json.dumps(manifest).encode() if relative == "RELEASE.json" else files[relative]
        with patch.object(BETA, "urlopen", side_effect=AssertionError("GitHub API was asked while waiting")), \
                patch.object(self.channel, "_download", side_effect=download), patch("builtins.print"):
            self.assertEqual(self.channel.install_latest(), "0.6.4")
        self.assertTrue(all(f"/{'c' * 40}/" in url for url in urls))


if __name__ == "__main__":
    unittest.main()
