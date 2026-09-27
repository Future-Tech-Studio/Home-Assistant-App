"""Run isolated Users browser checks with a fresh temporary database."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from access_preview import create_preview


def main():
    node = os.environ.get("FHT_NODE_BINARY") or shutil.which("node")
    if not node:
        raise SystemExit("Set FHT_NODE_BINARY to your Node executable.")
    with tempfile.TemporaryDirectory(prefix="fht-access-browser-") as directory:
        server = create_preview(directory)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            environment = {**os.environ, "FHT_ACCESS_PREVIEW_URL": f"http://127.0.0.1:{server.server_address[1]}/"}
            result = subprocess.run([node, str(Path(__file__).with_name("access_browser.cjs"))], env=environment, timeout=150)
            return result.returncode
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    raise SystemExit(main())
