import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access_log import AccessLogMiddleware, coarse_query, visitor_id


def make_client(salt="test-salt"):
    app = FastAPI()

    @app.get("/api/route")
    def route():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.add_middleware(AccessLogMiddleware, salt=salt)
    return TestClient(app)


def records(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "app.access"]


def capture(caplog):
    logger = logging.getLogger("app.access")
    logger.addHandler(caplog.handler)
    return logger


def test_logs_hashed_visitor_and_rounded_coordinates(caplog):
    logger = capture(caplog)
    try:
        make_client().get(
            "/api/route?from_lat=36.62579030907297&from_lon=127.46038101502052&mode=heat",
            headers={"CF-Connecting-IP": "203.0.113.7", "User-Agent": "okhttp/4.12.0"},
        )
    finally:
        logger.removeHandler(caplog.handler)
    (record,) = records(caplog)
    assert record["visitor"] == visitor_id("203.0.113.7", "test-salt")
    assert "203.0.113.7" not in json.dumps(record)
    assert record["query"] == {"from_lat": "36.626", "from_lon": "127.460", "mode": "heat"}
    assert record["status"] == 200
    assert record["ua"] == "okhttp/4.12.0"


def test_same_ip_same_visitor_and_health_is_skipped(caplog):
    logger = capture(caplog)
    try:
        client = make_client()
        for ip in ("198.51.100.1", "198.51.100.1", "198.51.100.2"):
            client.get("/api/route", headers={"CF-Connecting-IP": ip})
        client.get("/health")
    finally:
        logger.removeHandler(caplog.handler)
    visitors = [r["visitor"] for r in records(caplog)]
    assert len(visitors) == 3
    assert visitors[0] == visitors[1] != visitors[2]


def test_salt_changes_the_id():
    assert visitor_id("198.51.100.1", "a") != visitor_id("198.51.100.1", "b")


def test_bad_coordinate_is_masked():
    assert coarse_query("lat=abc&lon=127.1234567") == {"lat": "?", "lon": "127.123"}
