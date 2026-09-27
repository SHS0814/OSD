"""Bare-earth terrain heights from the 5 m grid built by scripts/build_terrain.py."""

from __future__ import annotations

from pathlib import Path

import numpy as np


class Terrain:
    def __init__(self, path: Path):
        with np.load(path) as data:
            self.heights = data["terrain"].astype(float)
            self.origin_x = float(data["origin_x"])  # west edge, EPSG:5179
            self.origin_y = float(data["origin_y"])  # north edge, EPSG:5179
            self.cell_size = float(data["cell_size"])

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Bilinear height at EPSG:5179 points; points off the grid take its edge."""
        rows, cols = self.heights.shape
        col = np.clip((np.asarray(x) - self.origin_x) / self.cell_size - 0.5, 0, cols - 1)
        row = np.clip((self.origin_y - np.asarray(y)) / self.cell_size - 0.5, 0, rows - 1)
        col0 = np.minimum(np.floor(col).astype(int), cols - 2)
        row0 = np.minimum(np.floor(row).astype(int), rows - 2)
        fx, fy = col - col0, row - row0
        h = self.heights
        top = h[row0, col0] * (1 - fx) + h[row0, col0 + 1] * fx
        bottom = h[row0 + 1, col0] * (1 - fx) + h[row0 + 1, col0 + 1] * fx
        return top * (1 - fy) + bottom * fy
