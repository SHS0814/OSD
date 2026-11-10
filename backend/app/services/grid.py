"""The campus grids shared by every model (common code: change only by agreement).

Results are reported on output cells of CELL_M. Geometry (shade, obstacles)
is resolved on a finer raster of FINE_M, SUBCELLS × SUBCELLS pixels per
output cell, so a cell half in shade gets a sunlit fraction of about 0.5. The
fine raster extends PAD_M beyond the output grid on every side so terrain,
trees and buildings just outside campus still count at its edge.

Both grids are in EPSG:5179 metres, with rows running south from the north
edge and columns east from the west edge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import MultiPoint

from .geometry import to_wgs84

# 4 m keeps a pedestrian-scale picture (a row of trees, the shade strip along a
# wall) while a response stays ~0.13 MB gzipped; 2 m is ~6.6 MB raw, too slow
# to parse on a phone for every slider move.
CELL_M = 4.0
FINE_M = 2.0
SUBCELLS = int(CELL_M / FINE_M)
PAD_M = 100.0
PAD = int(PAD_M / FINE_M)

# An output cell counts as open ground only if most of it is outside buildings.
MAX_BUILDING_SHARE = 0.5


def ray_distances(limit_m: float) -> np.ndarray:
    """Sample spacing along a ray: every fine pixel nearby, coarser further out."""
    near = np.arange(FINE_M, min(limit_m, 60.0) + FINE_M, FINE_M)
    far = np.arange(60.0 + 5.0, limit_m + 5.0, 5.0) if limit_m > 60.0 else np.array([])
    return np.concatenate([near, far])


@dataclass(frozen=True)
class GridSpec:
    origin_x: float  # west edge, EPSG:5179
    origin_y: float  # north edge, EPSG:5179
    rows: int
    cols: int

    @classmethod
    def covering(cls, bounds: tuple[float, float, float, float]) -> GridSpec:
        """The grid of whole CELL_M cells covering projected (west, south, east, north)."""
        west, south, east, north = bounds
        west, south = math.floor(west / CELL_M) * CELL_M, math.floor(south / CELL_M) * CELL_M
        east, north = math.ceil(east / CELL_M) * CELL_M, math.ceil(north / CELL_M) * CELL_M
        return cls(west, north, int((north - south) / CELL_M), int((east - west) / CELL_M))

    @property
    def fine_origin(self) -> tuple[float, float]:
        """(west, north) edge of the fine raster."""
        return self.origin_x - PAD_M, self.origin_y + PAD_M

    @property
    def fine_shape(self) -> tuple[int, int]:
        """(rows, cols) of the fine raster: the output grid plus PAD pixels on every side."""
        return self.rows * SUBCELLS + 2 * PAD, self.cols * SUBCELLS + 2 * PAD

    @property
    def window(self) -> tuple[slice, slice]:
        """The part of the fine raster that lies under the output grid."""
        return (
            slice(PAD, PAD + self.rows * SUBCELLS),
            slice(PAD, PAD + self.cols * SUBCELLS),
        )

    def corners_wgs84(self) -> list[list[float]]:
        west, north = self.origin_x, self.origin_y
        east, south = west + self.cols * CELL_M, north - self.rows * CELL_M
        points = to_wgs84(MultiPoint([(west, north), (east, north), (east, south), (west, south)]))
        return [[round(p.x, 7), round(p.y, 7)] for p in points.geoms]
