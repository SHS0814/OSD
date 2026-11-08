"""Shade-aware routing on a small hand-made network where the answer is known."""

import json

import numpy as np
import pytest
from shapely.geometry import LineString

from app.services import routing
from app.services.geometry import to_projected, to_wgs84

# A 100 m straight street from A to B, and a detour of 120 m through C.
ORIGIN = to_projected(LineString([(127.4560, 36.6270), (127.4561, 36.6271)])).coords[0]


def lonlat(x: float, y: float) -> list[float]:
    point = to_wgs84(LineString([(ORIGIN[0] + x, ORIGIN[1] + y), (ORIGIN[0] + x + 1, ORIGIN[1] + y)])).coords[0]
    return [point[0], point[1]]


def network(tmp_path, detour_height: float) -> routing.WalkNetwork:
    features = [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [lonlat(0, 0), lonlat(100, 0)]}, "properties": {}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [lonlat(0, 0), lonlat(0, detour_height), lonlat(100, detour_height), lonlat(100, 0)]}, "properties": {}},
    ]
    path = tmp_path / "net.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return routing.WalkNetwork(path)


def street_is_sunny(net: routing.WalkNetwork, sun: float, shade: float) -> np.ndarray:
    on_street = np.abs(net.mid[:, 1] - ORIGIN[1]) < 0.5
    return np.where(on_street, sun, shade)


def ends(net: routing.WalkNetwork) -> tuple[int, int]:
    return net.snap(*lonlat(0, 0)), net.snap(*lonlat(100, 0))


def test_pieces_are_short_and_total_length_is_kept(tmp_path) -> None:
    net = network(tmp_path, 10)
    assert net.length.max() <= routing.SEGMENT_M + 1e-6
    assert net.length.sum() == pytest.approx(100 + 120, abs=0.5)


def test_hot_street_sends_the_cool_route_through_the_shaded_detour(tmp_path) -> None:
    net = network(tmp_path, 10)  # detour 120 m: 20% longer
    utci = street_is_sunny(net, sun=44.0, shade=38.0)
    found = net.routes(*ends(net), utci, heat_base=38.0, daylight=True)
    assert [route.kind for route in found] == ["shortest", "coolest"]
    assert net.length[found[0].edges].sum() == pytest.approx(100, abs=0.5)
    assert net.length[found[1].edges].sum() == pytest.approx(120, abs=0.5)


def test_detour_beyond_the_limit_is_not_offered(tmp_path) -> None:
    net = network(tmp_path, 25)  # detour 150 m: 50% longer
    utci = street_is_sunny(net, sun=44.0, shade=38.0)
    found = net.routes(*ends(net), utci, heat_base=38.0, daylight=True)
    assert [route.kind for route in found] == ["shortest"]


def test_mild_weather_and_night_give_only_the_shortest(tmp_path) -> None:
    net = network(tmp_path, 10)
    mild = street_is_sunny(net, sun=24.0, shade=20.0)
    assert len(net.routes(*ends(net), mild, heat_base=20.0, daylight=True)) == 1
    hot = street_is_sunny(net, sun=44.0, shade=38.0)
    assert len(net.routes(*ends(net), hot, heat_base=38.0, daylight=False)) == 1


def test_describe_reports_sun_exposure(tmp_path) -> None:
    net = network(tmp_path, 10)
    utci = street_is_sunny(net, sun=44.0, shade=38.0)
    sunlit = street_is_sunny(net, sun=1.0, shade=0.0)
    shortest, coolest = net.routes(*ends(net), utci, heat_base=38.0, daylight=True)
    hot = net.describe(shortest, utci, sunlit, shortest_m=100)["properties"]
    cool = net.describe(coolest, utci, sunlit, shortest_m=100)["properties"]
    assert hot["sun_share"] == pytest.approx(1.0) and cool["sun_share"] == pytest.approx(0.0)
    assert cool["extra_m"] == pytest.approx(20, abs=0.5)
    assert hot["sun_minutes"] == pytest.approx(100 / routing.WALK_SPEED_MS / 60, abs=0.05)
    assert cool["mean_utci"] == pytest.approx(38.0)


def test_far_points_and_same_place_are_refused(tmp_path) -> None:
    net = network(tmp_path, 10)
    with pytest.raises(routing.RouteUnavailable):
        net.snap(*lonlat(0, 500))
    start = net.snap(*lonlat(0, 0))
    with pytest.raises(routing.RouteUnavailable):
        net.routes(start, start, np.zeros(len(net.length)), heat_base=20.0, daylight=True)


def test_cold_street_sends_the_sun_route_through_the_sunny_detour(tmp_path) -> None:
    net = network(tmp_path, 10)
    # Winter noon: the street is in the shade of a wall, the detour in the sun.
    utci = street_is_sunny(net, sun=-4.0, shade=4.0)
    found = net.routes(*ends(net), utci, heat_base=-4.0, cold_base=4.0, daylight=True)
    assert [route.kind for route in found] == ["shortest", "coolest"]
    assert {route.mode for route in found} == {"cold"}
    assert net.length[found[1].edges].sum() == pytest.approx(120, abs=0.5)
    props = net.describe(found[0], utci, street_is_sunny(net, 0.0, 1.0), shortest_m=100)["properties"]
    assert props["mode"] == "cold"
    assert props["cold_minutes"] == pytest.approx(100 / routing.WALK_SPEED_MS / 60, abs=0.05)


def test_cold_baseline_is_the_sunny_side_not_the_comfort_limit(tmp_path) -> None:
    net = network(tmp_path, 10)
    # Midwinter: even the sun is below 9 °C. Against 9 °C both ways are cold;
    # against the sunny side only the shaded street is penalised.
    utci = street_is_sunny(net, sun=-10.0, shade=-3.0)
    penalty, mode = routing.comfort_penalty(utci, heat_base=-10.0, cold_base=-3.0)
    assert mode == "cold"
    on_street = np.abs(net.mid[:, 1] - ORIGIN[1]) < 0.5
    assert np.all(penalty[~on_street] == 0) and np.all(penalty[on_street] > 0)
    # A warm sunny side is capped at the comfort limit.
    _, mode = routing.comfort_penalty(np.array([12.0, 15.0]), heat_base=12.0, cold_base=15.0)
    assert mode == "none"


def test_modes_for_heat_and_comfort(tmp_path) -> None:
    net = network(tmp_path, 10)
    hot = street_is_sunny(net, sun=44.0, shade=38.0)
    assert {r.mode for r in net.routes(*ends(net), hot, heat_base=38.0, cold_base=44.0, daylight=True)} == {"heat"}
    mild = street_is_sunny(net, sun=20.0, shade=14.0)
    found = net.routes(*ends(net), mild, heat_base=14.0, cold_base=20.0, daylight=True)
    assert [(r.kind, r.mode) for r in found] == [("shortest", "none")]
    cold = street_is_sunny(net, sun=-4.0, shade=4.0)
    night = net.routes(*ends(net), cold, heat_base=-4.0, cold_base=4.0, daylight=False)
    assert [(r.kind, r.mode) for r in night] == [("shortest", "none")]
