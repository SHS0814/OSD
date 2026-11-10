"""What the space side and the atmosphere side hand each other.

The campus model has two halves that are built and tested apart:

- space and shade (geometry_field.py, surfaces.py, terrain.py, shadow.py):
  where the buildings, crowns and ground are, and what that does to sunlight;
- atmosphere and comfort (weather.py, thermal.py, comfort.py, wind.py): the
  weather at an instant and what a pedestrian feels in it.

They meet only through the data classes here and the grids in grid.py:

- ``GeometryFields``: sun, sky and ground per output cell at one instant
  (space -> comfort);
- ``ObstacleRaster``: buildings and crowns on the fine raster (space -> wind);
- ``WeatherSample``: the 청주 ASOS state at one instant (atmosphere -> all).

A change here is agreed by both sides; neither imports the other's modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .grid import GridSpec


@dataclass(frozen=True, eq=False)
class GeometryFields:
    """Per output cell, for one sun position and day. Arrays are [rows, cols]."""

    valid: np.ndarray  # bool: inside campus and mostly open ground
    sunlit: np.ndarray  # direct-sun share of the open ground, 0..1; NaN where not valid
    sky_view: np.ndarray  # sky view factor with crowns for the day, 0..1; NaN where not valid
    # Mean over the open ground; a cell with none (all building) has the default surface's.
    albedo: np.ndarray
    heating: np.ndarray  # ground warming, K per W/m² of sun reaching it


@dataclass(frozen=True, eq=False)
class ObstacleRaster:
    """Buildings and crowns on the fine raster (``grid.fine_shape``), for the wind.

    Heights are above the local ground. A building of unknown height is in
    ``footprint`` with ``building_height`` 0; it is up to the reader what to
    assume for it. Crowns are never under a building.
    """

    grid: GridSpec
    inside: np.ndarray  # bool [rows, cols]: output cells inside campus
    valid: np.ndarray  # bool [rows, cols]: inside campus and mostly open ground
    footprint: np.ndarray  # bool, fine: under a building
    building_height: np.ndarray  # m, fine; 0 outside footprints
    crown_height: np.ndarray  # m, fine; 0 where there is no crown
    crown_kind: np.ndarray  # int, fine: index into the transmissivities, -1 where no crown
    # Share of direct sun that gets through each kind of crown, in and out of leaf.
    transmissivity_leaf_on: tuple[float, ...]
    transmissivity_leaf_off: tuple[float, ...]

    def transmissivity(self, leaf_on: bool) -> np.ndarray:
        """Per crown kind, with a last entry of 1.0 for "no crown" (index -1)."""
        values = self.transmissivity_leaf_on if leaf_on else self.transmissivity_leaf_off
        return np.array(list(values) + [1.0])


@dataclass(frozen=True)
class WeatherSample:
    when: datetime
    observed_at: datetime  # latest observation the sample draws on
    persisted: bool  # True when carried forward past the latest observation
    air_temp_c: float
    relative_humidity: float
    dew_point_c: float
    vapour_hpa: float
    wind_ms: float
    cloud_fraction: float
    clearness_index: float
    global_horizontal: float  # instantaneous estimate, W/m²
    hour_mean_global_horizontal: float  # as observed over the enclosing hour, W/m²
    # Degrees the wind blows from (meteorological, 360 = north); None when calm or unobserved.
    wind_direction_deg: float | None = None

    def as_dict(self) -> dict:
        return {
            "station": "청주 ASOS (131)",
            "observed_at": self.observed_at.isoformat(),
            "persisted": self.persisted,
            "air_temp_c": round(self.air_temp_c, 2),
            "relative_humidity": round(self.relative_humidity, 1),
            "dew_point_c": round(self.dew_point_c, 2),
            "wind_ms": round(self.wind_ms, 2),
            "wind_direction_deg": None if self.wind_direction_deg is None else round(self.wind_direction_deg, 1),
            "cloud_fraction": round(self.cloud_fraction, 2),
            "clearness_index": round(self.clearness_index, 3),
            "global_horizontal_wm2": round(self.global_horizontal, 1),
            "hour_mean_global_horizontal_wm2": round(self.hour_mean_global_horizontal, 1),
        }
