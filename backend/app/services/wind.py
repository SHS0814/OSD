"""Per-cell wind speed factor K(x, y; wind direction) - an empirical shelter model.

UTCI needs a wind speed, and so far the 청주 ASOS 10 m wind was used for every
cell. Here each cell gets

    wind = ASOS ws × K,   K = K_BG × S(x, y; sector, season)

computed for the 16 compass sectors and both leaf seasons, so a request only
looks a map up. Two textbook pieces, explainable without CFD:

1. **K_BG - from the open ASOS site to campus.** The ASOS mast stands on open
   ground (WMO: z0 ≈ 0.03 m). The wind reaching campus has crossed suburban
   청주 and the campus itself, "very rough" terrain in the Davenport-Wieringa
   classification (z0 ≈ 0.5 m; Wieringa 1992). Taking the wind as equal at a
   blending height of 60 m above both (Wieringa 1986) and bringing it down
   with the log law to 10 m:

       K_BG = [ln(10/z0) / ln(60/z0)] / [ln(10/z0s) / ln(60/z0s)] ≈ 0.82

   This is the same everywhere; it matters only through UTCI's nonlinearity
   and its 0.5 m/s floor. ``morphometry`` gives the plan and frontal area
   indices and Macdonald et al. (1998) z0 and d of campus for comparison;
   they are not used because with trees counted d approaches 10 m, where the
   log law no longer holds, and obstacles are already counted by S.

2. **S - shelter behind obstacles.** Walking upwind from a cell, every
   obstacle of height H met at distance x leaves a wake deficit

       D = D_MAX × b × exp(−x / (WAKE_E_FOLD × H))

   b is 1 for a building and 1 − τ for a crown, τ being the crown's
   transmissivity already used for sunlight (optical porosity stands in for
   aerodynamic porosity, Heisler & DeWalle 1988). The strongest deficit
   counts, S = 1 − max D, averaged over three rays across the 22.5° sector.
   D_MAX and WAKE_E_FOLD follow the windbreak and building-wake literature:
   ~0.3 u₀ just behind a solid obstacle, ~85 % recovered by 10 H and nearly
   all by 20 H (Hosker 1984; Heisler & DeWalle 1988; Cleugh 1998). A cell
   under a crown starts in its own shelter (x = 0).

Not modelled (and not verifiable without an anemometer): channelling and
corner speed-up, the stagnation zone upwind of a wall, terrain sheltering,
the change of direction inside the campus, and gusts. K is clipped to
[K_MIN, 1].

UTCI takes the 10 m wind and reduces it to 1.1 m internally with an
open-terrain profile; scaling that input by K is the same as scaling the
pedestrian-level wind by K.
"""

from __future__ import annotations

import math
import threading
from datetime import date

import numpy as np
from scipy import ndimage

from .surfaces import in_leaf

SECTORS = 16
SECTOR_DEG = 360.0 / SECTORS
# ASOS reports wd = 0 with ws < 0.5 for calm (north is 360).
CALM_MS = 0.5

STATION_Z0_M = 0.03  # WMO open-terrain site
CAMPUS_Z0_M = 0.5  # Wieringa (1992) "very rough": scattered buildings and trees
BLENDING_HEIGHT_M = 60.0
REFERENCE_HEIGHT_M = 10.0
# Macdonald et al. (1998) constants for staggered cubes.
MACDONALD_A = 4.43
MACDONALD_BETA = 1.0
DRAG_COEFFICIENT = 1.2
VON_KARMAN = 0.4

D_MAX = 0.7
WAKE_E_FOLD = 6.0  # in obstacle heights
WAKE_RANGE_M = 300.0
RAY_SPREAD_DEG = (-7.5, 0.0, 7.5)
MIN_OBSTACLE_M = 1.5
# 38 of the 105 campus buildings have no known height. The shade model leaves
# them out (a wrong height casts a wrong shadow); for wind a building of
# unknown height certainly blocks, so it is given about three storeys.
DEFAULT_BUILDING_HEIGHT_M = 12.0
K_MIN = 0.05


def sector_of(direction_deg: float | None, speed_ms: float | None = None) -> int | None:
    """Compass sector 0 (N) .. 15 (NNW) of a 'from' direction; None when calm."""
    if direction_deg is None or not math.isfinite(direction_deg):
        return None
    if direction_deg == 0 or (speed_ms is not None and speed_ms < CALM_MS):
        return None
    return int(round(direction_deg / SECTOR_DEG)) % SECTORS


