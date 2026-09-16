"""Эталон code_agent a2a: listen GUEST_LISTEN_PORT, POST /invoke."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _listen_port() -> int:
    raw = os.environ.get("GUEST_LISTEN_PORT")
    if raw is None or raw.strip() == "":
        raise RuntimeError("GUEST_LISTEN_PORT is required")
    port = int(raw)
    if port < 1 or port > 65535:
        raise RuntimeError(f"GUEST_LISTEN_PORT is invalid: {raw}")
    return port


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        _ = format, args

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/invoke":
            self.send_error(404)
            return
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self.send_error(400, "Content-Length required")
            return
        raw = self.rfile.read(int(length_header))
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            self.send_error(400, "JSON object required")
            return
        text = parsed.get("text")
        if not isinstance(text, str):
            self.send_error(400, "text required")
            return
        body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = _listen_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
