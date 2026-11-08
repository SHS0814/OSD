from datetime import datetime

import numpy as np
import pytest
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


def test_sensor_sites_are_geojson_points() -> None:
    with TestClient(app) as client:
        response = client.get("/api/sensors")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"]
    for feature in payload["features"]:
        assert feature["geometry"]["type"] == "Point"
        lon, lat = feature["geometry"]["coordinates"]
        assert 127.44 < lon < 127.47 and 36.62 < lat < 36.64
        assert feature["properties"]["sensor"] == feature["id"]


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
    # Cells under buildings are filled for display but kept out of the summary.
    assert summary["cell_count"] < sum(value is not None for value in payload["utci"])
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


def test_summer_route_offers_a_shadier_alternative() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/route",
            params={
                "from_lat": 36.630931, "from_lon": 127.454222,
                "to_lat": 36.626035, "to_lon": 127.456245,
                "datetime": "2026-08-07T15:00:00+09:00",
            },
        )
    assert response.status_code == 200
    routes = response.json()["routes"]["features"]
    assert routes[0]["properties"]["kind"] == "shortest"
    assert len(routes) >= 2
    assert response.json()["mode"] == "heat"
    assert {route["properties"]["mode"] for route in routes} == {"heat"}
    shortest, other = routes[0]["properties"], routes[-1]["properties"]
    assert other["sun_share"] < shortest["sun_share"]
    assert other["length_m"] <= shortest["length_m"] * 1.3 + 1


# 2026-01-13 13:00: clear (cloud 2/10, a full hour of sunshine), 1.7 °C, wind 3.1 m/s from 290°.
WINTER_NOON = "2026-01-13T13:00:00+09:00"


def test_winter_route_offers_a_sunnier_alternative() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/route",
            params={
                "from_lat": 36.630931, "from_lon": 127.454222,
                "to_lat": 36.626035, "to_lon": 127.456245,
                "datetime": WINTER_NOON,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "cold"
    routes = payload["routes"]["features"]
    assert routes[0]["properties"]["kind"] == "shortest"
    assert len(routes) >= 2
    shortest, other = routes[0]["properties"], routes[-1]["properties"]
    assert other["mode"] == "cold"
    assert other["sun_share"] > shortest["sun_share"]
    assert other["mean_utci"] > shortest["mean_utci"]
    assert other["cold_minutes"] <= shortest["cold_minutes"]
    assert other["length_m"] <= shortest["length_m"] * 1.3 + 1


def test_night_route_is_only_the_shortest() -> None:
    with TestClient(app) as client:
        payload = client.get(
            "/api/route",
            params={
                "from_lat": 36.630931, "from_lon": 127.454222,
                "to_lat": 36.626035, "to_lon": 127.456245,
                "datetime": "2026-01-13T22:00:00+09:00",
            },
        ).json()
    assert payload["mode"] == "none"
    assert [route["properties"]["kind"] for route in payload["routes"]["features"]] == ["shortest"]


def test_microclimate_uses_the_per_cell_wind() -> None:
    from app.services.solar import calculate_solar_position, parse_requested_datetime

    with TestClient(app) as client:
        payload = client.get("/api/microclimate", params={"datetime": WINTER_NOON}).json()
        assert payload["inputs"]["wind_field"] is True
        assert payload["weather"]["wind_direction_deg"] == 290.0
        model = app.state.microclimate
        when = parse_requested_datetime(datetime.fromisoformat(WINTER_NOON), None, None)
        weather = app.state.weather.at(when)
        solar = calculate_solar_position(when, 36.6282, 127.4567)
        uniform = model.fields(when, solar, weather).utci
        per_cell = model.fields(when, solar, weather, wind_direction_deg=290.0).utci
    # Sheltered wind on a cold day feels warmer than the open-site ASOS wind.
    valid = np.isfinite(uniform) & np.isfinite(per_cell)
    assert np.all(per_cell[valid] >= uniform[valid] - 1e-6)
    assert np.mean(per_cell[valid] - uniform[valid]) > 0.5
    assert payload["summary"]["utci_mean"] == pytest.approx(float(np.nanmean(per_cell)), abs=0.1)


def test_wind_points_for_drawing_arrows() -> None:
    with TestClient(app) as client:
        response = client.get("/api/wind", params={"datetime": WINTER_NOON})
        dense = client.get("/api/wind", params={"datetime": WINTER_NOON, "step_m": 12}).json()
        too_dense = client.get("/api/wind", params={"datetime": WINTER_NOON, "step_m": 4})
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["wind"] == {"asos_speed_ms": 3.1, "direction_deg": 290.0, "wind_field": True}
    points = payload["features"]
    assert points
    assert len(dense["features"]) > 3 * len(points)
    for point in points:
        lon, lat = point["geometry"]["coordinates"]
        assert 127.44 < lon < 127.47 and 36.62 < lat < 36.64
        props = point["properties"]
        assert 0 < props["factor"] <= 1
        assert props["speed_ms"] <= payload["wind"]["asos_speed_ms"]
        assert props["direction_deg"] == 290.0
    assert too_dense.status_code == 422


def test_calm_wind_has_no_arrows() -> None:
    with TestClient(app) as client:
        payload = client.get("/api/wind", params={"datetime": "2026-01-15T11:00:00+09:00"}).json()
    assert payload["wind"]["direction_deg"] is None  # ASOS: ws 0.1, wd 0
    assert payload["wind"]["wind_field"] is True
    assert payload["features"] == []


def test_wind_outside_the_snapshot_is_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/wind", params={"datetime": "2030-01-01T12:00:00+09:00"})
    assert response.status_code == 404


def test_route_from_off_campus_is_refused() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/route",
            params={"from_lat": 37.5665, "from_lon": 126.978, "to_lat": 36.626, "to_lon": 127.456,
                    "datetime": "2026-08-07T15:00:00+09:00"},
        )
    assert response.status_code == 422


def test_weather_for_an_observed_instant() -> None:
    with TestClient(app) as client:
        payload = client.get("/api/weather", params={"datetime": "2026-08-07T15:00:00+09:00"}).json()
    assert payload["latest"] is False
    assert payload["weather"]["station"] == "청주 ASOS (131)"
    assert payload["solar"]["altitude"] > 0


def test_weather_now_falls_back_to_the_latest_observation() -> None:
    with TestClient(app) as client:
        period = client.get("/api/weather/period").json()
        payload = client.get("/api/weather").json()
    # The committed snapshot ends before today, so without an API허브 key "now" is the latest hour.
    if payload["latest"]:
        assert payload["datetime"] == period["latest_observation"]


def test_weather_outside_the_snapshot_is_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/weather", params={"datetime": "2020-01-01T12:00:00+09:00"})
    assert response.status_code == 404
