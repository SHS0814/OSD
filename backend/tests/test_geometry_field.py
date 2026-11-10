"""The space side (terrain, surfaces, GeometryField) on small synthetic scenes, where the answer is known."""

from datetime import date
import json

import numpy as np
import pytest
from shapely.geometry import Polygon, box

from app.services.geometry import to_projected, to_wgs84
from app.services.surfaces import Canopy, CanopyPatch, in_leaf, load_street_trees
from app.services.terrain import Terrain

SUMMER = date(2025, 8, 5)
WINTER = date(2026, 1, 15)
CENTRE = to_projected(box(127.4566, 36.6281, 127.4568, 36.6283)).centroid
TREE = Canopy(height_m=12.0, transmissivity_leaf_on=0.2, transmissivity_leaf_off=0.6)


def square(x: float, y: float, half: float) -> Polygon:
    """Projected square centred ``(x, y)`` metres from the scene centre."""
    return box(CENTRE.x + x - half, CENTRE.y + y - half, CENTRE.x + x + half, CENTRE.y + y + half)


def test_terrain_samples_bilinearly(tmp_path) -> None:
    path = tmp_path / "dtm.npz"
    np.savez(path, terrain=np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32),
             origin_x=0.0, origin_y=10.0, cell_size=5.0, crs="EPSG:5179")
    terrain = Terrain(path)
    assert terrain.sample(np.array([2.5]), np.array([7.5]))[0] == pytest.approx(0.0)
    assert terrain.sample(np.array([5.0]), np.array([5.0]))[0] == pytest.approx(15.0)
    assert terrain.sample(np.array([-100.0]), np.array([7.5]))[0] == pytest.approx(0.0)


def test_street_tree_lines_become_crowns(tmp_path) -> None:
    line = to_wgs84(square(0, 0, 1)).centroid
    far = to_wgs84(square(100, 0, 1)).centroid
    path = tmp_path / "trees.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[line.x, line.y], [far.x, far.y]]},
        "properties": {"leaf": "conifer", "height_m": 9, "canopy_width_m": 6},
    }]}))
    [patch] = load_street_trees(path)
    assert patch.geometry.area == pytest.approx(100 * 6, rel=0.05)
    assert patch.canopy.height_m == 9
    assert patch.canopy.transmissivity(WINTER) == patch.canopy.transmissivity(SUMMER)
    assert load_street_trees(tmp_path / "missing.geojson") == []


def test_leaf_season() -> None:
    assert in_leaf(SUMMER)
    assert not in_leaf(WINTER)
    assert not in_leaf(date(2026, 11, 20))
