"""VWorld aerial photo tiles for the app's satellite base map, passed through the API.

The app asks this server rather than VWorld so the VWorld key stays on the
server. Tiles are cached on disk (the same folder scripts/build_tree_canopy.py
fills), and only the campus area is served, so the endpoint cannot be used to
pull imagery for anywhere else through this key.
"""

from __future__ import annotations

import math
import ssl
import urllib.request
from pathlib import Path

import certifi

ENDPOINT = "https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{z}/{y}/{x}.jpeg"
MIN_ZOOM = 10
MAX_ZOOM = 19  # VWorld's finest Satellite level, ~0.24 m per pixel here
# Served area: campus with a margin for panning around it (WGS84).
AREA = (127.43, 36.61, 127.49, 36.645)  # west, south, east, north

_TLS = ssl.create_default_context(cafile=certifi.where())


class TileUnavailable(LookupError):
    pass


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) of a Web Mercator tile."""
    n = 2**z

    def lat(row: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / n))))

    return x / n * 360.0 - 180.0, lat(y + 1), (x + 1) / n * 360.0 - 180.0, lat(y)


def in_area(z: int, x: int, y: int) -> bool:
    if not MIN_ZOOM <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        return False
    west, south, east, north = tile_bounds(z, x, y)
    area_west, area_south, area_east, area_north = AREA
    return west < area_east and east > area_west and south < area_north and north > area_south


def get_tile(key: str | None, referer: str, cache_dir: Path, z: int, x: int, y: int) -> bytes:
    if not in_area(z, x, y):
        raise TileUnavailable(f"tile {z}/{x}/{y} is outside the campus area")
    path = cache_dir / str(z) / str(y) / f"{x}.jpeg"
    if path.exists():
        return path.read_bytes()
    if not key:
        raise TileUnavailable("VWORLD_API_KEY is not set")
    request = urllib.request.Request(ENDPOINT.format(key=key, z=z, y=y, x=x), headers={"Referer": referer})
    with urllib.request.urlopen(request, timeout=20, context=_TLS) as response:
        data = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
