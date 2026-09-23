from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_buildings_are_geojson() -> None:
    with TestClient(app) as client:
        response = client.get("/api/buildings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 105


def test_daytime_shadows_are_geojson() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/shadows",
            params={
                "datetime": "2026-09-09T14:00:00+09:00",
                "lat": 36.6268,
                "lon": 127.4583,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["timezone"] == "Asia/Seoul"
    assert payload["solar"]["altitude"] > 0
    assert payload["shadows"]["type"] == "FeatureCollection"
    assert payload["building_count"] == 105
    assert payload["shadow_building_count"] == len(payload["shadows"]["features"])
    assert payload["eligible_building_count"] >= 64
    assert payload["eligible_building_count"] + payload["skipped_missing_height"] == 105
    properties = payload["shadows"]["features"][0]["properties"]
    assert properties["shadow_length"] > 0
    assert "solar_azimuth" in properties


def test_night_returns_empty_shadow_collection() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/shadows",
            params={
                "date": "2026-09-09",
                "time": "02:00",
                "lat": 36.6268,
                "lon": 127.4583,
            },
        )
    assert response.status_code == 200
    assert response.json()["shadows"]["features"] == []
    assert response.json()["shadow_building_count"] == 0


def test_datetime_is_required() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/shadows", params={"lat": 36.6268, "lon": 127.4583}
        )
    assert response.status_code == 422
