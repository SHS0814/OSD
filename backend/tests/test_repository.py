from pathlib import Path

from app.db.repository import BuildingRepository


def test_cbnu_geojson_loads_with_source_metadata() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "cbnu_buildings.geojson"
    buildings = BuildingRepository(None, sample_path).list_buildings()

    assert len(buildings) == 117
    assert buildings[0].geometry.geom_type == "Polygon"
    assert buildings[0].source_geometry == "OpenStreetMap"
    assert buildings[0].osm_type == "way"
    assert len({building.osm_id for building in buildings}) == 117
