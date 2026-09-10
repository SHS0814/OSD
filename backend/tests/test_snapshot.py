import json
from pathlib import Path

from shapely.geometry import shape


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_cbnu_snapshot_integrity() -> None:
    collection = json.loads((DATA_DIR / "cbnu_buildings.geojson").read_text())
    features = collection["features"]

    assert len(features) == 117
    assert len({feature["properties"]["osm_id"] for feature in features}) == 117
    assert all(shape(feature["geometry"]).is_valid for feature in features)
    assert all(
        feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}
        for feature in features
    )
    for feature in features:
        properties = feature["properties"]
        if properties["height_m"] is not None:
            assert properties["source_height"] in {
                "OpenStreetMap:height",
                "VWorld:LT_C_BLDGINFO:height",
            }


def test_match_report_matches_snapshot_counts() -> None:
    collection = json.loads((DATA_DIR / "cbnu_buildings.geojson").read_text())
    report = json.loads((DATA_DIR / "cbnu_buildings_match_report.json").read_text())
    features = collection["features"]
    direct_heights = sum(
        feature["properties"]["height_m"] is not None for feature in features
    )

    assert report["output"]["building_count"] == len(features)
    assert report["output"]["direct_height_count"] == direct_heights
    assert report["output"]["missing_height_count"] == len(features) - direct_heights
    assert report["matching"]["accepted_count"] == len(report["matching"]["accepted"])
    matched_osm_ids = [item["osm_id"] for item in report["matching"]["accepted"]]
    matched_vworld_ids = [item["vworld_id"] for item in report["matching"]["accepted"]]
    assert len(matched_osm_ids) == len(set(matched_osm_ids))
    assert len(matched_vworld_ids) == len(set(matched_vworld_ids))
    assert report["matching"]["height_conflict_count"] == len(
        report["matching"]["height_conflicts"]
    )
