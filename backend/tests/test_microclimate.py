"""MicroclimateModel: geometry fields and comfort joined, with and without per-cell wind."""

from datetime import datetime

import numpy as np

from app.services.comfort import comfort_fields
from app.services.geometry import to_wgs84
from app.services.microclimate import MicroclimateModel
from app.services.solar import SEOUL_TZ, SolarPosition
from app.services.wind import WindField
from fakes import fixed_weather
from test_geometry_field import Block, cell_at, square

WHEN = datetime(2025, 8, 5, 14, tzinfo=SEOUL_TZ)
SUN = SolarPosition(altitude=60, azimuth=200)


def model_scene(buildings=()) -> MicroclimateModel:
    return MicroclimateModel(
        to_wgs84(square(0, 0, 150)),
        [Block(to_wgs84(geometry), height) for geometry, height in buildings],
    )


def test_fields_are_comfort_over_the_geometry_fields() -> None:
    model = model_scene(buildings=[(square(0, 0, 10), 15.0)])
    weather = fixed_weather()
    fields = model.fields(WHEN, SUN, weather)
    direct = comfort_fields(model.geometry.at(SUN, WHEN.date()), WHEN, SUN, weather, weather.wind_ms)
    assert np.array_equal(fields.utci, direct.utci, equal_nan=True)
    assert model.fields(WHEN, SUN, weather) is fields  # cached
    payload = model.compute(WHEN, SUN, weather)
    assert len(payload["utci"]) == model.grid.rows * model.grid.cols
    assert payload["summary"]["cell_count"] == int(model.valid.sum())
    assert payload["inputs"] == {"terrain": False, "canopy_share": 0.0, "in_leaf": True, "wind_field": False}


def test_fields_keep_uniform_wind_unless_asked() -> None:
    model = model_scene(buildings=[(square(0, 0, 10), 15.0)])
    weather = fixed_weather(wind_ms=4.0)
    uniform = model.fields(WHEN, SUN, weather).utci
    # Attaching a field changes nothing until a direction is passed.
    model.wind_field = WindField(model.obstacles)
    assert np.array_equal(model.fields(WHEN, SUN, weather).utci, uniform, equal_nan=True)
    per_cell = model.fields(WHEN, SUN, weather, wind_direction_deg=270).utci
    lee, upwind = cell_at(model, 16, 0), cell_at(model, -60, 0)
    # Less wind on a hot afternoon feels hotter, most of all in the lee.
    assert per_cell[upwind] > uniform[upwind]
    assert per_cell[lee] - uniform[lee] > per_cell[upwind] - uniform[upwind]
    model.wind_field = None
    assert np.array_equal(model.fields(WHEN, SUN, weather, wind_direction_deg=270).utci, uniform, equal_nan=True)
