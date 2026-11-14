"""Process health and version fixture for W1-TV2 infrastructure smoke checks."""

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.partition("?")[0]
        if path == "/healthz":
            self.send_json(200, {"status": "ok"})
        elif path == "/version":
            self.send_json(
                200,
                {
                    "fixture": True,
                    "version": os.environ.get("APP_VERSION", "fixture-v1"),
                    "instance": socket.gethostname(),
                },
            )
        else:
            self.send_json(404, {"error": "not_found"})

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code="-", size="-"):
        self.log_message("HTTP %s %s", self.command, code)


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    with ThreadingHTTPServer((host, port), FixtureHandler) as server:
        print(f"TV2 fixture listening on {host}:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
