from pathlib import Path

from app.db.repository import BuildingRepository


def test_sample_geojson_loads_with_source_metadata() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample_buildings.geojson"
    buildings = BuildingRepository(None, sample_path).list_buildings()

    assert len(buildings) == 8
    assert buildings[0].geometry.geom_type == "Polygon"
    assert buildings[0].source_geometry == "manual-mvp"
    assert buildings[0].source_height == "manual-estimate"
