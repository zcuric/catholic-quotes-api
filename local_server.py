#!/usr/bin/env python3
"""Serve the Vercel package locally with its API and interface together."""

from __future__ import annotations

import mimetypes
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from api.index import handler as ApiHandler


ROOT = Path(__file__).resolve().parent


class LocalHandler(ApiHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


if __name__ == "__main__":
    address = ("127.0.0.1", 8787)
    print(f"Commonplace local app: http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, LocalHandler).serve_forever()
