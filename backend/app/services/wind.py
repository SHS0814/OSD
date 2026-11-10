"""Per-cell wind K(x, y; wind direction) and its direction - shelter plus a 2D mass-consistent flow.

UTCI needs a wind speed, and so far the 청주 ASOS 10 m wind was used for every
cell. Here each cell gets

    wind = ASOS ws × K,   K = K_BG × S(x, y; sector, season) × flow correction M

S is computed for the 16 compass sectors and both leaf seasons, and M is
solved once for two directions, so a request only looks maps up and combines
them. Three textbook pieces, explainable without CFD:

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

3. **M - flow around buildings, a 2D mass-consistent field** (Sherman 1978,
   the diagnostic step of MATHEW/QUIC-URB). The initial field is the ASOS
   wind, uniform, × K_BG. Building cells (≥ half covered, the same cells
   ``valid`` of the obstacle raster drops) are solid. The field closest to the initial one
   (least squares) that has zero 2D divergence and no flow through a wall is
   u = u0 + ∇φ, with the Lagrange multiplier φ from

       ∇²φ = −∇·u0,   ∂φ/∂n = 0 on walls,   φ = 0 on the open domain edge

   solved on a staggered (MAC) grid of output cells with one sparse LU
   factorisation. φ = 0 on every outer edge is Sherman's flow-through
   condition for inflow and outflow alike; the edge lies PAD_M + MARGIN_M
   beyond the campus with no building in between, so it barely constrains the
   flow among the buildings. The problem is linear in u0 and its boundary
   conditions do not depend on the wind direction, so two solves (a unit
   east and a unit north initial wind) give the field for any direction.
   This gives what S lacks: flow turning round a building, the slow-down in
   front of a wall, and the speed-up through passages and round corners.
   Open cells walled in on every side (courtyards at 4 m) get no 2D flow at
   all; they keep the S estimate and the ASOS direction.

Combining them. S and M both describe sheltering by the same buildings: M
has the slow-down next to the walls but, being a potential flow, no wake; S
has the wake. Multiplying their deficits would count the lee of a wall
twice, so - as within S, where the strongest deficit counts - the deficit is
the stronger of the two, and M's speed-up (which S knows nothing of)
multiplies:

    K = K_BG × min(m, S) × max(m, 1),   m = |M| / K_BG

S here is the whole shelter (buildings and crowns: crowns are porous, not
solid in M). The direction at a cell is M's direction.

Not modelled (and not verifiable without an anemometer): flow over the
roofs, the recirculation (reversed flow) in a wake, terrain sheltering and
gusts. The field is 2D, so a passage can only be squeezed sideways and the
speed-up m is capped at SPEEDUP_MAX; K is clipped to [K_MIN, K_BG × SPEEDUP_MAX].

UTCI takes the 10 m wind and reduces it to 1.1 m internally with an
open-terrain profile; scaling that input by K is the same as scaling the
pedestrian-level wind by K.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu

from .common import in_leaf
from .contracts import ObstacleRaster
from .grid import CELL_M, FINE_M, MAX_BUILDING_SHARE, PAD, SUBCELLS, ray_distances

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
# Open ground added round the fine raster's PAD_M for the flow solve, so the
# φ = 0 edge is ≥ 200 m from any campus building.
MARGIN_M = 100.0
# Pedestrian-level amplification in passages and at corners stays below ~2 in
# wind-tunnel and CFD studies (e.g. Blocken et al. 2007, passages between
# parallel buildings); a 2D potential-type flow squeezed through a one-cell
# gap has no such bound, hence the cap.
SPEEDUP_MAX = 2.0


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


@dataclass(frozen=True)
class FaceFlow:
    """A mass-consistent field on a staggered grid (array axes: rows run south).

    ``east`` [rows, cols + 1] is the flow through the west/east faces of each
    cell, positive eastwards; ``south`` [rows + 1, cols] through the north/south
    faces, positive southwards. ``walled_in`` marks open cells with no path
    to the domain edge, where the 2D problem has no flow."""

    east: np.ndarray
    south: np.ndarray
    walled_in: np.ndarray

    def divergence(self) -> np.ndarray:
        return self.east[:, 1:] - self.east[:, :-1] + self.south[1:, :] - self.south[:-1, :]

    def cell_velocity(self) -> tuple[np.ndarray, np.ndarray]:
        """(u east, v north) at cell centres, the mean of opposite faces."""
        u = 0.5 * (self.east[:, :-1] + self.east[:, 1:])
        v = -0.5 * (self.south[:-1, :] + self.south[1:, :])
        return u, v


class MassConsistentSolver:
    """Sherman (1978) in 2D: u = u0 + ∇φ with ∇²φ = −∇·u0, no flux through
    ``solid`` cells and φ = 0 just outside the array (flow-through edge).

    Cells are of unit size (φ is in units of the cell, which only scales φ).
    The matrix does not depend on u0, so it is factorised once."""

    def __init__(self, solid: np.ndarray):
        self.solid = np.asarray(solid, dtype=bool)
        labels, _ = ndimage.label(~self.solid)  # 4-connected open regions
        edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
        reaches_edge = np.isin(labels, edge[edge > 0])
        self.active = reaches_edge & ~self.solid
        self.walled_in = ~self.solid & ~reaches_edge
        index = np.full(self.solid.shape, -1)
        index[self.active] = np.arange(int(self.active.sum()))
        self.index = index
        n = int(self.active.sum())
        diagonal = np.zeros(n)
        pairs_i, pairs_j = [], []
        # Each open face of an active cell adds −1 on the diagonal; one shared
        # with another active cell adds +1 off it. Walls add nothing (∂φ/∂n = 0),
        # the domain edge only the −1 (φ = 0 outside).
        for a, b, ia, ib in (
            (self.active[:-1, :], self.active[1:, :], index[:-1, :], index[1:, :]),
            (self.active[:, :-1], self.active[:, 1:], index[:, :-1], index[:, 1:]),
        ):
            both = a & b
            pairs_i.append(ia[both])
            pairs_j.append(ib[both])
            np.add.at(diagonal, ia[both], -1.0)
            np.add.at(diagonal, ib[both], -1.0)
        for border in (index[0, :], index[-1, :], index[:, 0], index[:, -1]):
            np.add.at(diagonal, border[border >= 0], -1.0)
        pi, pj = np.concatenate(pairs_i), np.concatenate(pairs_j)
        matrix = coo_matrix(
            (
                np.concatenate([-diagonal, -np.ones(pi.size), -np.ones(pi.size)]),
                (np.concatenate([np.arange(n), pi, pj]), np.concatenate([np.arange(n), pj, pi])),
            ),
            shape=(n, n),
        ).tocsc()
        self._lu = splu(matrix) if n else None  # −∇², symmetric positive definite

    def solve(self, u0_east: float, v0_north: float) -> FaceFlow:
        rows, cols = self.solid.shape
        active, index = self.active, self.index
        w0 = -v0_north  # southward component, along the rows
        # Initial face flows: u0 through every face between two active cells or
        # an active cell and the edge; 0 at walls.
        open_east = np.zeros((rows, cols + 1), dtype=bool)
        open_east[:, 1:-1] = active[:, :-1] & active[:, 1:]
        open_east[:, 0], open_east[:, -1] = active[:, 0], active[:, -1]
        open_south = np.zeros((rows + 1, cols), dtype=bool)
        open_south[1:-1, :] = active[:-1, :] & active[1:, :]
        open_south[0, :], open_south[-1, :] = active[0, :], active[-1, :]
        east0 = np.where(open_east, u0_east, 0.0)
        south0 = np.where(open_south, w0, 0.0)
        if self._lu is None:
            return FaceFlow(east0, south0, self.walled_in)
        div0 = (east0[:, 1:] - east0[:, :-1] + south0[1:, :] - south0[:-1, :])[active]
        # Σ_open faces (φ_nb − φ_i) = −div0, i.e. (−∇²) φ = div0.
        phi_active = self._lu.solve(div0)
        phi = np.zeros((rows + 2, cols + 2))  # with the φ = 0 ring outside
        inner = np.zeros((rows, cols))
        inner[active] = phi_active[index[active]]
        phi[1:-1, 1:-1] = inner
        east = east0 + np.where(open_east, phi[1:-1, 1:] - phi[1:-1, :-1], 0.0)
        south = south0 + np.where(open_south, phi[1:, 1:-1] - phi[:-1, 1:-1], 0.0)
        return FaceFlow(east, south, self.walled_in)


def from_direction(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Compass bearing the wind blows from (north 360, as ASOS) of (u east, v north)."""
    bearing = np.degrees(np.arctan2(-u, -v)) % 360.0
    return np.where(bearing < 0.05, 360.0, bearing)


