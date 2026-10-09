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
    found = net.routes(*ends(net), utci, shade_utci=38.0, daylight=True)
    assert [route.kind for route in found] == ["shortest", "coolest"]
    assert net.length[found[0].edges].sum() == pytest.approx(100, abs=0.5)
    assert net.length[found[1].edges].sum() == pytest.approx(120, abs=0.5)


def test_detour_beyond_the_limit_is_not_offered(tmp_path) -> None:
    net = network(tmp_path, 25)  # detour 150 m: 50% longer
    utci = street_is_sunny(net, sun=44.0, shade=38.0)
    found = net.routes(*ends(net), utci, shade_utci=38.0, daylight=True)
    assert [route.kind for route in found] == ["shortest"]


def test_mild_weather_and_night_give_only_the_shortest(tmp_path) -> None:
    net = network(tmp_path, 10)
    mild = street_is_sunny(net, sun=24.0, shade=20.0)
    assert len(net.routes(*ends(net), mild, shade_utci=20.0, daylight=True)) == 1
    hot = street_is_sunny(net, sun=44.0, shade=38.0)
    assert len(net.routes(*ends(net), hot, shade_utci=38.0, daylight=False)) == 1


def test_describe_reports_sun_exposure(tmp_path) -> None:
    net = network(tmp_path, 10)
    utci = street_is_sunny(net, sun=44.0, shade=38.0)
    sunlit = street_is_sunny(net, sun=1.0, shade=0.0)
    shortest, coolest = net.routes(*ends(net), utci, shade_utci=38.0, daylight=True)
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
        net.routes(start, start, np.zeros(len(net.length)), shade_utci=20.0, daylight=True)
