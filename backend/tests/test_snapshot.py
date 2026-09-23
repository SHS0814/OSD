import json
from pathlib import Path

from shapely.geometry import shape


DATA_DIR = Path(__file__).resolve().parents[2] / "data"

BUILDING_COUNT = 105
HEIGHT_SOURCES = {
    "건축물대장:heit",
    "건축물대장:heit(단지)",
    "OpenStreetMap:height",
}
DIRECT_HEIGHT_COUNT = 64


def load_snapshot() -> list[dict]:
    collection = json.loads((DATA_DIR / "cbnu_buildings.geojson").read_text())
    return collection["features"]


def test_cbnu_snapshot_integrity() -> None:
    features = load_snapshot()

    assert len(features) == BUILDING_COUNT
    assert len({feature["properties"]["osm_id"] for feature in features}) == BUILDING_COUNT
    assert all(shape(feature["geometry"]).is_valid for feature in features)
    assert all(
        feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}
        for feature in features
    )
    for feature in features:
        properties = feature["properties"]
        if properties["height_m"] is not None:
            assert properties["height_m"] > 0
            assert properties["source_height"] in HEIGHT_SOURCES
        else:
            assert properties["source_height"] is None


def test_level_counts_are_recorded_but_never_converted() -> None:
    """A building with only building:levels must stay height-less.

    Converting levels to metres would put an estimate on the map that looks
    exactly like a surveyed height, so the snapshot keeps the raw tag instead.
    """
    features = load_snapshot()
    levels_only = [
        feature["properties"]
        for feature in features
        if feature["properties"]["height_m"] is None
        and (
            feature["properties"]["building_levels"] is not None
            or feature["properties"]["ledger_floors"] is not None
        )
    ]

    assert levels_only, "expected some buildings to carry only a level count"
    assert all(properties["source_height"] is None for properties in levels_only)


def test_all_buildings_lie_inside_the_campus_boundary() -> None:
    boundary = shape(
        json.loads((DATA_DIR / "cbnu_campus_boundary.geojson").read_text())["features"][0]["geometry"]
    )

    assert boundary.is_valid
    for feature in load_snapshot():
        point = shape(feature["geometry"]).representative_point()
        assert boundary.contains(point), feature["properties"]["name"]


def test_match_report_matches_snapshot_counts() -> None:
    features = load_snapshot()
    report = json.loads((DATA_DIR / "cbnu_buildings_match_report.json").read_text())
    direct_heights = sum(
        feature["properties"]["height_m"] is not None for feature in features
    )

    assert direct_heights == DIRECT_HEIGHT_COUNT
    assert report["output"]["building_count"] == len(features)
    assert report["output"]["direct_height_count"] == direct_heights
    assert report["output"]["missing_height_count"] == len(features) - direct_heights
    assert report["matching"]["accepted_count"] == len(report["matching"]["accepted"])
    assert report["matching"]["height_conflict_count"] == len(
        report["matching"]["height_conflicts"]
    )


def test_report_records_how_many_buildings_lack_any_height_clue() -> None:
    features = load_snapshot()
    report = json.loads((DATA_DIR / "cbnu_buildings_match_report.json").read_text())
    availability = report["height_availability"]

    levels_only = sum(
        feature["properties"]["height_m"] is None
        and (
            feature["properties"]["building_levels"] is not None
            or feature["properties"]["ledger_floors"] is not None
        )
        for feature in features
    )
    no_clue = sum(
        feature["properties"]["height_m"] is None
        and feature["properties"]["building_levels"] is None
        and feature["properties"]["ledger_floors"] is None
        for feature in features
    )

    assert availability["direct_height"] == DIRECT_HEIGHT_COUNT
    assert availability["levels_only_not_converted"] == levels_only
    assert availability["no_height_and_no_levels"] == no_clue
    assert (
        availability["direct_height"]
        + availability["levels_only_not_converted"]
        + availability["no_height_and_no_levels"]
        == len(features)
    )
