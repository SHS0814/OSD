"""Walkable ways on and around campus, from OpenStreetMap, for shade-aware routing.

Every OSM way tagged highway=* near the campus that a pedestrian may use goes
in: sidewalks and crossings (footway), paths, steps, campus service roads and
the streets around the campus. Motorways, ways under construction and ways
closed to pedestrians are left out. Only the largest connected piece is kept,
since a parking aisle that touches nothing else cannot be routed to anyway.

    python scripts/build_walk_network.py
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import shape

from osm_common import overpass

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_PATH = DATA_DIR / "cbnu_walk_network.geojson"
MARGIN_DEG = 0.0015  # ~150 m around the campus, for the sidewalks of the streets bounding it

EXCLUDED = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "construction", "proposed", "abandoned", "platform", "bus_stop", "rest_area", "raceway",
}
CLOSED = {"no", "private"}


def walkable(tags: dict) -> bool:
    return (
        tags.get("highway") not in EXCLUDED
        and tags.get("access") not in CLOSED
        and tags.get("foot") not in CLOSED
        and tags.get("area") != "yes"
    )


def key(lon: float, lat: float) -> tuple[float, float]:
    return round(lon, 7), round(lat, 7)


def largest_component(ways: list[dict]) -> list[dict]:
    parent: dict = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for way in ways:
        nodes = [key(*point) for point in way["coords"]]
        for a, b in zip(nodes, nodes[1:]):
            parent[find(a)] = find(b)
    sizes = Counter(find(key(*way["coords"][0])) for way in ways)
    biggest = sizes.most_common(1)[0][0]
    return [way for way in ways if find(key(*way["coords"][0])) == biggest]


def main() -> None:
    boundary = shape(json.loads((DATA_DIR / "cbnu_campus_boundary.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
    west, south, east, north = boundary.bounds
    west, south, east, north = west - MARGIN_DEG, south - MARGIN_DEG, east + MARGIN_DEG, north + MARGIN_DEG
    payload = overpass(f'[out:json][timeout:120];way["highway"]({south},{west},{north},{east});out geom tags;')

    ways = []
    for element in payload["elements"]:
        tags = element.get("tags", {})
        if not walkable(tags):
            continue
        coords = [(point["lon"], point["lat"]) for point in element["geometry"]]
        if len(coords) >= 2:
            ways.append({"id": element["id"], "highway": tags["highway"], "name": tags.get("name"), "coords": coords})
    kept = largest_component(ways)
    print(f"{len(ways)} walkable ways, {len(kept)} in the largest connected network")

    features = [
        {
            "type": "Feature",
            "id": way["id"],
            "geometry": {"type": "LineString", "coordinates": [[round(x, 7), round(y, 7)] for x, y in way["coords"]]},
            "properties": {"osm_id": way["id"], "highway": way["highway"], "name": way["name"]},
        }
        for way in kept
    ]
    output = {
        "type": "FeatureCollection",
        "name": "cbnu_walk_network",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "OpenStreetMap contributors (ODbL), Overpass API",
            "area": f"campus bounding box + {MARGIN_DEG}°",
            "kept": "walkable highway=* ways, largest connected piece only",
        },
        "features": features,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.name}: {len(features)} ways")


if __name__ == "__main__":
    main()
