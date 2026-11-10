"""The space side (terrain, surfaces, GeometryField) on small synthetic scenes, where the answer is known."""


import numpy as np
import pytest
from app.services.terrain import Terrain


def test_terrain_samples_bilinearly(tmp_path) -> None:
    path = tmp_path / "dtm.npz"
    np.savez(path, terrain=np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32),
             origin_x=0.0, origin_y=10.0, cell_size=5.0, crs="EPSG:5179")
    terrain = Terrain(path)
    assert terrain.sample(np.array([2.5]), np.array([7.5]))[0] == pytest.approx(0.0)
    assert terrain.sample(np.array([5.0]), np.array([5.0]))[0] == pytest.approx(15.0)
    assert terrain.sample(np.array([-100.0]), np.array([7.5]))[0] == pytest.approx(0.0)
