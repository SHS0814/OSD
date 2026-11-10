"""Sun, sky and ground on the campus grid - the space half of model v1.

What varies across campus is the radiation a pedestrian receives, and that
is set by the surroundings, all known without sensors:

- a surface model of terrain (5 m DTM from 수치지도), buildings standing on it,
  and tree crowns (환경부 토지피복지도, crowns traced from aerial photos and
  hand-drawn street trees);
- shade found by tracing a ray from each 2 m ground pixel towards the sun: a
  ray that meets terrain or a building is blocked, one that passes through a
  crown keeps the crown's transmissivity;
- the sky view factor from the same surface model, with crowns counted as
  partly see-through;
- ground albedo and heating from the land cover.

``GeometryField.at`` hands these to the comfort side as ``GeometryFields``
(contracts.py). Geometry is resolved on the fine raster and reported on the
output cells (grid.py).
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from .geometry import to_projected
from .grid import CELL_M, FINE_M, MAX_BUILDING_SHARE, PAD, SUBCELLS, GridSpec, ray_distances
from .terrain import Terrain


class GeometryField:
    def __init__(
        self,
        campus_boundary: BaseGeometry,
        buildings: list,
        terrain: Terrain | None = None,
    ):
        self.boundary = to_projected(campus_boundary)
        self.buildings = buildings
        self.has_terrain = terrain is not None
        self.grid = GridSpec.covering(self.boundary.bounds)
        west, north = self.grid.origin_x, self.grid.origin_y

        # Fine raster: the output grid plus PAD pixels on every side.
        self.fine_origin_x, self.fine_origin_y = self.grid.fine_origin
        fine_rows, fine_cols = self.grid.fine_shape
        xs = self.fine_origin_x + (np.arange(fine_cols) + 0.5) * FINE_M
        ys = self.fine_origin_y - (np.arange(fine_rows) + 0.5) * FINE_M
        self.fine_x, self.fine_y = np.meshgrid(xs, ys)
        self.window = self.grid.window

        self.ground = terrain.sample(self.fine_x, self.fine_y) if terrain else np.zeros(self.fine_x.shape)
        self.solid, self.footprint = self._raise_buildings()

        cell_x = west + (np.arange(self.grid.cols) + 0.5) * CELL_M
        cell_y = north - (np.arange(self.grid.rows) + 0.5) * CELL_M
        self.cell_x, self.cell_y = np.meshgrid(cell_x, cell_y)
        open_ground = ~self.footprint[self.window]
        open_count = self._to_cells(open_ground.astype(float))
        building_share = 1.0 - open_count
        self.inside = shapely.contains_xy(self.boundary, self.cell_x, self.cell_y)
        self.valid = self.inside & (building_share < MAX_BUILDING_SHARE)

    # -- building the surface model ------------------------------------------------

    def _mask(self, polygon: BaseGeometry) -> tuple[tuple[slice, slice], np.ndarray]:
        """Fine pixels inside ``polygon``, computed only over its bounding box."""
        minx, miny, maxx, maxy = polygon.bounds
        rows, cols = self.fine_x.shape
        c0 = max(int((minx - self.fine_origin_x) / FINE_M), 0)
        c1 = min(int((maxx - self.fine_origin_x) / FINE_M) + 1, cols)
        r0 = max(int((self.fine_origin_y - maxy) / FINE_M), 0)
        r1 = min(int((self.fine_origin_y - miny) / FINE_M) + 1, rows)
        box = (slice(r0, max(r0, r1)), slice(c0, max(c0, c1)))
        return box, shapely.contains_xy(polygon, self.fine_x[box], self.fine_y[box])

    def _raise_buildings(self) -> tuple[np.ndarray, np.ndarray]:
        solid = self.ground.copy()
        footprint = np.zeros(self.fine_x.shape, dtype=bool)
        for building in self.buildings:
            box, inside = self._mask(to_projected(building.geometry))
            if not inside.any():
                continue
            footprint[box] |= inside
            if building.height_m is not None:
                # A flat roof over the lowest ground under the footprint.
                roof = self.ground[box][inside].min() + building.height_m
                solid[box] = np.where(inside, np.maximum(solid[box], roof), solid[box])
        return solid, footprint

    def _to_cells(self, fine: np.ndarray) -> np.ndarray:
        rows, cols = self.grid.rows, self.grid.cols
        return fine.reshape(rows, SUBCELLS, cols, SUBCELLS).mean(axis=(1, 3))
