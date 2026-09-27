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


def test_microclimate_grid_for_a_summer_noon() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/microclimate", params={"datetime": "2025-08-05T12:00:00+09:00"}
        )
    assert response.status_code == 200
    payload = response.json()
    grid = payload["grid"]
    assert len(payload["utci"]) == grid["rows"] * grid["cols"]
    assert len(payload["mrt"]) == len(payload["sunlit"]) == len(payload["utci"])
    assert len(grid["corners_wgs84"]) == 4
    assert payload["weather"]["air_temp_c"] == 31.8
    summary = payload["summary"]
    assert summary["cell_count"] == sum(value is not None for value in payload["utci"])
    # Shaded cells must come out cooler than sunlit ones.
    assert summary["utci_max"] - summary["utci_min"] > 3
    assert 0 < summary["sunlit_share"] < 1


def test_microclimate_has_no_sun_at_night() -> None:
    with TestClient(app) as client:
        payload = client.get(
            "/api/microclimate", params={"datetime": "2025-08-05T22:00:00+09:00"}
        ).json()
    assert payload["solar"]["altitude"] < 0
    assert payload["summary"]["sunlit_share"] == 0
    assert payload["irradiance"]["direct_normal_wm2"] == 0


def test_microclimate_outside_weather_snapshot_is_404() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/microclimate", params={"datetime": "2030-01-01T12:00:00+09:00"}
        )
    assert response.status_code == 404


def test_weather_period_names_the_latest_full_date() -> None:
    with TestClient(app) as client:
        payload = client.get("/api/weather/period").json()
    assert payload["start"].startswith("2025-06-01T00:00")
    assert payload["latest_full_date"] == payload["end"][:10]
