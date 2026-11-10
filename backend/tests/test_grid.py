"""The shared campus grids (services/grid.py)."""

import numpy as np
import pytest

from app.services.grid import CELL_M, FINE_M, PAD, PAD_M, SUBCELLS, GridSpec, ray_distances


def test_grid_covers_the_bounds_in_whole_cells() -> None:
    grid = GridSpec.covering((1001.0, 2003.0, 1099.0, 2101.0))
    assert (grid.origin_x, grid.origin_y) == (1000.0, 2104.0)
    assert grid.cols * CELL_M >= 1099.0 - 1000.0
    assert grid.origin_y - grid.rows * CELL_M <= 2003.0
    assert (grid.rows, grid.cols) == (26, 25)


def test_fine_raster_pads_the_output_grid() -> None:
    grid = GridSpec(1000.0, 2000.0, rows=10, cols=20)
    assert grid.fine_origin == (1000.0 - PAD_M, 2000.0 + PAD_M)
    assert grid.fine_shape == (10 * SUBCELLS + 2 * PAD, 20 * SUBCELLS + 2 * PAD)
    rows, cols = grid.window
    assert (rows.start, rows.stop) == (PAD, PAD + 10 * SUBCELLS)
    assert (cols.start, cols.stop) == (PAD, PAD + 20 * SUBCELLS)
    assert SUBCELLS * FINE_M == CELL_M


def test_corners_run_clockwise_from_the_north_west() -> None:
    # Near 청주 in EPSG:5179.
    corners = GridSpec(960_000.0, 1_850_400.0, rows=100, cols=100).corners_wgs84()
    (west, north), (east, north_east), (east_south, south), (west_south, south_west) = corners
    assert west < east and south < north
    assert north == pytest.approx(north_east, abs=1e-4) and west == pytest.approx(west_south, abs=1e-4)
    assert 126 < west < 129 and 35 < south < 38


def test_rays_are_dense_nearby_and_sparse_far_away() -> None:
    distances = ray_distances(200.0)
    assert distances[0] == FINE_M
    assert np.all(np.diff(distances) > 0)
    assert np.diff(distances)[:5].max() == FINE_M
    assert distances[-1] >= 200.0
    assert ray_distances(30.0)[-1] == pytest.approx(30.0)
