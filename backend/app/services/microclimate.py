"""Campus-wide thermal comfort (UTCI) on a regular grid - model v0.

v0 uses only what is known everywhere without sensors: building shadows, the
sky view factor of the building layout, and the 청주 ASOS observation for the
hour. Air temperature, humidity and wind are therefore the same in every cell;
what varies across campus is the radiation a pedestrian receives, which is
where shade matters most. Terrain, trees and land cover come in v1 and the
sensor correction of air temperature in v2 (docs/04-data-usage-plan.md).

Geometry is resolved on a fine raster (FINE_M) and reported on coarser output
cells (CELL_M), so a cell half in shadow gets a sunlit fraction of about 0.5
rather than flipping on whichever side its centre point falls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .geometry import to_projected, to_wgs84
from .shadow import building_shadows
from .solar import SolarPosition
from .thermal import (
    mean_radiant_temperature,
    relative_humidity,
    split_irradiance,
    utci,
    utci_category,
)
from .weather import WeatherSample

MODEL_VERSION = "v0"
CELL_M = 10.0
FINE_M = 2.0
SUBCELLS = int(CELL_M / FINE_M)

# Sky view factor: horizon angle searched in this many azimuths, out to this range.
SVF_DIRECTIONS = 36
SVF_RANGE_M = 200.0

# An output cell counts as open ground only if most of it is outside buildings.
MAX_BUILDING_SHARE = 0.5


@dataclass(frozen=True)
class GridSpec:
    origin_x: float  # west edge, EPSG:5179
    origin_y: float  # north edge, EPSG:5179
    rows: int
    cols: int

    def corners_wgs84(self) -> list[list[float]]:
        west, north = self.origin_x, self.origin_y
        east, south = west + self.cols * CELL_M, north - self.rows * CELL_M
        from shapely.geometry import MultiPoint

        points = to_wgs84(MultiPoint([(west, north), (east, north), (east, south), (west, south)]))
        return [[round(p.x, 7), round(p.y, 7)] for p in points.geoms]


class MicroclimateModel:
    def __init__(self, campus_boundary: BaseGeometry, buildings: list):
        self.boundary = to_projected(campus_boundary)
        self.buildings = buildings
        west, south, east, north = self.boundary.bounds
        west, south = math.floor(west / CELL_M) * CELL_M, math.floor(south / CELL_M) * CELL_M
        east, north = math.ceil(east / CELL_M) * CELL_M, math.ceil(north / CELL_M) * CELL_M
        self.grid = GridSpec(west, north, int((north - south) / CELL_M), int((east - west) / CELL_M))

        fine_rows, fine_cols = self.grid.rows * SUBCELLS, self.grid.cols * SUBCELLS
        xs = west + (np.arange(fine_cols) + 0.5) * FINE_M
        ys = north - (np.arange(fine_rows) + 0.5) * FINE_M
        self.fine_x, self.fine_y = np.meshgrid(xs, ys)

        self.heights, footprint = self._rasterize_buildings()
        building_share = self._to_cells(footprint.astype(float))
        cell_x = west + (np.arange(self.grid.cols) + 0.5) * CELL_M
        cell_y = north - (np.arange(self.grid.rows) + 0.5) * CELL_M
        self.cell_x, self.cell_y = np.meshgrid(cell_x, cell_y)
        inside = shapely.contains_xy(self.boundary, self.cell_x, self.cell_y)
        self.valid = inside & (building_share < MAX_BUILDING_SHARE)
        self.open_ground = ~footprint
        self.sky_view = np.where(self.valid, self._sky_view_factor(), np.nan)

    def _rasterize_buildings(self) -> tuple[np.ndarray, np.ndarray]:
        heights = np.zeros(self.fine_x.shape)
        footprint = np.zeros(self.fine_x.shape, dtype=bool)
        for building in self.buildings:
            polygon = to_projected(building.geometry)
            inside = shapely.contains_xy(polygon, self.fine_x, self.fine_y)
            footprint |= inside
            if building.height_m is not None:
                heights = np.where(inside, np.maximum(heights, building.height_m), heights)
        return heights, footprint

    def _to_cells(self, fine: np.ndarray) -> np.ndarray:
        rows, cols = self.grid.rows, self.grid.cols
        return fine.reshape(rows, SUBCELLS, cols, SUBCELLS).mean(axis=(1, 3))

    def _sky_view_factor(self) -> np.ndarray:
        """1 - mean(sin² horizon angle) over azimuths, seen from each cell centre at ground level."""
        rows, cols = self.valid.nonzero()
        x = self.cell_x[rows, cols]
        y = self.cell_y[rows, cols]
        fine_rows, fine_cols = self.heights.shape
        distances = np.arange(FINE_M, SVF_RANGE_M + FINE_M, FINE_M)
        sin_squared = np.zeros(x.shape)
        for azimuth in np.linspace(0, 2 * math.pi, SVF_DIRECTIONS, endpoint=False):
            dx, dy = math.sin(azimuth), math.cos(azimuth)
            steepest = np.zeros(x.shape)
            for distance in distances:
                col = ((x + dx * distance - self.grid.origin_x) / FINE_M).astype(int)
                row = ((self.grid.origin_y - (y + dy * distance)) / FINE_M).astype(int)
                inside = (row >= 0) & (row < fine_rows) & (col >= 0) & (col < fine_cols)
                height = np.zeros(x.shape)
                height[inside] = self.heights[row[inside], col[inside]]
                steepest = np.maximum(steepest, height / distance)
            sin_squared += np.sin(np.arctan(steepest)) ** 2
        result = np.full(self.valid.shape, np.nan)
        result[rows, cols] = 1.0 - sin_squared / SVF_DIRECTIONS
        return result

    def sunlit_fraction(self, solar: SolarPosition) -> np.ndarray:
        """Unshaded share of the open ground in each cell (0 at night)."""
        if solar.altitude <= 0:
            return np.where(self.valid, 0.0, np.nan)
        shadows = [polygon for _, _, polygon in building_shadows(self.buildings, solar)]
        shaded = np.zeros(self.fine_x.shape, dtype=bool)
        if shadows:
            union = unary_union(shadows)
            shapely.prepare(union)
            shaded = shapely.contains_xy(union, self.fine_x, self.fine_y)
        open_count = self._to_cells(self.open_ground.astype(float))
        lit_count = self._to_cells((self.open_ground & ~shaded).astype(float))
        with np.errstate(invalid="ignore", divide="ignore"):
            fraction = np.where(open_count > 0, lit_count / open_count, 0.0)
        return np.where(self.valid, fraction, np.nan)

    def compute(self, when: datetime, solar: SolarPosition, weather: WeatherSample) -> dict:
        sunlit = self.sunlit_fraction(solar)
        irradiance = split_irradiance(
            weather.global_horizontal, when.timetuple().tm_yday, solar.altitude
        )
        air = np.full(self.valid.shape, weather.air_temp_c)
        mrt = mean_radiant_temperature(
            air_temp_c=air,
            sunlit=np.nan_to_num(sunlit),
            sky_view=np.nan_to_num(self.sky_view, nan=1.0),
            irradiance=irradiance,
            solar_altitude_deg=solar.altitude,
            vapour_hpa=weather.vapour_hpa,
            cloud_fraction=weather.cloud_fraction,
        )
        humidity = relative_humidity(air, weather.dew_point_c)
        comfort = utci(air, mrt, weather.wind_ms, humidity)
        mrt = np.where(self.valid, mrt, np.nan)
        comfort = np.where(self.valid, comfort, np.nan)

        return {
            "model_version": MODEL_VERSION,
            "irradiance": {
                "direct_normal_wm2": round(irradiance.direct_normal, 1),
                "diffuse_horizontal_wm2": round(irradiance.diffuse_horizontal, 1),
            },
            "grid": {
                "crs": "EPSG:5179",
                "cell_size_m": CELL_M,
                "rows": self.grid.rows,
                "cols": self.grid.cols,
                "origin": {"x": self.grid.origin_x, "y": self.grid.origin_y},
                "corners_wgs84": self.grid.corners_wgs84(),
                "order": "row-major from the north-west corner; null outside campus or inside buildings",
            },
            "summary": self._summary(comfort, mrt, sunlit),
            "utci": _rounded(comfort),
            "mrt": _rounded(mrt),
            "sunlit": _rounded(sunlit, digits=2),
        }

    def _summary(self, comfort: np.ndarray, mrt: np.ndarray, sunlit: np.ndarray) -> dict:
        values = comfort[np.isfinite(comfort)]
        categories: dict[str, int] = {}
        for value in values:
            code, _ = utci_category(float(value))
            categories[code] = categories.get(code, 0) + 1
        return {
            "cell_count": int(self.valid.sum()),
            "utci_min": _round(values.min()) if values.size else None,
            "utci_mean": _round(values.mean()) if values.size else None,
            "utci_max": _round(values.max()) if values.size else None,
            "mrt_mean": _round(np.nanmean(mrt)) if values.size else None,
            "sunlit_share": _round(np.nanmean(sunlit), 3),
            "categories": categories,
        }


def _round(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def _rounded(values: np.ndarray, digits: int = 1) -> list[float | None]:
    return [None if not math.isfinite(v) else round(float(v), digits) for v in values.ravel()]
