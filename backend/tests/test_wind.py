"""Per-cell wind (services/wind.py) on synthetic scenes where the answer is known."""

import math

import numpy as np
import pytest

from shapely.affinity import rotate, scale

from app.services.wind import (
    K_BG,
    SPEEDUP_MAX,
    STATION_Z0_M,
    MassConsistentSolver,
    WindField,
    arrow_features,
    background_factor,
    from_direction,
    macdonald,
    sector_of,
)
from fakes import cell_of, square_obstacles
from test_geometry_field import SUMMER, WINTER, cell_at, scene, square

NORTH, EAST, SOUTH, WEST = 0, 4, 8, 12


def test_sectors_follow_the_compass_and_calm_has_none() -> None:
    assert sector_of(360) == NORTH
    assert sector_of(270) == WEST
    assert sector_of(290) == 13  # WNW
    assert sector_of(90) == EAST
    assert sector_of(0, 0.3) is None  # ASOS writes calm as wd = 0
    assert sector_of(270, 0.2) is None
    assert sector_of(None) is None


def test_background_factor_is_one_on_open_ground_and_less_on_rough() -> None:
    assert background_factor(STATION_Z0_M) == pytest.approx(1.0)
    assert 0.75 < K_BG < 0.9
    assert background_factor(1.0) < K_BG


def test_macdonald_gives_more_roughness_for_more_frontal_area() -> None:
    d_low, z0_low = macdonald(0.2, 0.05, 15.0)
    d_high, z0_high = macdonald(0.2, 0.2, 15.0)
    assert d_low == pytest.approx(d_high)  # d depends on λp only
    assert z0_high > z0_low
    assert macdonald(0.0, 0.0, 0.0) == (0.0, STATION_Z0_M)


def test_the_field_needs_only_an_obstacle_raster() -> None:
    # A stand-in raster (no ray tracer, no campus data): one 10 m tall,
    # 20 m wide building; a west wind leaves its wake to the east.
    raster = square_obstacles(buildings=[(0, 0, 10, 10.0)])
    field = WindField(raster)
    k = field.shelter_factor(WEST, leaf_on=True)
    assert k[cell_of(raster, -40, 0)] == pytest.approx(K_BG)
    assert k[cell_of(raster, 14, 0)] < k[cell_of(raster, 60, 0)] < K_BG
    k, bearing = field.wind(270.0, leaf_on=True)
    assert not np.isfinite(k[cell_of(raster, 0, 0)])  # building cells are not valid
    assert np.nanmax(k) > K_BG  # sped up beside the building
    assert np.nanmedian(bearing) == pytest.approx(270, abs=1)


def test_open_ground_gets_the_background_factor() -> None:
    k, bearing = WindField(scene().obstacles).wind(270.0, leaf_on=True)
    assert np.nanmin(k) == pytest.approx(K_BG)
    assert np.nanmax(k) == pytest.approx(K_BG)
    assert np.nanmin(bearing) == pytest.approx(270.0)
    assert np.nanmax(bearing) == pytest.approx(270.0)


def test_a_building_shelters_its_lee_and_the_wake_recovers() -> None:
    # The shelter model S alone, without the flow round the building.
    # 10 m tall, 20 m wide; a west wind leaves its wake to the east.
    model = scene(buildings=[(square(0, 0, 10), 10.0)])
    k = WindField(model.obstacles).shelter_factor(WEST, leaf_on=True)
    upwind = k[cell_at(model, -40, 0)]
    near = k[cell_at(model, 14, 0)]
    mid = k[cell_at(model, 60, 0)]
    far = k[cell_at(model, 130, 0)]
    beside = k[cell_at(model, 40, 60)]
    assert upwind == pytest.approx(K_BG)
    assert beside == pytest.approx(K_BG)
    assert near < mid < far < K_BG
    assert near == pytest.approx(K_BG * (1 - 0.7 * np.exp(-4 / 60)), rel=0.1)
    # The same building, wind from the east: the west side is now the lee.
    k_east = WindField(model.obstacles).shelter_factor(EAST, leaf_on=True)
    # Cell centres do not sit symmetrically about the walls, hence the tolerance.
    assert k_east[cell_at(model, -14, 0)] == pytest.approx(near, rel=0.1)
    assert k_east[cell_at(model, 14, 0)] == pytest.approx(K_BG)


