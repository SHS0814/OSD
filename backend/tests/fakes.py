"""Stand-ins for the other half of the model, so each side's tests run on their own.

The comfort and wind code (atmosphere side) only ever sees the space side
through contracts.py; these build those contracts directly, without the ray
tracer or any campus data:

- ``sunny_geometry``: GeometryFields with the same sun, sky and ground in every cell;
- ``square_obstacles``: an ObstacleRaster of a square campus with square
  buildings and crowns;
- ``fixed_weather``: a WeatherSample of a clear, hot afternoon.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.services.contracts import GeometryFields, ObstacleRaster, WeatherSample
from app.services.grid import CELL_M, FINE_M, MAX_BUILDING_SHARE, SUBCELLS, GridSpec
from app.services.solar import SEOUL_TZ

# A campus-sized square (EPSG:5179 metres); positions below are from its centre.
CAMPUS_M = 300.0
ORIGIN = (950_000.0, 1_850_000.0)  # west, south: about where 청주 is
BROADLEAF_TAU = (0.2, 0.6)  # (leaf on, leaf off) transmissivity of a broadleaf crown


def square_grid(size_m: float = CAMPUS_M) -> GridSpec:
    west, south = ORIGIN
    return GridSpec.covering((west, south, west + size_m, south + size_m))


def sunny_geometry(
    grid: GridSpec | None = None,
    *,
    sunlit: float = 1.0,
    sky_view: float = 1.0,
    albedo: float = 0.12,
    heating: float = 0.020,
) -> GeometryFields:
    """The same open, sunny paved ground everywhere (no shade, full sky)."""
    grid = grid or square_grid()
    shape = (grid.rows, grid.cols)
    return GeometryFields(
        valid=np.ones(shape, dtype=bool),
        sunlit=np.full(shape, sunlit),
        sky_view=np.full(shape, sky_view),
        albedo=np.full(shape, albedo),
        heating=np.full(shape, heating),
    )


def square_obstacles(
    buildings: tuple[tuple[float, float, float, float], ...] = (),
    crowns: tuple[tuple[float, float, float, float], ...] = (),
    size_m: float = CAMPUS_M,
) -> ObstacleRaster:
    """Square buildings and crowns, each (x, y, half width, height) in metres
    from the campus centre; every crown is a broadleaf one (BROADLEAF_TAU)."""
    grid = square_grid(size_m)
    fine_west, fine_north = grid.fine_origin
    rows, cols = grid.fine_shape
    x = fine_west + (np.arange(cols) + 0.5) * FINE_M
    y = fine_north - (np.arange(rows) + 0.5) * FINE_M
    x, y = np.meshgrid(x, y)
    centre_x, centre_y = ORIGIN[0] + size_m / 2, ORIGIN[1] + size_m / 2

    def square(cx: float, cy: float, half: float) -> np.ndarray:
        return (np.abs(x - centre_x - cx) < half) & (np.abs(y - centre_y - cy) < half)

    footprint = np.zeros(x.shape, dtype=bool)
    building_height = np.zeros(x.shape)
    for cx, cy, half, height in buildings:
        inside = square(cx, cy, half)
        footprint |= inside
        building_height = np.where(inside, np.maximum(building_height, height), building_height)
    crown_height = np.zeros(x.shape)
    for cx, cy, half, height in crowns:
        inside = square(cx, cy, half) & ~footprint
        crown_height = np.where(inside, np.maximum(crown_height, height), crown_height)
    crown_kind = np.where(crown_height > 0, 0, -1)

    share = footprint[grid.window].reshape(grid.rows, SUBCELLS, grid.cols, SUBCELLS).mean(axis=(1, 3))
    inside = np.ones((grid.rows, grid.cols), dtype=bool)
    return ObstacleRaster(
        grid=grid,
        inside=inside,
        valid=inside & (share < MAX_BUILDING_SHARE),
        footprint=footprint,
        building_height=building_height,
        crown_height=crown_height,
        crown_kind=crown_kind,
        transmissivity_leaf_on=(BROADLEAF_TAU[0],),
        transmissivity_leaf_off=(BROADLEAF_TAU[1],),
    )


def cell_of(raster: ObstacleRaster, x: float, y: float, size_m: float = CAMPUS_M) -> tuple[int, int]:
    """Output cell (row, col) of a point (x, y) metres from the campus centre."""
    grid = raster.grid
    col = int((ORIGIN[0] + size_m / 2 + x - grid.origin_x) / CELL_M)
    row = int((grid.origin_y - (ORIGIN[1] + size_m / 2 + y)) / CELL_M)
    return row, col


def fixed_weather(**changes) -> WeatherSample:
    """청주 on a clear August afternoon; any field can be changed."""
    when = datetime(2025, 8, 5, 14, tzinfo=SEOUL_TZ)
    values = dict(
        when=when, observed_at=when, persisted=False, air_temp_c=33.0, relative_humidity=50.0,
        dew_point_c=21.4, vapour_hpa=25.0, wind_ms=2.0, cloud_fraction=0.1,
        clearness_index=0.7, global_horizontal=800.0, hour_mean_global_horizontal=800.0,
    )
    values.update(changes)
    return WeatherSample(**values)
