#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_BIN="${NODE_BIN:-}"

if [[ -z "${NODE_BIN}" ]]; then
    if command -v node >/dev/null 2>&1; then
        NODE_BIN="$(command -v node)"
    elif [[ -x "/Users/spicerfamily/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node" ]]; then
        NODE_BIN="/Users/spicerfamily/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    else
        echo "Node.js is required for the browser-module syntax check." >&2
        exit 1
    fi
fi

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/fht-release-pycache}"
cd "${ROOT}"

echo "[1/4] Compiling Python sources"
"${PYTHON_BIN}" -m py_compile future_homes_tech_app/*.py scripts/package_candidate.py

echo "[2/4] Checking browser module syntax"
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

echo "[3/4] Running the complete regression suite"
"${PYTHON_BIN}" -m unittest discover -s tests -v

echo "[4/4] Verifying release metadata and runtime assets"
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