def test_bare_crowns_shelter_less_than_crowns_in_leaf() -> None:
    model = scene(canopies=[square(0, 0, 10)])
    field = WindField(model.obstacles)
    lee = cell_at(model, 20, 0)
    in_leaf = field.shelter_factor(WEST, leaf_on=True)[lee]
    bare = field.shelter_factor(WEST, leaf_on=False)[lee]
    assert in_leaf < bare < K_BG
    under = cell_at(model, 0, 0)
    # Own crown at x = 0: deficit 0.7 × (1 − τ), τ = 0.2 in leaf.
    assert field.shelter_factor(WEST, leaf_on=True)[under] == pytest.approx(K_BG * (1 - 0.7 * 0.8), rel=0.02)


def test_frontal_area_depends_on_the_wind_direction() -> None:
    # A wall running east-west, then one running south-west to north-east.
    long_wall = scale(square(0, 0, 4), xfact=15, yfact=1)  # 120 m × 8 m, east-west
    ew = WindField(scene(buildings=[(long_wall, 10.0)]).obstacles)
    assert ew.morphometry(NORTH, True)["frontal_index"] > 5 * ew.morphometry(EAST, True)["frontal_index"]
    diagonal = WindField(scene(buildings=[(rotate(long_wall, 45, origin="centroid"), 10.0)]).obstacles)
    # Its long side faces north-west / south-east. The raster staircase along a
    # diagonal edge adds frontal area end-on, so the contrast is smaller.
    assert diagonal.morphometry(14, True)["frontal_index"] > 2 * diagonal.morphometry(2, True)["frontal_index"]


def test_wind_ms_scales_asos_speed_and_uses_the_season() -> None:
    model = scene(canopies=[square(0, 0, 10)])
    field = WindField(model.obstacles)
    under = cell_at(model, 0, 0)
    summer = field.wind_ms(3.0, 270, SUMMER)
    winter = field.wind_ms(3.0, 270, WINTER)
    assert summer[under] < winter[under]
    assert np.nanmax(summer[model.valid]) == pytest.approx(3.0 * K_BG)
    calm = field.wind_ms(0.3, 0, SUMMER)  # calm: mean over the sectors
    assert np.all(np.isfinite(calm))


# -- the 2D mass-consistent flow -------------------------------------------------


def _block_flow(solid: np.ndarray):
    flow = MassConsistentSolver(solid).solve(1.0, 0.0)  # west wind, unit speed
    u, v = flow.cell_velocity()
    return flow, u, v


def test_flow_round_a_block_has_no_divergence_and_no_flow_inside() -> None:
    solid = np.zeros((60, 80), dtype=bool)
    solid[25:35, 30:40] = True  # rows run south, columns east
    flow, u, v = _block_flow(solid)
    assert np.abs(flow.divergence()).max() < 1e-9
    assert np.abs(flow.east[:, 30:41][25:35]).max() == 0.0  # no flow through or inside the block
    assert np.abs(flow.south[25:36, 30:40]).max() == 0.0
    assert np.hypot(u, v)[solid].max() == 0.0
    # Far to the side of the block the wind is the initial one.
    assert u[2, 35] == pytest.approx(1.0, abs=0.03) and abs(v[2, 35]) < 0.03


def test_flow_turns_round_a_block_and_speeds_up_beside_it() -> None:
    solid = np.zeros((60, 80), dtype=bool)
    solid[25:35, 30:40] = True
    _, u, v = _block_flow(solid)
    speed = np.hypot(u, v)
    bearing = from_direction(u, v)
    # In front of the west wall the wind slows and turns: north of the
    # centre line it goes round the north side (from the south-west), south
    # of it round the south side (from the north-west).
    assert speed[30, 29] < 0.5
    assert bearing[26, 28] < 270 - 15
    assert bearing[33, 28] > 270 + 15
    # Beside the block it speeds up and blows along the wall again.
    assert speed[24, 35] > 1.2
    assert bearing[24, 35] == pytest.approx(270, abs=3)


def test_flow_speeds_up_through_a_passage() -> None:
    solid = np.zeros((60, 80), dtype=bool)
    solid[10:28, 30:40] = True
    solid[32:50, 30:40] = True  # a 4-cell passage running east-west
    _, u, v = _block_flow(solid)
    speed = np.hypot(u, v)
    assert speed[28:32, 35].min() > 1.5
    assert speed[28:32, 35].min() > speed[30, 5] * 1.5
    assert np.abs(v[28:32, 35]).max() < 0.05  # straight along the passage