class WindField:
    """K maps over one obstacle raster (the space side's buildings and crowns,
    contracts.ObstacleRaster); computed per (sector, season) on first use."""

    def __init__(
        self,
        obstacles: ObstacleRaster,
        *,
        k_bg: float = K_BG,
        d_max: float = D_MAX,
        wake_e_fold: float = WAKE_E_FOLD,
    ):
        self.obstacles = obstacles
        self.k_bg = k_bg
        self.d_max = d_max
        self.wake_e_fold = wake_e_fold
        footprint = obstacles.footprint
        height = obstacles.building_height
        height = np.where(footprint & (height < MIN_OBSTACLE_M), DEFAULT_BUILDING_HEIGHT_M, height)
        self.building_h = height
        self.crown_h = obstacles.crown_height
        self.crown_kind = obstacles.crown_kind
        self.campus_fine = self._campus_mask()  # over the raster's window
        self._cache: dict[tuple[int, bool], np.ndarray] = {}  # S per (sector, leaf_on)
        self._lock = threading.Lock()
        self._basis = None  # flow_basis()
        self._flow_lock = threading.Lock()

    # -- geometry ---------------------------------------------------------------

    def _campus_mask(self) -> np.ndarray:
        return np.repeat(np.repeat(self.obstacles.inside, SUBCELLS, axis=0), SUBCELLS, axis=1)

    def blockage(self, leaf_on: bool) -> np.ndarray:
        """Per-fine-pixel aerodynamic blockage of crowns, 1 − τ; 0 where there is no crown."""
        tau = self.obstacles.transmissivity(leaf_on)
        return 1.0 - tau[self.crown_kind]

    def effective_height(self, leaf_on: bool) -> np.ndarray:
        return np.maximum(self.building_h, self.crown_h * self.blockage(leaf_on))

    def morphometry(self, sector: int, leaf_on: bool) -> dict:
        """λp, λf, mean height, d and z0 of campus (fine raster inside the boundary).

        A diagnostic for the documentation; K does not use it (module docstring)."""
        window = self.obstacles.grid.window
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
        valid = self.obstacles.valid
        rows, cols = valid.nonzero()
        r0 = rows * SUBCELLS + SUBCELLS // 2 + PAD
        c0 = cols * SUBCELLS + SUBCELLS // 2 + PAD
        n_rows, n_cols = self.obstacles.footprint.shape
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
        out = np.full(valid.shape, np.nan)
        out[rows, cols] = total / len(RAY_SPREAD_DEG)
        return out

    # -- flow round the buildings -----------------------------------------------

    def _solve_grid(self) -> tuple[np.ndarray, int]:
        """Solid output-size cells over the fine raster plus MARGIN_M of open
        ground, and the row/column offset of the output grid in it."""
        footprint = self.obstacles.footprint
        rows, cols = footprint.shape
        share = footprint.reshape(rows // SUBCELLS, SUBCELLS, cols // SUBCELLS, SUBCELLS).mean(axis=(1, 3))
        # The same rule that takes a cell out of ``valid``: every valid cell is open.
        solid = share >= MAX_BUILDING_SHARE
        margin = round(MARGIN_M / CELL_M)
        return np.pad(solid, margin, constant_values=False), PAD // SUBCELLS + margin

    def flow_basis(self) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray], np.ndarray]:
        """Cell (u, v) for a unit initial wind blowing east and one blowing
        north (before K_BG), and the walled-in cells, over the output grid."""
        with self._flow_lock:
            if self._basis is None:
                solid, offset = self._solve_grid()
                solver = MassConsistentSolver(solid)
                rows, cols = self.obstacles.valid.shape
                window = (slice(offset, offset + rows), slice(offset, offset + cols))
                east = tuple(c[window] for c in solver.solve(1.0, 0.0).cell_velocity())
                north = tuple(c[window] for c in solver.solve(0.0, 1.0).cell_velocity())
                self._basis = (east, north, solver.walled_in[window])
        return self._basis

    def flow(self, direction_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(u east, v north) per output cell relative to the ASOS speed (K_BG
        included) for a wind from ``direction_deg``, and the walled-in cells."""
        east, north, walled_in = self.flow_basis()
        bearing = math.radians(direction_deg)
        a, b = -math.sin(bearing), -math.cos(bearing)  # where the wind blows to
        u = self.k_bg * (a * east[0] + b * north[0])
        v = self.k_bg * (a * east[1] + b * north[1])
        return u, v, walled_in

    # -- lookup ---------------------------------------------------------------

    def _shelter(self, sector: int, leaf_on: bool) -> np.ndarray:
        key = (sector, leaf_on)
        with self._lock:
            cached = self._cache.get(key)
        if cached is None:
            cached = self.shelter(sector, leaf_on)
            with self._lock:
                self._cache[key] = cached
        return cached

    def shelter_factor(self, sector: int, leaf_on: bool) -> np.ndarray:
        """K_BG × S alone (no flow round the buildings), clipped to [K_MIN, 1]."""
        k = np.clip(self.k_bg * self._shelter(sector, leaf_on), K_MIN, 1.0)
        return np.where(self.obstacles.valid, k, np.nan)

    def wind(self, direction_deg: float | None, leaf_on: bool) -> tuple[np.ndarray, np.ndarray]:
        """K and the 'from' bearing per output cell (NaN where not valid).

        ``direction_deg`` None (calm) gives the mean K over the 16 sectors and no bearing."""
        sector = sector_of(direction_deg)
        if sector is None:
            k = np.mean([self.wind(s * SECTOR_DEG or 360.0, leaf_on)[0] for s in range(SECTORS)], axis=0)
            return k, np.full(k.shape, np.nan)
        shelter = self._shelter(sector, leaf_on)
        u, v, walled_in = self.flow(direction_deg)
        m = np.minimum(np.hypot(u, v) / self.k_bg, SPEEDUP_MAX)
        k = self.k_bg * np.minimum(m, shelter) * np.maximum(m, 1.0)
        # No 2D flow reaches a walled-in cell; keep the shelter estimate there.
        k = np.where(walled_in, self.k_bg * shelter, k)
        k = np.clip(k, K_MIN, self.k_bg * SPEEDUP_MAX)
        bearing = np.where(walled_in, float(direction_deg), from_direction(u, v))
        valid = self.obstacles.valid
        return np.where(valid, k, np.nan), np.where(valid, bearing, np.nan)

    def factor(self, direction_deg: float | None, leaf_on: bool) -> np.ndarray:
        """K per output cell; for calm (None) the mean over the 16 sectors."""
        return self.wind(direction_deg, leaf_on)[0]

    def precompute(self) -> None:
        self.flow_basis()
        for leaf_on in (True, False):
            for sector in range(SECTORS):
                self._shelter(sector, leaf_on)

    def wind_ms(self, speed_ms: float, direction_deg: float | None, day: date) -> np.ndarray:
        """Per-cell 10 m-equivalent wind; cells outside the valid area keep the ASOS value."""
        calm = sector_of(direction_deg, speed_ms) is None
        k = self.factor(None if calm else direction_deg, in_leaf(day))
        return speed_ms * np.where(np.isfinite(k), k, 1.0)
