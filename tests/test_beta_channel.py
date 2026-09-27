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


if __name__ == "__main__":
    unittest.main()
