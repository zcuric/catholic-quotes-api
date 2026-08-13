"""Read-only Vercel Python API for the international quote snapshot.

This function deliberately opens only ``vercel_app/data/international.sqlite3``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "international.sqlite3"
MAX_LIMIT = 100
CATENA_EXCERPT_LIMIT = 560
ROUTES = {"health", "sources", "saints", "quotes", "random", "docs"}
HTML_PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/docs": "docs.html",
    "/docs.html": "docs.html",
}
BINARY_ASSETS = {
    "/support-qr.png": ("assets/buy-me-a-coffee-qr.png", "image/png"),
    "/robert-arrington-catholic-interior.jpg": ("assets/robert-arrington-catholic-interior.jpg", "image/jpeg"),
    "/favicon.svg": ("assets/favicon.svg", "image/svg+xml"),
}
SENTENCE_BREAK = re.compile(r'(?<=[.!?])\s+(?=(?:[A-Z“"\']))')
ANSWER_START = re.compile(r"\bI answer that\b", re.IGNORECASE)
NON_QUOTE_OPENING = re.compile(r"^(?:objection|reply to objection|reply|on the contrary)\b", re.IGNORECASE)
SENTENCE_OPENING = re.compile(r"^(?:[“\"']?[A-Z]|\([A-Z])")


def connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"database not bundled: {DB_PATH}")
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = 1")
    return connection


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def source_object(row: sqlite3.Row) -> dict:
    return {
        "domain": row["source_domain"],
        "url": row["source_url"],
    }


def concise_catena_excerpt(raw_text: str) -> str:
    """Return a complete-sentence excerpt while preserving the cited source unit.

    Some Catena rows are whole articles rather than short passages. For those,
    prefer Aquinas's ``I answer that`` section, then return one or more complete
    sentences within the display limit. The full source unit remains available
    with ``full=1``.
    """
    text = " ".join(raw_text.split())
    if len(text) <= CATENA_EXCERPT_LIMIT:
        return text

    answer = ANSWER_START.search(text)
    preferred_start = answer is not None
    if answer:
        text = text[answer.start():]

    sentences = [sentence.strip() for sentence in SENTENCE_BREAK.split(text) if sentence.strip()]
    if not sentences:
        return text[: CATENA_EXCERPT_LIMIT - 1].rstrip() + "…"

    if preferred_start:
        start_index = 0
    else:
        start_index = next(
            (
                index
                for index, sentence in enumerate(sentences)
                if len(sentence) >= 80
                and SENTENCE_OPENING.match(sentence)
                and not NON_QUOTE_OPENING.match(sentence)
            ),
            0,
        )

    selected: list[str] = []
    for sentence in sentences[start_index:]:
        proposed = " ".join([*selected, sentence])
        if len(proposed) > CATENA_EXCERPT_LIMIT:
            if not selected:
                boundary = sentence.rfind(" ", 0, CATENA_EXCERPT_LIMIT - 1)
                return sentence[: boundary if boundary > 100 else CATENA_EXCERPT_LIMIT - 1].rstrip(" ,;:") + "…"
            break
        selected.append(sentence)
    return " ".join(selected) if selected else text[: CATENA_EXCERPT_LIMIT - 1].rstrip() + "…"


def wants_full_text(params: dict[str, list[str]]) -> bool:
    return params.get("full", [""])[0].strip().lower() in {"1", "true", "yes"}


def quote_object(row: sqlite3.Row, full_text: bool = False) -> dict:
    text = row["text"]
    is_excerpt = False
    if row["dataset"] == "catena" and not full_text:
        text = concise_catena_excerpt(text)
        is_excerpt = text != row["text"]
    return {
        "id": row["id"],
        "dataset": row["dataset"],
        "text": text,
        "language": row["language"],
        "author": row["author"],
        "collection": row["collection"],
        "source_category": row["source_category"],
        "citation": row["citation"],
        "title": row["title"],
        "work": row["work"],
        "source": source_object(row),
        "license_note": row["license_note"],
        "quote_type": row["quote_type"],
        "is_excerpt": is_excerpt,
    }


def parse_int(params: dict[str, list[str]], key: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(params.get(key, [str(default)])[0])
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    return max(value, minimum)


def search_terms(value: str) -> list[str]:
    # Keep search independent of optional SQLite extensions.  The snapshot is
    # only 6,203 records, so a bounded AND-of-LIKE query is fast and works on
    # the standard Vercel Python runtime as well as local SQLite builds.
    return re.findall(r"[\wÀ-ž]{2,}", value, flags=re.UNICODE)[:8]


def route_from(path: str, params: dict[str, list[str]]) -> str:
    explicit = params.get("route", [""])[0].strip().lower()
    if explicit in ROUTES:
        return explicit
    pieces = [piece for piece in urlparse(path).path.split("/") if piece]
    if pieces and pieces[-1].removesuffix(".py") in ROUTES:
        return pieces[-1].removesuffix(".py")
    return "health" if not pieces or pieces[-1] in {"api", "index.py"} else ""


def handle(route: str, params: dict[str, list[str]]) -> dict:
    if route == "docs":
        return {
            "name": "Catholic Quotes API",
            "language": "en",
            "sources": ["wikiquote", "catena"],
            "endpoints": {
                "/api/health": "status and record counts",
                "/api/sources": "source and license metadata",
                "/api/saints": "Wikiquote authors",
                "/api/quotes": "paginated search",
                "/api/random": "one random record",
            },
            "query_parameters": {
                "source": "wikiquote (default), catena, or all",
                "q": "full-text search",
                "author": "Wikiquote author filter",
                "collection": "Catena collection filter",
                "full": "set to 1, true, or yes to return full Catena source units",
                "limit": "1-100, default 25",
                "offset": "zero-based, default 0",
            },
        }

    connection = connect()
    try:
        if route == "health":
            counts = {
                row["dataset"]: row["count"]
                for row in connection.execute("SELECT dataset, COUNT(*) AS count FROM quotes GROUP BY dataset")
            }
            return {
                "ok": True,
                "language": "en",
                "record_count": sum(counts.values()),
                "datasets": counts,
            }

        if route == "sources":
            rows = connection.execute(
                "SELECT id, label, description, license_note FROM sources WHERE id != 'meta' ORDER BY id"
            ).fetchall()
            return {"sources": [dict(row) for row in rows]}

        if route == "saints":
            rows = connection.execute(
                """
                SELECT author, COUNT(*) AS quote_count
                FROM quotes
                WHERE dataset = 'wikiquote' AND author IS NOT NULL AND author != ''
                GROUP BY author ORDER BY lower(author)
                """
            ).fetchall()
            return {"count": len(rows), "authors": [dict(row) for row in rows]}

        source = params.get("source", ["wikiquote"])[0].strip().lower()
        if source not in {"all", "wikiquote", "catena"}:
            raise ValueError("source must be all, wikiquote, or catena")
        limit = min(parse_int(params, "limit", 25, 1), MAX_LIMIT)
        offset = parse_int(params, "offset", 0)
        conditions: list[str] = []
        values: list[object] = []
        if source != "all":
            conditions.append("q.dataset = ?")
            values.append(source)
        full_text = wants_full_text(params)
        query = params.get("q", [""])[0].strip()
        if query:
            for term in search_terms(query):
                conditions.append(
                    "(lower(q.text) LIKE lower(?) OR lower(coalesce(q.author, '')) LIKE lower(?) "
                    "OR lower(coalesce(q.collection, '')) LIKE lower(?) OR lower(coalesce(q.citation, '')) LIKE lower(?))"
                )
                pattern = f"%{term}%"
                values.extend([pattern, pattern, pattern, pattern])
        author = params.get("author", [""])[0].strip()
        if author:
            conditions.append("lower(q.author) LIKE lower(?)")
            values.append(f"%{author}%")
        collection = params.get("collection", [""])[0].strip()
        if collection:
            conditions.append("lower(q.collection) LIKE lower(?)")
            values.append(f"%{collection}%")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = connection.execute(f"SELECT COUNT(*) FROM quotes q {where}", values).fetchone()[0]
        if route == "random":
            rows = connection.execute(
                f"SELECT q.* FROM quotes q {where} ORDER BY RANDOM() LIMIT 1", values
            ).fetchall()
            return {"source": source, "count": total, "item": quote_object(rows[0], full_text) if rows else None}
        if route != "quotes":
            raise ValueError("unknown route")
        rows = connection.execute(
            f"SELECT q.* FROM quotes q {where} ORDER BY q.dataset, q.author COLLATE NOCASE, q.rowid LIMIT ? OFFSET ?",
            [*values, limit, offset],
        ).fetchall()
        return {
            "source": source,
            "language": "en",
            "count": total,
            "limit": limit,
            "offset": offset,
            "items": [quote_object(row, full_text) for row in rows],
        }
    finally:
        connection.close()


class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime discovers this handler class automatically."""

    def _send_html(self, page_name: str) -> None:
        body = (BASE_DIR / page_name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _send_asset(self, asset_name: str, content_type: str) -> None:
        body = (BASE_DIR / asset_name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(body)

    def _send(self, payload: object, status: int = 200) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "public, s-maxage=300, stale-while-revalidate=86400")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib API
        self._send({}, 204)

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        parsed = urlparse(self.path)
        page_name = HTML_PAGES.get(parsed.path)
        if page_name:
            self._send_html(page_name)
            return
        asset = BINARY_ASSETS.get(parsed.path)
        if asset:
            self._send_asset(*asset)
            return
        params = parse_qs(parsed.query)
        route = route_from(self.path, params)
        if not route:
            self._send({"error": "not found", "docs": "/api/docs"}, 404)
            return
        try:
            self._send(handle(route, params))
        except ValueError as exc:
            self._send({"error": str(exc)}, 400)
        except Exception as exc:  # keep the public response JSON-shaped
            self._send({"error": "internal server error", "detail": str(exc)}, 500)

    def log_message(self, format: str, *args) -> None:
        return
