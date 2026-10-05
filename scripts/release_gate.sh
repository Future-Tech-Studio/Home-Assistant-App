#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_BIN="${NODE_BIN:-}"

if [[ -z "${NODE_BIN}" ]]; then
    if command -v node >/dev/null 2>&1; then
        NODE_BIN="$(command -v node)"
    elif [[ -x "${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node" ]]; then
        NODE_BIN="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    else
        echo "Node.js is required for the browser-module syntax check." >&2
        exit 1
    fi
fi

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/fht-release-pycache}"
cd "${ROOT}"

echo "[1/6] Compiling Python sources"
"${PYTHON_BIN}" -m py_compile future_homes_tech_app/*.py scripts/*.py

echo "[2/6] Linting Python sources"
if command -v ruff >/dev/null 2>&1; then
    ruff check --select F,E9,B --quiet future_homes_tech_app scripts
elif "${PYTHON_BIN}" -m pyflakes --version >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pyflakes future_homes_tech_app scripts
else
    echo "ruff or pyflakes is required for the lint check (pip install ruff)." >&2
    exit 1
fi

echo "[3/6] Checking browser module syntax"
MODULE_DIR="$(mktemp -d /tmp/fht-index.XXXXXX)"
MODULE_PATH="${MODULE_DIR}/index.mjs"
trap 'rm -rf "${MODULE_DIR}"' EXIT
"${PYTHON_BIN}" - "${MODULE_PATH}" <<'PY'
from pathlib import Path
import sys

html = Path("future_homes_tech_app/web/index.html").read_text(encoding="utf-8")
marker = '<script type="module" nonce="__FHT_CSP_NONCE__">'
start = html.index(marker) + len(marker)
end = html.index("</script>", start)
Path(sys.argv[1]).write_text(html[start:end], encoding="utf-8")
import importlib.util
import re
spec = importlib.util.spec_from_file_location("fht_release_server", "future_homes_tech_app/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
bundle = server.interface_bundle(str(Path("future_homes_tech_app/web").resolve()), 0, 0)
for filename, asset in bundle["assets"].items():
    if filename.endswith(".js"):
        Path(sys.argv[1]).with_name("served.mjs").write_bytes(asset["content"])
bootstrap = re.search(r'<script nonce="__FHT_CSP_NONCE__">(.*?)</script>', html, re.S)
Path(sys.argv[1]).with_name("bootstrap.js").write_text(bootstrap.group(1), encoding="utf-8")
PY
"${NODE_BIN}" --check "${MODULE_PATH}"
"${NODE_BIN}" --check "${MODULE_DIR}/served.mjs"
"${NODE_BIN}" --check "${MODULE_DIR}/bootstrap.js"
cp future_homes_tech_app/web/users-access.js "${MODULE_DIR}/users-access.mjs"
"${NODE_BIN}" --check "${MODULE_DIR}/users-access.mjs"
cp future_homes_tech_app/web/maintenance.js "${MODULE_DIR}/maintenance.mjs"
"${NODE_BIN}" --check "${MODULE_DIR}/maintenance.mjs"

echo "[4/6] Running the complete regression suite"
"${PYTHON_BIN}" -m unittest discover -s tests -v

echo "[5/6] Running browser checks"
if [[ "${FHT_SKIP_BROWSER_TESTS:-0}" == "1" ]]; then
    echo "WARNING: browser checks skipped by FHT_SKIP_BROWSER_TESTS=1; this is not a full release check." >&2
else
    if [[ -z "${FHT_PLAYWRIGHT:-}" ]] && ! "${NODE_BIN}" -e "require('playwright')" >/dev/null 2>&1; then
        echo "Playwright is required for browser checks. Set FHT_PLAYWRIGHT to its module path, or FHT_SKIP_BROWSER_TESTS=1 to skip." >&2
        exit 1
    fi
    export FHT_NODE_BINARY="${FHT_NODE_BINARY:-${NODE_BIN}}"
    (cd tests && "${PYTHON_BIN}" run_access_browser.py && "${PYTHON_BIN}" run_maintenance_browser.py && "${PYTHON_BIN}" run_switches_browser.py)
    "${NODE_BIN}" tests/phone_alerts_browser.cjs
    "${NODE_BIN}" tests/alarm_alignment.cjs
    "${NODE_BIN}" tests/room_devices_browser.cjs
    "${NODE_BIN}" tests/room_modes_browser.cjs
    "${NODE_BIN}" tests/environment_browser.cjs
    "${NODE_BIN}" tests/door_open_alerts_browser.cjs
    "${NODE_BIN}" tests/settings_history_browser.cjs
    "${NODE_BIN}" tests/future_tech_portal_browser.cjs
    "${NODE_BIN}" tests/scene_lights_browser.cjs
    "${NODE_BIN}" tests/update_button_browser.cjs
    "${NODE_BIN}" tests/lighting_columns_browser.cjs
    "${NODE_BIN}" tests/update_return_browser.cjs
    "${NODE_BIN}" tests/page_loading_browser.cjs
fi

echo "[6/6] Verifying release metadata and runtime assets"
"${PYTHON_BIN}" scripts/build_release_manifest.py --check
"${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import re

root = Path.cwd()
config = (root / "future_homes_tech_app/config.yaml").read_text(encoding="utf-8")
html = (root / "future_homes_tech_app/web/index.html").read_text(encoding="utf-8")
version_match = re.search(r"^version:\s*([^\s]+)", config, re.MULTILINE)
if not version_match:
    raise SystemExit("config.yaml has no version")
version = version_match.group(1)
required = (
    f'<div class="brand-version">V {version}</div>',
    f'const CLIENT_VERSION = "{version}"',
    'url("fht-infinite-vertical-warp-4da39efb.webp")',
)
for value in required:
    if value not in html:
        raise SystemExit(f"release metadata mismatch: {value}")
web = root / "future_homes_tech_app/web"
for retired in (
    "fht-groups-data-lanes.png",
    "fht-groups-hyperlane.png",
    "fht-infinite-vertical-warp.png",
):
    if (web / retired).exists():
        raise SystemExit(f"retired runtime asset remains: {retired}")
print(f"Release gate passed for {version}.")
PY
