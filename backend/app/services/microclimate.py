"""Campus-wide thermal comfort (UTCI) on a regular grid - model v1.

This joins the two halves of the model and keeps nothing of its own:

- ``GeometryField`` (geometry_field.py, space side) traces the sun through
  terrain, buildings and crowns and gives each output cell its sunlit
  fraction, sky view factor and ground albedo and heating;
- ``comfort_fields`` (comfort.py, atmosphere side) turns those and the 청주
  ASOS weather of the hour into the mean radiant temperature and UTCI.

The wind is the ASOS speed everywhere unless a WindField (wind.py: shelter
behind obstacles plus a 2D mass-consistent flow round the buildings, built
from ``obstacles``) is attached as ``wind_field`` and the wind direction is
passed to ``fields``.
"""

from __future__ import annotations

import math
import threading
from datetime import datetime

import numpy as np
from shapely.geometry.base import BaseGeometry

from .comfort import Fields, comfort_fields, summary
from .contracts import ObstacleRaster, WeatherSample
from .geometry_field import GeometryField
from .grid import CELL_M, GridSpec
from .common import in_leaf
from .solar import SolarPosition
from .surfaces import CanopyPatch, GroundPatch
from .terrain import Terrain

__all__ = ["CELL_M", "Fields", "GridSpec", "MODEL_VERSION", "MicroclimateModel"]

MODEL_VERSION = "v1"

# Instants whose per-cell results are kept (heatmap and routes share them).
FIELDS_CACHE_SIZE = 8


class MicroclimateModel:
    def __init__(
        self,
        campus_boundary: BaseGeometry,
        buildings: list,
        terrain: Terrain | None = None,
        ground: list[GroundPatch] | None = None,
        canopies: list[CanopyPatch] | None = None,
    ):
        # Builds the surface model and the sky view factor once; per request
        # only the sun rays and the radiation are computed.
        self.geometry = GeometryField(campus_boundary, buildings, terrain=terrain, ground=ground, canopies=canopies)
        # Optional per-cell wind (services/wind.WindField); None keeps ASOS wind everywhere.
        self.wind_field = None
        self._fields_cache: dict = {}
        self._fields_lock = threading.Lock()

    @property
    def grid(self) -> GridSpec:
        return self.geometry.grid

    @property
    def valid(self) -> np.ndarray:
        """Output cells inside campus and mostly open ground."""
        return self.geometry.valid

    @property
    def inside(self) -> np.ndarray:
        return self.geometry.inside

    @property
    def obstacles(self) -> ObstacleRaster:
        """What a WindField is built from."""
        return self.geometry.obstacles

    def fill_under_buildings(self, values: np.ndarray) -> np.ndarray:
        return self.geometry.fill_under_buildings(values)

    def fields(
        self,
        when: datetime,
        solar: SolarPosition,
        weather: WeatherSample,
        wind_direction_deg: float | None = None,
    ) -> Fields:
        """Per-cell results for one instant; cached, since the heatmap and a
        route asked for the same instant would otherwise trace the sun twice.

        With ``wind_field`` attached and a wind direction (ASOS wd, degrees the
        wind comes from) given, the wind varies by cell; otherwise it is the
        ASOS speed everywhere."""
        per_cell_wind = self.wind_field is not None and wind_direction_deg is not None
        cache_key = (when, solar.altitude, solar.azimuth, weather,
                     (id(self.wind_field), wind_direction_deg) if per_cell_wind else None)
        with self._fields_lock:
            cached = self._fields_cache.get(cache_key)
        if cached is not None:
            return cached
        day = when.date()
        geometry = self.geometry.at(solar, day)
        wind = self.wind_field.wind_ms(weather.wind_ms, wind_direction_deg, day) if per_cell_wind else weather.wind_ms
        result = comfort_fields(geometry, when, solar, weather, wind)
        with self._fields_lock:
            while len(self._fields_cache) >= FIELDS_CACHE_SIZE:
                self._fields_cache.pop(next(iter(self._fields_cache)))
            self._fields_cache[cache_key] = result
        return result

    def compute(
        self,
        when: datetime,
        solar: SolarPosition,
        weather: WeatherSample,
        wind_direction_deg: float | None = None,
    ) -> dict:
        day = when.date()
        fields = self.fields(when, solar, weather, wind_direction_deg=wind_direction_deg)
        irradiance = fields.irradiance
        grid = self.grid

        return {
            "model_version": MODEL_VERSION,
            "inputs": {
                "terrain": self.geometry.has_terrain,
                "canopy_share": round(self.geometry.canopy_share(), 3),
                "in_leaf": in_leaf(day),
                # Per-cell wind is attached; at calm (no direction) it is the ASOS wind everywhere.
                "wind_field": self.wind_field is not None,
            },
            "irradiance": {
                "direct_normal_wm2": round(irradiance.direct_normal, 1),
                "diffuse_horizontal_wm2": round(irradiance.diffuse_horizontal, 1),
            },
            "grid": {
                "crs": "EPSG:5179",
                "cell_size_m": CELL_M,
                "rows": grid.rows,
                "cols": grid.cols,
                "origin": {"x": grid.origin_x, "y": grid.origin_y},
                "corners_wgs84": grid.corners_wgs84(),
                "order": "row-major from the north-west corner; null outside campus",
                "under_buildings": "filled from the surrounding open ground for display; "
                "not part of the summary",
            },
            "summary": summary(fields, self.valid),
            "utci": _rounded(self.fill_under_buildings(fields.utci)),
            "mrt": _rounded(self.fill_under_buildings(fields.mrt)),
            "sunlit": _rounded(self.fill_under_buildings(fields.sunlit), digits=2),
        }


def _rounded(values: np.ndarray, digits: int = 1) -> list[float | None]:
    return [None if not math.isfinite(v) else round(float(v), digits) for v in values.ravel()]
