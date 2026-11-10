"""One JSON line per request, without the visitor's IP or exact position.

The API sits behind a Cloudflare tunnel and Docker, so the socket address is
always the Docker gateway. The real address arrives in ``CF-Connecting-IP``;
it is never written out, only a salted hash of it, which is enough to count
visitors and tell sessions apart. Coordinates in the query (``*_lat``,
``*_lon``, ``lat``, ``lon``) are rounded to 3 decimals, about 100 m.

Set ``VISITOR_HASH_SALT`` to keep visitor ids stable across restarts; without
it a random salt is drawn at start-up and ids change on every restart.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import logging
import secrets
import time
from urllib.parse import parse_qsl

from app.services.solar import SEOUL_TZ

logger = logging.getLogger("app.access")
SKIP_PATHS = {"/health"}
COORD_DECIMALS = 3


def _configure_logger() -> None:
    # uvicorn only configures its own loggers; give ours a plain stdout handler.
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(getattr(h, "_access_log", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._access_log = True
        logger.addHandler(handler)


def visitor_id(ip: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:12]


def is_coordinate(key: str) -> bool:
    return key in ("lat", "lon") or key.endswith(("_lat", "_lon"))


def coarse_query(query_string: str) -> dict[str, str]:
    params = {}
    for key, value in parse_qsl(query_string, keep_blank_values=True):
        if is_coordinate(key):
            try:
                value = f"{float(value):.{COORD_DECIMALS}f}"
            except ValueError:
                value = "?"
        params[key] = value
    return params


def client_ip(scope) -> str:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    if headers.get("cf-connecting-ip"):
        return headers["cf-connecting-ip"].strip()
    if headers.get("x-forwarded-for"):
        return headers["x-forwarded-for"].split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


def user_agent(scope) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == b"user-agent":
            # "okhttp/4.12.0" for the app, the browser's product token otherwise.
            return value.decode("latin-1").split(" ")[0][:40]
    return ""


class AccessLogMiddleware:
    def __init__(self, app, salt: str | None = None):
        self.app = app
        self.salt = salt or secrets.token_hex(16)
        _configure_logger()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in SKIP_PATHS:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            record = {
                "t": datetime.now(SEOUL_TZ).isoformat(timespec="seconds"),
                "visitor": visitor_id(client_ip(scope), self.salt),
                "method": scope["method"],
                "path": scope["path"],
                "query": coarse_query(scope.get("query_string", b"").decode("latin-1")),
                "status": status["code"],
                "ms": round((time.perf_counter() - started) * 1000),
                "ua": user_agent(scope),
            }
            logger.info(json.dumps(record, ensure_ascii=False))
