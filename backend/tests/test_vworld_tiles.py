"""Satellite tile pass-through: campus-only, served from cache, never online in tests."""

import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import vworld_tiles


def tile_of(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


CAMPUS = (127.4567, 36.6282)


def test_campus_tiles_are_in_the_area_and_far_ones_are_not() -> None:
    assert vworld_tiles.in_area(19, *tile_of(*CAMPUS, 19))
    assert vworld_tiles.in_area(10, *tile_of(*CAMPUS, 10))
    assert not vworld_tiles.in_area(19, *tile_of(126.9780, 37.5665, 19))  # Seoul
    assert not vworld_tiles.in_area(9, *tile_of(*CAMPUS, 9))  # coarser than served
    assert not vworld_tiles.in_area(20, *tile_of(*CAMPUS, 20))


def test_tile_bounds_contain_the_point() -> None:
    west, south, east, north = vworld_tiles.tile_bounds(17, *tile_of(*CAMPUS, 17))
    assert west <= CAMPUS[0] <= east and south <= CAMPUS[1] <= north


def test_cached_tile_is_served_without_a_key(tmp_path) -> None:
    x, y = tile_of(*CAMPUS, 18)
    path = tmp_path / "18" / str(y) / f"{x}.jpeg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"jpeg")
    assert vworld_tiles.get_tile(None, "http://localhost", tmp_path, 18, x, y) == b"jpeg"


def test_missing_tile_without_a_key_is_unavailable(tmp_path) -> None:
    with pytest.raises(vworld_tiles.TileUnavailable):
        vworld_tiles.get_tile(None, "http://localhost", tmp_path, 18, *tile_of(*CAMPUS, 18))


def test_api_refuses_tiles_outside_campus() -> None:
    x, y = tile_of(126.9780, 37.5665, 18)
    with TestClient(app) as client:
        assert client.get(f"/api/tiles/satellite/18/{x}/{y}.jpeg").status_code == 404
