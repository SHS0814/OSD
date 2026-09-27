"""Campus-wide thermal comfort (UTCI) on a regular grid - model v1.

What varies across campus is the radiation a pedestrian receives, and v1
builds it from everything known without sensors:

- a surface model of terrain (5 m DTM from 수치지도), buildings standing on it,
  and tree crowns (환경부 토지피복지도 plus hand-drawn street trees);
- shade found by tracing a ray from each 2 m ground pixel towards the sun: a
  ray that meets terrain or a building is blocked, one that passes through a
  crown keeps the crown's transmissivity;
- the sky view factor from the same surface model, with crowns counted as
  partly see-through;
- ground albedo and heating from the land cover.

Air temperature, humidity and wind are the 청주 ASOS values for the hour, the
same everywhere; the sensor correction of air temperature is v2
(docs/04-data-usage-plan.md).

Geometry is resolved on a fine raster (FINE_M) and reported on coarser output
cells (CELL_M), so a cell half in shade gets a sunlit fraction of about 0.5.
The fine raster extends PAD_M beyond the campus so terrain and trees just
outside it can shade the edge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import shapely
from shapely.geometry import MultiPoint
from shapely.geometry.base import BaseGeometry

from .geometry import to_projected, to_wgs84
from .solar import SolarPosition
from .surfaces import (
    CROWN_BASE_M,
    DEFAULT_SURFACE,
    SURFACES,
    Canopy,
    CanopyPatch,
    GroundPatch,
    in_leaf,
)
from .terrain import Terrain
from .thermal import (
    mean_radiant_temperature,
    relative_humidity,
    split_irradiance,
    utci,
    utci_category,
)
from .weather import WeatherSample

MODEL_VERSION = "v1"
CELL_M = 10.0
FINE_M = 2.0
SUBCELLS = int(CELL_M / FINE_M)
PAD_M = 100.0
PAD = int(PAD_M / FINE_M)

# Rays start at a pedestrian's chest rather than the ground, so the facets of
# the triangulated terrain do not shade the very pixel they start from.
OBSERVER_M = 1.1
SHADOW_RANGE_M = 300.0

# Sky view factor: horizon angle searched in this many azimuths, out to this range.
SVF_DIRECTIONS = 36
SVF_RANGE_M = 200.0

# An output cell counts as open ground only if most of it is outside buildings.
MAX_BUILDING_SHARE = 0.5
# Neighbour-averaging rounds for cells under buildings; 10 covers a 200 m wide block.
FILL_ROUNDS = 10


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

    def corners_wgs84(self) -> list[list[float]]:
        west, north = self.origin_x, self.origin_y
        east, south = west + self.cols * CELL_M, north - self.rows * CELL_M
        points = to_wgs84(MultiPoint([(west, north), (east, north), (east, south), (west, south)]))
        return [[round(p.x, 7), round(p.y, 7)] for p in points.geoms]


class MicroclimateModel:
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
        west, south, east, north = self.boundary.bounds
        west, south = math.floor(west / CELL_M) * CELL_M, math.floor(south / CELL_M) * CELL_M
        east, north = math.ceil(east / CELL_M) * CELL_M, math.ceil(north / CELL_M) * CELL_M
        self.grid = GridSpec(west, north, int((north - south) / CELL_M), int((east - west) / CELL_M))

        # Fine raster: the output grid plus PAD pixels on every side.
        self.fine_origin_x, self.fine_origin_y = west - PAD_M, north + PAD_M
        fine_rows = self.grid.rows * SUBCELLS + 2 * PAD
        fine_cols = self.grid.cols * SUBCELLS + 2 * PAD
        xs = self.fine_origin_x + (np.arange(fine_cols) + 0.5) * FINE_M
        ys = self.fine_origin_y - (np.arange(fine_rows) + 0.5) * FINE_M
        self.fine_x, self.fine_y = np.meshgrid(xs, ys)
        self.window = (
            slice(PAD, PAD + self.grid.rows * SUBCELLS),
            slice(PAD, PAD + self.grid.cols * SUBCELLS),
        )

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
        self.target_z = self.ground[self.target_rows, self.target_cols] + OBSERVER_M
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

    # -- per request ---------------------------------------------------------------

    def _transmissivity_lookup(self, day) -> np.ndarray:
        """Per canopy type index -> transmissivity; the extra last entry (index -1) is open sky."""
        return np.array([canopy.transmissivity(day) for canopy in self.canopy_types] + [1.0])

    def sky_view(self, day) -> np.ndarray:
        """Crowns hide part of the sky; what they hide still lets its transmissivity through."""
        lookup = self._transmissivity_lookup(day)
        present = self.canopy_kind[self.canopy_kind >= 0]
        tau = float(lookup[present].mean()) if present.size else 1.0
        return self.sky_view_canopy + (self.sky_view_solid - self.sky_view_canopy) * tau

    def sunlit_fraction(self, solar: SolarPosition, day) -> np.ndarray:
        """Direct-sun share of the open ground in each cell: 0 in full shade, 1 in full sun."""
        if solar.altitude <= 0:
            return np.where(self.valid, 0.0, np.nan)
        lookup = self._transmissivity_lookup(day)
        tan_altitude = math.tan(math.radians(solar.altitude))
        dx = math.sin(math.radians(solar.azimuth)) / FINE_M
        dy = math.cos(math.radians(solar.azimuth)) / FINE_M
        n_rows, n_cols = self.fine_x.shape

        z = self.target_z
        # A pedestrian under a crown starts in its shade.
        own = self.canopy_kind[self.target_rows, self.target_cols]
        transmitted = np.where(
            self.canopy_top[self.target_rows, self.target_cols] > z, lookup[own], 1.0
        )
        blocked = np.zeros(z.shape, dtype=bool)
        highest = max(float(self.solid.max()), float(self.canopy_top.max()))
        limit = min(SHADOW_RANGE_M, (highest - float(z.min())) / tan_altitude)
        for distance in ray_distances(limit):
            row = np.round(self.target_rows - dy * distance).astype(int)
            col = np.round(self.target_cols + dx * distance).astype(int)
            np.clip(row, 0, n_rows - 1, out=row)
            np.clip(col, 0, n_cols - 1, out=col)
            ray = z + distance * tan_altitude
            blocked |= self.solid[row, col] > ray
            in_crown = (self.canopy_top[row, col] > ray) & (self.ground[row, col] + CROWN_BASE_M < ray)
            transmitted = np.where(in_crown, np.minimum(transmitted, lookup[self.canopy_kind[row, col]]), transmitted)
        sun = np.where(blocked, 0.0, transmitted)

        with np.errstate(invalid="ignore", divide="ignore"):
            per_cell = np.bincount(self.target_cell, weights=sun, minlength=self.valid.size) / self.target_count
        return np.where(self.valid, per_cell.reshape(self.valid.shape), np.nan)

    def compute(self, when: datetime, solar: SolarPosition, weather: WeatherSample) -> dict:
        day = when.date()
        sunlit = self.sunlit_fraction(solar, day)
        sky_view = self.sky_view(day)
        irradiance = split_irradiance(
            weather.global_horizontal, when.timetuple().tm_yday, solar.altitude
        )
        air = np.full(self.valid.shape, weather.air_temp_c)
        mrt = mean_radiant_temperature(
            air_temp_c=air,
            sunlit=np.nan_to_num(sunlit),
            sky_view=np.nan_to_num(sky_view, nan=1.0),
            irradiance=irradiance,
            solar_altitude_deg=solar.altitude,
            vapour_hpa=weather.vapour_hpa,
            cloud_fraction=weather.cloud_fraction,
            ground_albedo=np.nan_to_num(self.albedo, nan=SURFACES[DEFAULT_SURFACE].albedo),
            ground_heating=np.nan_to_num(self.heating, nan=SURFACES[DEFAULT_SURFACE].ground_heating),
        )
        humidity = relative_humidity(air, weather.dew_point_c)
        comfort = utci(air, mrt, weather.wind_ms, humidity)
        mrt = np.where(self.valid, mrt, np.nan)
        comfort = np.where(self.valid, comfort, np.nan)
        summary = self._summary(comfort, mrt, sunlit)

        return {
            "model_version": MODEL_VERSION,
            "inputs": {
                "terrain": self.has_terrain,
                "canopy_share": _round(np.nanmean(np.where(self.valid, self.canopy_cover, np.nan)), 3),
                "in_leaf": in_leaf(day),
            },
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
                "order": "row-major from the north-west corner; null outside campus",
                "under_buildings": "filled from the surrounding open ground for display; "
                "not part of the summary",
            },
            "summary": summary,
            "utci": _rounded(self._fill_under_buildings(comfort)),
            "mrt": _rounded(self._fill_under_buildings(mrt)),
            "sunlit": _rounded(self._fill_under_buildings(sunlit), digits=2),
        }

    def _fill_under_buildings(self, values: np.ndarray) -> np.ndarray:
        """Give campus cells covered by buildings the mean of their open neighbours.

        Building outlines do not follow the 10 m grid, so leaving those cells
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
