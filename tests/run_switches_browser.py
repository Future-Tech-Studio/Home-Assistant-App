import os
from pathlib import Path
import subprocess
import tempfile
import threading

from access_preview import create_preview


with tempfile.TemporaryDirectory(prefix="fht-switches-preview-") as directory:
    server = create_preview(directory)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        result = subprocess.run([os.environ["FHT_NODE_BINARY"], str(Path(__file__).with_name("switches_browser.cjs"))], env={**os.environ, "FHT_SWITCHES_URL": f"http://127.0.0.1:{server.server_address[1]}/"}, timeout=120)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
    raise SystemExit(result.returncode)
