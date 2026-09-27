import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("candidate_local_test", Path(__file__).parents[1] / "scripts/package_candidate.py")
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class LocalCandidateTests(unittest.TestCase):
    def test_local_candidate_is_honest_and_preserves_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "future_homes_tech_app"
            (app / "web").mkdir(parents=True)
            (app / "config.yaml").write_text("version: 0.5.35\n")
            (app / "web/index.html").write_text('<div class="brand-version">V 0.5.35</div>\nconst CLIENT_VERSION = "0.5.35";')
            stable = root / "STABLE.json"
            stable.write_text('{"stable_version":"0.5.23"}')
            original = stable.read_bytes()
            candidates = root / "candidates"
            with patch.multiple(PACKAGE, ROOT=root, APP_SOURCE=app, STABLE_POINTER=stable, CANDIDATE_ROOT=candidates), patch("sys.argv", ["package_candidate", "0.5.35", "--local-only"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(PACKAGE.main(), 0)
                with self.assertRaises(SystemExit):
                    PACKAGE.main()
            manifest = json.loads((candidates / "0.5.35/MANIFEST.json").read_text())
            self.assertEqual(manifest["status"], "local-candidate-not-mounted-or-installed")
            self.assertFalse(any(key.startswith("mounted_") for key in manifest))
            self.assertTrue((candidates / "0.5.35" / manifest["local_runtime_archive"]).is_file())
            self.assertEqual(stable.read_bytes(), original)
