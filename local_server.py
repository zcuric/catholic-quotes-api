#!/usr/bin/env python3
"""Serve the Vercel package locally with its API and interface together."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
from api.index import handler as ApiHandler


class LocalHandler(ApiHandler):
    """Keep the local server on the same request path as Vercel's handler."""


if __name__ == "__main__":
    address = ("127.0.0.1", 8787)
    print(f"Catholic Quotes API local app: http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, LocalHandler).serve_forever()