def test_a_walled_in_courtyard_has_no_2d_flow() -> None:
    solid = np.zeros((40, 40), dtype=bool)
    solid[10:30, 10:30] = True
    solid[15:25, 15:25] = False  # courtyard
    solver = MassConsistentSolver(solid)
    assert solver.walled_in.sum() == 100
    u, v = solver.solve(1.0, 0.0).cell_velocity()
    assert np.hypot(u, v)[15:25, 15:25].max() == 0.0


def test_field_combines_flow_and_shelter_without_counting_the_lee_twice() -> None:
    # 10 m tall, 20 m wide; west wind.
    model = scene(buildings=[(square(0, 0, 10), 10.0)])
    field = WindField(model.obstacles)
    k, bearing = field.wind(270.0, leaf_on=True)
    shelter = field.shelter_factor(WEST, leaf_on=True)
    u, v, _ = field.flow(270.0)
    m = np.hypot(u, v) / K_BG
    lee = cell_at(model, 14, 0)
    # Both slow the lee; the stronger deficit counts, not their product.
    assert k[lee] == pytest.approx(K_BG * min(m[lee], shelter[lee] / K_BG), rel=1e-6)
    assert k[lee] > K_BG * m[lee] * shelter[lee] / K_BG
    # In front of the wall only the flow sees the slow-down; S says open.
    front = cell_at(model, -14, 0)
    assert shelter[front] == pytest.approx(K_BG)
    assert k[front] < 0.8 * K_BG
    # Beside the building the flow speeds up and turns back along the wall,
    # while round the front corners it turns away from the west.
    beside = cell_at(model, 0, 16)
    assert K_BG < k[beside] <= K_BG * SPEEDUP_MAX
    assert bearing[beside] == pytest.approx(270, abs=5)
    assert bearing[cell_at(model, -14, 8)] < 260
    assert bearing[cell_at(model, -14, -8)] > 280
    # Building cells are not valid: no value there.
    assert not np.isfinite(k[cell_at(model, 0, 0)])


def test_field_speeds_up_between_two_buildings() -> None:
    model = scene(buildings=[
        (scale(square(0, 18, 10), xfact=1, yfact=1.4), 10.0),
        (scale(square(0, -18, 10), xfact=1, yfact=1.4), 10.0),
    ])
    k, bearing = WindField(model.obstacles).wind(270.0, leaf_on=True)
    gap = cell_at(model, 0, 0)
    assert k[gap] > 1.2 * K_BG
    assert bearing[gap] == pytest.approx(270, abs=5)


def test_wind_for_other_directions_rotates_with_it() -> None:
    model = scene(buildings=[(square(0, 0, 10), 10.0)])
    field = WindField(model.obstacles)
    k_west, _ = field.wind(270.0, leaf_on=True)
    k_south, bearing_south = field.wind(180.0, leaf_on=True)
    # A square building: beside it for a west wind is north of it, for a south
    # wind east of it. Cell centres do not sit symmetrically about the walls,
    # hence the tolerance.
    assert k_south[cell_at(model, 16, 0)] == pytest.approx(k_west[cell_at(model, 0, 16)], rel=0.1)
    assert k_south[cell_at(model, 16, 0)] > K_BG
    assert np.nanmedian(bearing_south) == pytest.approx(180, abs=1)
    calm = field.factor(None, leaf_on=True)
    assert np.all(np.isfinite(calm[model.valid]))


def test_arrows_follow_the_cell_wind_and_skip_buildings() -> None:
    model = scene(buildings=[(square(0, 0, 20), 10.0)])
    field = WindField(model.obstacles)
    points = arrow_features(field, 3.0, 270.0, SUMMER, step_cells=1)
    k, bearing = field.wind(270.0, leaf_on=True)
    assert len(points) == int(model.valid.sum())
    assert len(points) < int(model.inside.sum())  # the building's cells are left out
    directions = [p["properties"]["direction_deg"] for p in points]
    assert all(0 < d <= 360 for d in directions)
    assert min(directions) < 250 and max(directions) > 290
    fastest = max(points, key=lambda p: p["properties"]["factor"])["properties"]
    assert fastest["factor"] > K_BG
    assert fastest["speed_ms"] == pytest.approx(3.0 * fastest["factor"], abs=0.01)
    assert arrow_features(field, 0.2, 270.0, SUMMER, step_cells=1) == []  # calm
