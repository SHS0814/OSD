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
and ``obstacles`` hands the wind side the buildings and crowns as an
``ObstacleRaster`` (contracts.py). Geometry is resolved on the fine raster
and reported on the output cells (grid.py).
"""

from __future__ import annotations

import math
from datetime import date
from functools import cached_property

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from .contracts import GeometryFields, ObstacleRaster
from .geometry import to_projected
from .grid import CELL_M, FINE_M, MAX_BUILDING_SHARE, PAD, SUBCELLS, GridSpec, ray_distances
from .solar import SolarPosition
from .surfaces import (
    CROWN_BASE_M,
    DEFAULT_SURFACE,
    SURFACES,
    Canopy,
    CanopyPatch,
    GroundPatch,
)
from .terrain import Terrain

# Rays start at a pedestrian's chest rather than the ground, so the facets of
# the triangulated terrain do not shade the very pixel they start from.
OBSERVER_M = 1.1
SHADOW_RANGE_M = 300.0

# Sky view factor: horizon angle searched in this many azimuths, out to this range.
SVF_DIRECTIONS = 36
SVF_RANGE_M = 200.0

# Neighbour-averaging rounds for cells under buildings: enough to close a
# 200 m wide block from both sides.
FILL_ROUNDS = math.ceil(100.0 / CELL_M)


class GeometryField:
    def __init__(
        self,
        campus_boundary: BaseGeometry,
        buildings: list,
        terrain: Terrain | None = None,
        ground: list[GroundPatch] | None = None,
        canopies: list[CanopyPatch] | None = None,
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
        self.canopy_top, self.canopy_kind, self.canopy_types = self._grow_canopies(canopies or [])
        albedo, heating = self._paint_ground(ground or [])

        cell_x = west + (np.arange(self.grid.cols) + 0.5) * CELL_M
        cell_y = north - (np.arange(self.grid.rows) + 0.5) * CELL_M
        self.cell_x, self.cell_y = np.meshgrid(cell_x, cell_y)
        open_ground = ~self.footprint[self.window]
        open_count = self._to_cells(open_ground.astype(float))
        building_share = 1.0 - open_count
        self.inside = shapely.contains_xy(self.boundary, self.cell_x, self.cell_y)
        self.valid = self.inside & (building_share < MAX_BUILDING_SHARE)

        with np.errstate(invalid="ignore", divide="ignore"):
            self.albedo = self._to_cells(np.where(open_ground, albedo[self.window], 0)) / open_count
            self.heating = self._to_cells(np.where(open_ground, heating[self.window], 0)) / open_count
        self.canopy_cover = self._to_cells(
            (open_ground & (self.canopy_kind[self.window] >= 0)).astype(float)
        )

        self._prepare_shadow_targets(open_ground)
        self.sky_view_solid, self.sky_view_canopy = self._sky_view_factors()

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

    def _grow_canopies(self, canopies: list[CanopyPatch]):
        top = np.full(self.fine_x.shape, -np.inf)
        kind = np.full(self.fine_x.shape, -1, dtype=np.int16)
        types: list[Canopy] = []
        for patch in canopies:
            if patch.canopy not in types:
                types.append(patch.canopy)
            index = types.index(patch.canopy)
            box, inside = self._mask(patch.geometry)
            inside &= ~self.footprint[box]  # buildings replace the land cover under them
            crown = self.ground[box] + patch.canopy.height_m
            higher = inside & (crown > top[box])
            top[box] = np.where(higher, crown, top[box])
            kind[box] = np.where(higher, index, kind[box])
        return top, kind, types

    def _paint_ground(self, ground: list[GroundPatch]) -> tuple[np.ndarray, np.ndarray]:
        default = SURFACES[DEFAULT_SURFACE]
        albedo = np.full(self.fine_x.shape, default.albedo)
        heating = np.full(self.fine_x.shape, default.ground_heating)
        for patch in ground:
            surface = SURFACES[patch.surface]
            box, inside = self._mask(patch.geometry)
            albedo[box] = np.where(inside, surface.albedo, albedo[box])
            heating[box] = np.where(inside, surface.ground_heating, heating[box])
        return albedo, heating

    def _to_cells(self, fine: np.ndarray) -> np.ndarray:
        rows, cols = self.grid.rows, self.grid.cols
        return fine.reshape(rows, SUBCELLS, cols, SUBCELLS).mean(axis=(1, 3))

    def _prepare_shadow_targets(self, open_ground: np.ndarray) -> None:
        """Open-ground fine pixels of the valid cells, which are all that need rays."""
        valid_fine = np.repeat(np.repeat(self.valid, SUBCELLS, axis=0), SUBCELLS, axis=1)
        rows, cols = np.nonzero(valid_fine & open_ground)
        self.target_rows = rows + PAD
        self.target_cols = cols + PAD
        self.target_cell = (rows // SUBCELLS) * self.grid.cols + cols // SUBCELLS
        self.target_count = np.bincount(self.target_cell, minlength=self.valid.size)

    def _sky_view_factors(self) -> tuple[np.ndarray, np.ndarray]:
        """SVF from each valid cell centre: over terrain and buildings, and with crowns too.

        Each is 1 - mean(sin² of the horizon angle) over SVF_DIRECTIONS azimuths.
        """
        rows, cols = self.valid.nonzero()
        fine_row = rows * SUBCELLS + SUBCELLS // 2 + PAD
        fine_col = cols * SUBCELLS + SUBCELLS // 2 + PAD
        x, y = self.fine_x[fine_row, fine_col], self.fine_y[fine_row, fine_col]
        z = self.ground[fine_row, fine_col] + OBSERVER_M
        n_rows, n_cols = self.fine_x.shape
        solid_sum = np.zeros(x.shape)
        canopy_sum = np.zeros(x.shape)
        for azimuth in np.linspace(0, 2 * math.pi, SVF_DIRECTIONS, endpoint=False):
            dx, dy = math.sin(azimuth), math.cos(azimuth)
            steep_solid = np.zeros(x.shape)
            steep_canopy = np.zeros(x.shape)
            for distance in ray_distances(SVF_RANGE_M):
                col = np.clip(((x + dx * distance - self.fine_origin_x) / FINE_M).astype(int), 0, n_cols - 1)
                row = np.clip(((self.fine_origin_y - (y + dy * distance)) / FINE_M).astype(int), 0, n_rows - 1)
                rise_solid = (self.solid[row, col] - z) / distance
                steep_solid = np.maximum(steep_solid, rise_solid)
                rise_canopy = (self.canopy_top[row, col] - z) / distance
                steep_canopy = np.maximum(steep_canopy, np.maximum(rise_solid, rise_canopy))
            solid_sum += np.sin(np.arctan(steep_solid)) ** 2
            canopy_sum += np.sin(np.arctan(steep_canopy)) ** 2
        solid = 1.0 - solid_sum / SVF_DIRECTIONS
        canopy = 1.0 - canopy_sum / SVF_DIRECTIONS
        # Standing under a crown, the sky overhead is the crown.
        canopy = np.where(self.canopy_top[fine_row, fine_col] > z, 0.0, canopy)
        out_solid = np.full(self.valid.shape, np.nan)
        out_canopy = np.full(self.valid.shape, np.nan)
        out_solid[rows, cols] = solid
        out_canopy[rows, cols] = canopy
        return out_solid, out_canopy

    # -- per instant ---------------------------------------------------------------

    def _transmissivity_lookup(self, day: date) -> np.ndarray:
        """Per canopy type index -> transmissivity; the extra last entry (index -1) is open sky."""
        return np.array([canopy.transmissivity(day) for canopy in self.canopy_types] + [1.0])

    def sky_view(self, day: date) -> np.ndarray:
        """Crowns hide part of the sky; what they hide still lets its transmissivity through."""
        lookup = self._transmissivity_lookup(day)
        present = self.canopy_kind[self.canopy_kind >= 0]
        tau = float(lookup[present].mean()) if present.size else 1.0
        return self.sky_view_canopy + (self.sky_view_solid - self.sky_view_canopy) * tau

    def _trace_sun(self, rows: np.ndarray, cols: np.ndarray, solar: SolarPosition, day: date) -> np.ndarray:
        """Direct-sun share reaching OBSERVER_M above the given fine pixels (sun above the horizon)."""
        lookup = self._transmissivity_lookup(day)
        tan_altitude = math.tan(math.radians(solar.altitude))
        dx = math.sin(math.radians(solar.azimuth)) / FINE_M
        dy = math.cos(math.radians(solar.azimuth)) / FINE_M
        n_rows, n_cols = self.fine_x.shape

        z = self.ground[rows, cols] + OBSERVER_M
        # A pedestrian under a crown starts in its shade.
        own = self.canopy_kind[rows, cols]
        transmitted = np.where(self.canopy_top[rows, cols] > z, lookup[own], 1.0)
        blocked = np.zeros(z.shape, dtype=bool)
        highest = max(float(self.solid.max()), float(self.canopy_top.max()))
        limit = min(SHADOW_RANGE_M, (highest - float(z.min())) / tan_altitude)
        for distance in ray_distances(limit):
            row = np.round(rows - dy * distance).astype(int)
            col = np.round(cols + dx * distance).astype(int)
            np.clip(row, 0, n_rows - 1, out=row)
            np.clip(col, 0, n_cols - 1, out=col)
            ray = z + distance * tan_altitude
            blocked |= self.solid[row, col] > ray
            in_crown = (self.canopy_top[row, col] > ray) & (self.ground[row, col] + CROWN_BASE_M < ray)
            transmitted = np.where(in_crown, np.minimum(transmitted, lookup[self.canopy_kind[row, col]]), transmitted)
        return np.where(blocked, 0.0, transmitted)

    def fine_pixel(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Fine raster (row, col) of projected points; only meaningful inside the raster."""
        col = ((np.asarray(x) - self.fine_origin_x) // FINE_M).astype(int)
        row = ((self.fine_origin_y - np.asarray(y)) // FINE_M).astype(int)
        return row, col

    def sunlit_at(self, solar: SolarPosition, day: date, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Direct-sun share at single points (projected), e.g. sensors, rather than cell means."""
        if solar.altitude <= 0:
            return np.zeros(np.shape(x))
        row, col = self.fine_pixel(x, y)
        return self._trace_sun(row, col, solar, day)

    def sunlit_fraction(self, solar: SolarPosition, day: date) -> np.ndarray:
        """Direct-sun share of the open ground in each cell: 0 in full shade, 1 in full sun."""
        if solar.altitude <= 0:
            return np.where(self.valid, 0.0, np.nan)
        sun = self._trace_sun(self.target_rows, self.target_cols, solar, day)

        with np.errstate(invalid="ignore", divide="ignore"):
            per_cell = np.bincount(self.target_cell, weights=sun, minlength=self.valid.size) / self.target_count
        return np.where(self.valid, per_cell.reshape(self.valid.shape), np.nan)

    def at(self, solar: SolarPosition, day: date) -> GeometryFields:
        """Sun, sky and ground of every output cell for the comfort side."""
        default = SURFACES[DEFAULT_SURFACE]
        return GeometryFields(
            valid=self.valid,
            sunlit=self.sunlit_fraction(solar, day),
            sky_view=self.sky_view(day),
            # Cells with no open ground (all building) take the default surface.
            albedo=np.nan_to_num(self.albedo, nan=default.albedo),
            heating=np.nan_to_num(self.heating, nan=default.ground_heating),
        )

    @cached_property
    def obstacles(self) -> ObstacleRaster:
        """Buildings and crowns on the fine raster for the wind side."""
        has_crown = (self.canopy_kind >= 0) & ~self.footprint
        return ObstacleRaster(
            grid=self.grid,
            inside=self.inside,
            valid=self.valid,
            footprint=self.footprint,
            building_height=np.where(self.footprint, self.solid - self.ground, 0.0),
            crown_height=np.where(has_crown, self.canopy_top - self.ground, 0.0),
            crown_kind=np.where(has_crown, self.canopy_kind, -1),
            transmissivity_leaf_on=tuple(c.transmissivity_leaf_on for c in self.canopy_types),
            transmissivity_leaf_off=tuple(c.transmissivity_leaf_off for c in self.canopy_types),
        )

    def canopy_share(self) -> float:
        """Share of the valid cells' open ground under crowns."""
        return float(np.nanmean(np.where(self.valid, self.canopy_cover, np.nan)))

    def fill_under_buildings(self, values: np.ndarray) -> np.ndarray:
        """Give campus cells covered by buildings the mean of their open neighbours.

        Building outlines do not follow the grid, so leaving those cells
        empty shows the base map as a pale seam between each building and the
        heatmap. The 3D buildings are drawn over these cells anyway; the fill
        only has to close the seam, so a few rounds of neighbour averaging do.
        """
        filled = values.copy()
        for _ in range(FILL_ROUNDS):
            missing = self.inside & ~np.isfinite(filled)
            if not missing.any():
                break
            padded = np.pad(filled, 1, constant_values=np.nan)
            neighbours = np.stack(
                [
                    padded[1 + dy : 1 + dy + filled.shape[0], 1 + dx : 1 + dx + filled.shape[1]]
                    for dy in (-1, 0, 1)
                    for dx in (-1, 0, 1)
                    if dy or dx
                ]
            )
            count = np.isfinite(neighbours).sum(axis=0)
            total = np.nansum(neighbours, axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                filled = np.where(missing & (count > 0), total / count, filled)
        return filled
