"""Start the fixture on loopback and check its HTTP responses."""

import json
import os
import subprocess
import sys
from pathlib import Path
from queue import Queue
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen


def read_json(url):
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def main():
    version = "fixture-smoke"
    env = dict(os.environ, HOST="127.0.0.1", PORT="0", APP_VERSION=version)
    app = Path(__file__).with_name("app.py")
    with subprocess.Popen(
        [sys.executable, str(app)], env=env, stdout=subprocess.PIPE, text=True
    ) as process:
        try:
            output = Queue()
            Thread(target=lambda: output.put(process.stdout.readline()), daemon=True).start()
            startup = output.get(timeout=5).strip()
            prefix = "TV2 fixture listening on 127.0.0.1:"
            if not startup.startswith(prefix):
                raise RuntimeError(f"Unexpected fixture startup output: {startup!r}")
            base_url = f"http://127.0.0.1:{int(startup.removeprefix(prefix))}"
            assert read_json(f"{base_url}/healthz") == (200, {"status": "ok"})
            status, payload = read_json(f"{base_url}/version")
            assert status == 200 and payload["fixture"] is True
            assert payload["version"] == version and payload["instance"]
            assert read_json(f"{base_url}/holds") == (404, {"error": "not_found"})
            print("PASS: fixture startup, /healthz, /version, and unknown route")
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
