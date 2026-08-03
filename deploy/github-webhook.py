#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

APP_DIR = Path("/home/inkfall/project")
PORT = int(os.environ.get("INKFALL_WEBHOOK_PORT", "9001"))
SECRET = os.environ.get("INKFALL_WEBHOOK_SECRET", "")


class Handler(BaseHTTPRequestHandler):
    server_version = "inkfall-webhook/1.0"

    def do_POST(self) -> None:
        if self.path != "/":
            self._send(404, b"not found")
            return

        event = self.headers.get("X-GitHub-Event", "")
        signature = self.headers.get("X-Hub-Signature-256", "")
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)

        if not SECRET:
            self._send(500, b"missing webhook secret")
            return

        if not signature.startswith("sha256="):
            self._send(401, b"missing signature")
            return

        expected = "sha256=" + hmac.new(SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            self._send(401, b"invalid signature")
            return

        if event != "push":
            self._send(202, b"ignored event")
            return

        try:
            subprocess.run([str(APP_DIR / "deploy" / "update.sh")], check=True)
        except subprocess.CalledProcessError:
            self._send(500, b"update failed")
            return

        self._send(200, b"ok")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send(self, status_code: int, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    httpd = HTTPServer(("127.0.0.1", PORT), Handler)
    httpd.serve_forever()
