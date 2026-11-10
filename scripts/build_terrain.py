"""Build a 5 m bare-earth terrain grid (DTM) for the campus from 수치지도.

The public 국토지리정보원 DEM is only 90 m, which averages the campus hills
away (28 m of relief against about 40 m in the surveyed spot heights), and
finer DEMs are 공개제한. The 1:5,000 수치지도 is public and carries 5 m
contours (N3L_F0010000) and spot heights (N3P_F0020000), so the grid is
interpolated from those: linear on their Delaunay triangulation.

Input: the two 수치지도 v2.0 SHP zips in data/raw/수치지도/ (도엽 36706049,
36706059; see docs/03-data-collection.md for how to get them). data/raw is not
committed; the output grid is.

    python scripts/build_terrain.py
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.interpolate import griddata
from scipy.ndimage import distance_transform_edt
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "수치지도"
BOUNDARY_PATH = ROOT / "data" / "cbnu_campus_boundary.geojson"
OUTPUT_PATH = ROOT / "data" / "cbnu_dtm_5m.npz"

CRS = "EPSG:5179"
CELL_M = 5.0
# Terrain beyond the campus can still cast shade onto it at low sun.
MARGIN_M = 300.0
CONTOUR_SPACING_M = 5.0  # densify contour lines so long straight runs still anchor the surface

CONTOURS = "N3L_F0010000"
SPOT_HEIGHTS = "N3P_F0020000"


def read_layer(zip_path: Path, layer: str) -> gpd.GeoDataFrame:
    # 수치지도 .cpg says euc_kr, but names use characters only CP949 has.
    frame = gpd.read_file(f"zip://{zip_path}!{layer}.shp", encoding="cp949")
    return frame.to_crs(CRS)


def sample_points(zips: list[Path]) -> tuple[np.ndarray, np.ndarray, dict]:
    xs, ys, zs = [], [], []
    counts = {"contour_lines": 0, "contour_vertices": 0, "spot_heights": 0}
    for zip_path in zips:
        contours = read_layer(zip_path, CONTOURS)
        for geometry, height in zip(contours.geometry.segmentize(CONTOUR_SPACING_M), contours["등고수치"]):
            if geometry is None or pd.isna(height):
                continue
            lines = geometry.geoms if geometry.geom_type == "MultiLineString" else [geometry]
            for line in lines:
                coords = np.asarray(line.coords)[:, :2]
                xs.append(coords[:, 0])
                ys.append(coords[:, 1])
                zs.append(np.full(len(coords), float(height)))
                counts["contour_vertices"] += len(coords)
            counts["contour_lines"] += 1
        spots = read_layer(zip_path, SPOT_HEIGHTS)
        spots = spots[spots["수치"].notna()]
        xs.append(spots.geometry.x.to_numpy())
        ys.append(spots.geometry.y.to_numpy())
        zs.append(spots["수치"].to_numpy(dtype=float))
        counts["spot_heights"] += len(spots)
    points = np.column_stack([np.concatenate(xs), np.concatenate(ys)])
    return points, np.concatenate(zs), counts


def main() -> None:
    zips = sorted(RAW_DIR.glob("*.zip"))
    if not zips:
        raise SystemExit(f"no 수치지도 zips in {RAW_DIR} (see docs/03-data-collection.md)")

    boundary = gpd.GeoSeries(
        [shape(json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))["features"][0]["geometry"])],
        crs="EPSG:4326",
    ).to_crs(CRS)
    west, south, east, north = boundary.total_bounds
    west = math.floor((west - MARGIN_M) / CELL_M) * CELL_M
    south = math.floor((south - MARGIN_M) / CELL_M) * CELL_M
    east = math.ceil((east + MARGIN_M) / CELL_M) * CELL_M
    north = math.ceil((north + MARGIN_M) / CELL_M) * CELL_M
    cols, rows = int((east - west) / CELL_M), int((north - south) / CELL_M)

    points, heights, counts = sample_points(zips)
    grid_x, grid_y = np.meshgrid(
        west + (np.arange(cols) + 0.5) * CELL_M,
        north - (np.arange(rows) + 0.5) * CELL_M,
    )
    terrain = griddata(points, heights, (grid_x, grid_y), method="linear")

    # Outside the triangulation (the 수치지도 sheets end at the campus's west
    # edge) carry the nearest surveyed value outwards. That strip is the low
    # town west of campus, so it hardly ever shades the campus.
    missing = ~np.isfinite(terrain)
    if missing.any():
        _, (near_row, near_col) = distance_transform_edt(missing, return_indices=True)
        terrain = terrain[near_row, near_col]

    np.savez_compressed(
        OUTPUT_PATH,
        terrain=terrain.astype(np.float32),
        origin_x=west,
        origin_y=north,
        cell_size=CELL_M,
        crs=CRS,
        metadata=json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "국토지리정보원 수치지도 v2.0 1:5,000 (36706049, 36706059): "
                "등고선 N3L_F0010000, 표고점 N3P_F0020000",
                "method": "linear interpolation on the Delaunay triangulation; "
                "cells outside it take the nearest value",
                "extrapolated_cells": int(missing.sum()),
                **counts,
            },
            ensure_ascii=False,
        ),
    )
    inside = terrain[np.isfinite(terrain)]
    print(f"wrote {OUTPUT_PATH.name}: {rows} x {cols} cells of {CELL_M:g} m")
    print(f"  from {counts['contour_lines']} contour lines ({counts['contour_vertices']} vertices), "
          f"{counts['spot_heights']} spot heights")
    print(f"  height {inside.min():.1f} - {inside.max():.1f} m, "
          f"{missing.sum()} cells ({missing.mean() * 100:.1f}%) extrapolated")


if __name__ == "__main__":
    main()
