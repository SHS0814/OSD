"""Per-cell wind K(x, y; wind direction) - shelter behind buildings and crowns.

UTCI needs a wind speed, and so far the 청주 ASOS 10 m wind was used for every
cell. Here each cell gets

    wind = ASOS ws × K,   K = K_BG × S(x, y; sector, season)

K_BG brings the open-site ASOS wind to the rougher campus with the log law
(Wieringa 1986, 1992). S is what is left behind obstacles upwind: every
obstacle of height H met at distance x leaves a wake deficit

    D = D_MAX × b × exp(−x / (WAKE_E_FOLD × H))

with b = 1 for a building and 1 − τ for a crown (τ its transmissivity for
sunlight; Heisler & DeWalle 1988), S = 1 − max D over three rays across the
22.5° sector (Hosker 1984; Cleugh 1998). The space side hands the buildings
and crowns over as an ObstacleRaster (contracts.py). The flow round the
buildings is still to come.
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

    def factor(self, direction_deg: float | None, leaf_on: bool) -> np.ndarray:
        """K = K_BG × S per output cell; for calm (None) the mean over the 16 sectors."""
        sector = sector_of(direction_deg)
        if sector is None:
            return np.mean([self.shelter_factor(s, leaf_on) for s in range(SECTORS)], axis=0)
        return self.shelter_factor(sector, leaf_on)

    def precompute(self) -> None:
        for leaf_on in (True, False):
            for sector in range(SECTORS):
                self._shelter(sector, leaf_on)

    def wind_ms(self, speed_ms: float, direction_deg: float | None, day: date) -> np.ndarray:
        """Per-cell 10 m-equivalent wind; cells outside the valid area keep the ASOS value."""
        calm = sector_of(direction_deg, speed_ms) is None
        k = self.factor(None if calm else direction_deg, in_leaf(day))
        return speed_ms * np.where(np.isfinite(k), k, 1.0)