def macdonald(plan_index: float, frontal_index: float, height_m: float) -> tuple[float, float]:
    """Displacement height d and roughness length z0 (m), Macdonald et al. 1998."""
    if height_m <= 0 or plan_index <= 0:
        return 0.0, STATION_Z0_M
    d_ratio = 1.0 + MACDONALD_A ** (-plan_index) * (plan_index - 1.0)
    exponent = 0.5 * MACDONALD_BETA * DRAG_COEFFICIENT / VON_KARMAN**2 * (1.0 - d_ratio) * frontal_index
    z0_ratio = (1.0 - d_ratio) * math.exp(-exponent ** -0.5) if exponent > 0 else 0.0
    return d_ratio * height_m, max(z0_ratio * height_m, STATION_Z0_M)


def background_factor(z0_m: float = CAMPUS_Z0_M, d_m: float = 0.0) -> float:
    """10 m wind over terrain (z0, d) relative to 10 m wind at the open ASOS site."""
    station = math.log(REFERENCE_HEIGHT_M / STATION_Z0_M) / math.log(BLENDING_HEIGHT_M / STATION_Z0_M)
    above = REFERENCE_HEIGHT_M - d_m
    if above <= z0_m:
        return K_MIN
    campus = math.log(above / z0_m) / math.log((BLENDING_HEIGHT_M - d_m) / z0_m)
    return min(max(campus / station, K_MIN), 1.0)


K_BG = background_factor()


class WindField:
    """K maps for one MicroclimateModel; computed per (sector, season) on first use."""

    def __init__(
        self, model, *, k_bg: float = K_BG, d_max: float = D_MAX, wake_e_fold: float = WAKE_E_FOLD
    ):
        self.model = model
        self.k_bg = k_bg
        self.d_max = d_max
        self.wake_e_fold = wake_e_fold
        height = np.where(model.footprint, model.solid - model.ground, 0.0)
        height = np.where(model.footprint & (height < MIN_OBSTACLE_M), DEFAULT_BUILDING_HEIGHT_M, height)
        self.building_h = height
        has_crown = (model.canopy_kind >= 0) & ~model.footprint
        self.crown_h = np.where(has_crown, model.canopy_top - model.ground, 0.0)
        self.crown_kind = np.where(has_crown, model.canopy_kind, -1)
        self.campus_fine = self._campus_mask()  # over model.window
        self._cache: dict[tuple[int, bool], np.ndarray] = {}
        self._lock = threading.Lock()

    # -- geometry ---------------------------------------------------------------

    def _campus_mask(self) -> np.ndarray:
        from .microclimate import SUBCELLS

        return np.repeat(np.repeat(self.model.inside, SUBCELLS, axis=0), SUBCELLS, axis=1)

    def blockage(self, leaf_on: bool) -> np.ndarray:
        """Per-fine-pixel aerodynamic blockage of crowns, 1 − τ; 0 where there is no crown."""
        tau = np.array(
            [c.transmissivity_leaf_on if leaf_on else c.transmissivity_leaf_off for c in self.model.canopy_types]
            + [1.0]
        )
        return 1.0 - tau[self.crown_kind]

    def effective_height(self, leaf_on: bool) -> np.ndarray:
        return np.maximum(self.building_h, self.crown_h * self.blockage(leaf_on))

    def morphometry(self, sector: int, leaf_on: bool) -> dict:
        """λp, λf, mean height, d and z0 of campus (fine raster inside the boundary).

        A diagnostic for the documentation; K does not use it (module docstring)."""
        from .microclimate import FINE_M

        window = self.model.window
        campus = self.campus_fine
        h_eff = self.effective_height(leaf_on)[window]
        weight = np.where(self.building_h[window] > 0, 1.0, self.blockage(leaf_on)[window])
        weight = np.where(campus, weight, 0.0)
        area = campus.sum() * FINE_M**2
        plan = float((weight * FINE_M**2).sum())
        heights = np.where(campus, np.maximum(self.building_h[window], self.crown_h[window]), 0.0)
        mean_h = float((weight * heights).sum() / weight.sum()) if weight.sum() else 0.0
        # Frontal area: rotate so the wind blows down the rows, then add up
        # every rise in height met along the wind.
        masked = np.where(campus, h_eff, 0.0)
        # ndimage.rotate turns counter-clockwise, which brings the bearing the
        # wind comes from to the top (north) of the array.
        rotated = ndimage.rotate(masked, sector * SECTOR_DEG, order=0, reshape=True, mode="constant", cval=0.0)
        rises = np.clip(np.diff(rotated, axis=0, prepend=0.0), 0, None)
        frontal = float(rises.sum() * FINE_M)
        plan_index, frontal_index = plan / area, frontal / area
        d, z0 = macdonald(plan_index, frontal_index, mean_h)
        return {
            "plan_index": plan_index,
            "frontal_index": frontal_index,
            "mean_height_m": mean_h,
            "d_m": d,
            "z0_m": z0,
            "k_bg_macdonald": background_factor(z0, d),
        }

    def shelter(self, sector: int, leaf_on: bool) -> np.ndarray:
        """S per output cell (NaN where not valid): 1 − strongest upwind wake deficit."""
        from .microclimate import FINE_M, PAD, SUBCELLS, ray_distances

        model = self.model
        rows, cols = model.valid.nonzero()
        r0 = rows * SUBCELLS + SUBCELLS // 2 + PAD
        c0 = cols * SUBCELLS + SUBCELLS // 2 + PAD
        n_rows, n_cols = model.fine_x.shape
        blockage = self.blockage(leaf_on)
        strength = np.where(self.building_h > 0, 1.0, blockage)  # b per pixel
        height = np.where(self.building_h > 0, self.building_h, self.crown_h)
        obstacle = height >= MIN_OBSTACLE_M
        total = np.zeros(rows.shape)
        distances = np.concatenate([[0.0], ray_distances(WAKE_RANGE_M)])
        for spread in RAY_SPREAD_DEG:
            bearing = math.radians(sector * SECTOR_DEG + spread)
            dx, dy = math.sin(bearing) / FINE_M, math.cos(bearing) / FINE_M  # towards where the wind comes from
            deficit = np.zeros(rows.shape)
            for distance in distances:
                row = np.clip(np.round(r0 - dy * distance).astype(int), 0, n_rows - 1)
                col = np.clip(np.round(c0 + dx * distance).astype(int), 0, n_cols - 1)
                hit = obstacle[row, col]
                if not hit.any():
                    continue
                h = height[row, col]
                with np.errstate(divide="ignore", invalid="ignore"):
                    d = np.where(hit, self.d_max * strength[row, col] * np.exp(-distance / (self.wake_e_fold * h)), 0.0)
                np.maximum(deficit, d, out=deficit)
            total += 1.0 - deficit
        out = np.full(model.valid.shape, np.nan)
        out[rows, cols] = total / len(RAY_SPREAD_DEG)
        return out

    # -- lookup ---------------------------------------------------------------

    def factor(self, sector: int | None, leaf_on: bool) -> np.ndarray:
        """K per output cell; for calm (None) the mean over the 16 sectors."""
        if sector is None:
            return np.mean([self.factor(s, leaf_on) for s in range(SECTORS)], axis=0)
        key = (sector, leaf_on)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        k = np.clip(self.k_bg * self.shelter(sector, leaf_on), K_MIN, 1.0)
        k = np.where(self.model.valid, k, np.nan)
        with self._lock:
            self._cache[key] = k
        return k

    def precompute(self) -> None:
        for leaf_on in (True, False):
            for sector in range(SECTORS):
                self.factor(sector, leaf_on)

    def wind_ms(self, speed_ms: float, direction_deg: float | None, day: date) -> np.ndarray:
        """Per-cell 10 m-equivalent wind; cells outside the valid area keep the ASOS value."""
        k = self.factor(sector_of(direction_deg, speed_ms), in_leaf(day))
        return speed_ms * np.where(np.isfinite(k), k, 1.0)


