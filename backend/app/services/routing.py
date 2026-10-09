"""Shade-aware walking routes over the campus path network.

The network is OpenStreetMap's walkable ways (scripts/build_walk_network.py),
cut into pieces no longer than SEGMENT_M so each piece reads the felt
temperature (UTCI) of the grid cell it lies in. A piece costs

    length × (1 + α × heat),   heat = max(0, UTCI − baseline) / HEAT_SCALE_C

where the baseline is the felt temperature in shade at that instant (a low
percentile over campus) but never below COMFORT_LIMIT_C. Measuring heat from
the shade rather than from the comfort limit matters in summer: shade is
already ~38 °C then, so against 26 °C sun and shade would cost nearly the
same and every route would be the shortest. On a mild day nothing exceeds the
comfort limit and only the shortest route is given.

α = 0 is the shortest route and a larger α trades distance for shade.
Routes are found for a ladder of α; the coolest one that is at most
COOLEST_DETOUR times the shortest is the "coolest" route, and the coolest
within BALANCED_DETOUR is the "balanced" one. Air temperature is the same
everywhere, so what the cost really steers by is sun versus shade.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, shape

from .geometry import to_projected, to_wgs84
from .microclimate import CELL_M, GridSpec

SEGMENT_M = 4.0
MAX_SNAP_M = 150.0  # a point further than this from any path is not on campus
COMFORT_LIMIT_C = 26.0  # top of UTCI "no thermal stress"
HEAT_SCALE_C = 5.0
# Percentile of campus UTCI taken as "in the shade" for the heat baseline.
SHADE_PERCENTILE = 5
STRONG_HEAT_C = 32.0  # UTCI "strong heat stress" and above
WALK_SPEED_MS = 1.2
ALPHAS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0)
BALANCED_DETOUR = 1.15
COOLEST_DETOUR = 1.30


class RouteUnavailable(LookupError):
    pass


@dataclass(frozen=True)
class Route:
    kind: str  # shortest | balanced | coolest
    nodes: list[int]
    edges: list[int]


class WalkNetwork:
    def __init__(self, path: Path):
        collection = json.loads(path.read_text(encoding="utf-8"))
        node_index: dict[tuple[float, float], int] = {}
        xy: list[tuple[float, float]] = []

        def vertex(x: float, y: float) -> int:
            key = (round(x, 2), round(y, 2))
            if key not in node_index:
                node_index[key] = len(xy)
                xy.append((x, y))
            return node_index[key]

        a_list, b_list = [], []
        for feature in collection["features"]:
            line = to_projected(shape(feature["geometry"]))
            coords = list(line.coords)
            for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
                length = math.hypot(x1 - x0, y1 - y0)
                if length == 0:
                    continue
                pieces = max(1, math.ceil(length / SEGMENT_M))
                previous = vertex(x0, y0)
                for step in range(1, pieces + 1):
                    t = step / pieces
                    current = vertex(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                    if current != previous:
                        a_list.append(previous)
                        b_list.append(current)
                    previous = current

        self.xy = np.array(xy)
        pairs: dict[tuple[int, int], int] = {}
        for a, b in zip(a_list, b_list):
            pairs.setdefault((min(a, b), max(a, b)), len(pairs))
        self.edge_a = np.array([a for a, _ in pairs])
        self.edge_b = np.array([b for _, b in pairs])
        self.edge_of = pairs
        delta = self.xy[self.edge_b] - self.xy[self.edge_a]
        self.length = np.maximum(np.hypot(delta[:, 0], delta[:, 1]), 0.01)
        self.mid = (self.xy[self.edge_a] + self.xy[self.edge_b]) / 2
        self.tree = cKDTree(self.xy)

    @property
    def node_count(self) -> int:
        return len(self.xy)

    def snap(self, lon: float, lat: float) -> int:
        point = to_projected(Point(lon, lat))
        distance, index = self.tree.query([point.x, point.y])
        if distance > MAX_SNAP_M:
            raise RouteUnavailable(f"({lat:.5f}, {lon:.5f}) is {distance:.0f} m from the nearest path")
        return int(index)

    def sample(self, values: np.ndarray, grid: GridSpec) -> np.ndarray:
        """Grid value at each edge's midpoint; NaN off the grid or outside campus."""
        col = np.floor((self.mid[:, 0] - grid.origin_x) / CELL_M).astype(int)
        row = np.floor((grid.origin_y - self.mid[:, 1]) / CELL_M).astype(int)
        inside = (row >= 0) & (row < grid.rows) & (col >= 0) & (col < grid.cols)
        out = np.full(len(self.length), np.nan)
        out[inside] = values[row[inside], col[inside]]
        return out

    def _path(self, weights: np.ndarray, start: int, end: int) -> tuple[list[int], list[int]]:
        n = self.node_count
        matrix = csr_matrix(
            (np.concatenate([weights, weights]),
             (np.concatenate([self.edge_a, self.edge_b]), np.concatenate([self.edge_b, self.edge_a]))),
            shape=(n, n),
        )
        _, predecessors = dijkstra(matrix, indices=start, return_predecessors=True)
        if predecessors[end] < 0:
            raise RouteUnavailable("the two points are not connected")
        nodes = [end]
        while nodes[-1] != start:
            nodes.append(int(predecessors[nodes[-1]]))
        nodes.reverse()
        edges = [self.edge_of[(min(a, b), max(a, b))] for a, b in zip(nodes, nodes[1:])]
        return nodes, edges

    def routes(self, start: int, end: int, utci: np.ndarray, shade_utci: float, daylight: bool) -> list[Route]:
        """Shortest, then balanced and coolest when they differ from it and from each other.

        ``utci`` is per edge; NaN (off campus) counts as the median of the edges.
        ``shade_utci`` is the felt temperature in shade at the instant.
        """
        if start == end:
            raise RouteUnavailable("start and end are the same place")
        nodes, edges = self._path(self.length, start, end)
        found = [Route("shortest", nodes, edges)]
        if not daylight:
            return found

        filled = np.where(np.isfinite(utci), utci, np.nanmedian(utci) if np.isfinite(utci).any() else 0.0)
        heat = np.maximum(filled - max(COMFORT_LIMIT_C, shade_utci), 0) / HEAT_SCALE_C
        if not heat.any():
            return found
        shortest_length = float(self.length[edges].sum())
        candidates = []
        for alpha in ALPHAS:
            nodes, edges = self._path(self.length * (1 + alpha * heat), start, end)
            candidates.append((float(self.length[edges].sum()), float((self.length[edges] * heat[edges]).sum()), nodes, edges))
        for kind, limit in (("balanced", BALANCED_DETOUR), ("coolest", COOLEST_DETOUR)):
            allowed = [c for c in candidates if c[0] <= shortest_length * limit]
            if not allowed:
                continue
            _, _, nodes, edges = min(allowed, key=lambda c: (c[1], c[0]))
            if all(route.nodes != nodes for route in found):
                found.append(Route(kind, nodes, edges))
        return found

    def describe(self, route: Route, utci: np.ndarray, sunlit: np.ndarray, shortest_m: float) -> dict:
        """GeoJSON feature with the route's length and heat exposure."""
        lengths = self.length[route.edges]
        total = float(lengths.sum())
        known = np.isfinite(utci[route.edges])
        temps = utci[route.edges]
        sun = sunlit[route.edges]
        line = to_wgs84(LineString(self.xy[route.nodes]))
        strong = float(lengths[known & (temps > STRONG_HEAT_C)].sum())
        sun_known = np.isfinite(sun)
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[round(x, 7), round(y, 7)] for x, y in line.coords]},
            "properties": {
                "kind": route.kind,
                "length_m": round(total, 1),
                "extra_m": round(total - shortest_m, 1),
                "walk_minutes": round(total / WALK_SPEED_MS / 60, 1),
                "mean_utci": round(float(np.average(temps[known], weights=lengths[known])), 1) if known.any() else None,
                "strong_heat_minutes": round(strong / WALK_SPEED_MS / 60, 1),
                "sun_share": round(float(np.average(sun[sun_known], weights=lengths[sun_known])), 2) if sun_known.any() else None,
                "sun_minutes": round(float((lengths[sun_known] * sun[sun_known]).sum()) / WALK_SPEED_MS / 60, 1),
            },
        }