def arrow_features(model, field: "WindField", speed_ms: float, direction_deg: float, day: date, step_cells: int) -> list[dict]:
    """GeoJSON points every ``step_cells`` output cells over open campus ground,
    each with the per-cell wind (before UTCI's 0.5 m/s floor) and K."""
    from shapely.geometry import MultiPoint

    from .geometry import to_wgs84
    from .microclimate import CELL_M

    k = field.factor(sector_of(direction_deg, speed_ms), in_leaf(day))
    offset = step_cells // 2
    rows, cols = model.valid.nonzero()
    keep = ((rows - offset) % step_cells == 0) & ((cols - offset) % step_cells == 0) & np.isfinite(k[rows, cols])
    rows, cols = rows[keep], cols[keep]
    if not len(rows):
        return []
    grid = model.grid
    x = grid.origin_x + (cols + 0.5) * CELL_M
    y = grid.origin_y - (rows + 0.5) * CELL_M
    points = to_wgs84(MultiPoint(np.column_stack([x, y]))).geoms
    return [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(point.x, 6), round(point.y, 6)]},
            "properties": {
                "speed_ms": round(float(speed_ms * k[r, c]), 2),
                "factor": round(float(k[r, c]), 3),
                "direction_deg": round(float(direction_deg), 1),
            },
        }
        for point, r, c in zip(points, rows, cols)
    ]
