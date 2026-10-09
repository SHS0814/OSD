"""Tree crowns on campus, traced automatically from VWorld aerial imagery.

The 환경부 land cover map (1:5,000) misses most campus trees: small stands,
rows along roads and trees in courtyards come out as grass or "paved", so the
model put every campus sensor in open sun even where it hangs in a wood. This
fetches VWorld's aerial photo tiles over the campus, finds tree crowns in them
and writes them as polygons the model reads like street trees.

A crown is a pixel that is green, darker than lawn and rough: in the summer
photos lawn is a smooth, lighter green (local SD ~2 and value ~95-115) while
crowns are dark with sunlit and shaded leaves side by side (SD 4-10, value
70-85). Building footprints are masked out, since green roofs pass the same
test. Heights cannot be seen from above, so they come from crown size.

Tiles are cached in data/raw/vworld_satellite/ (not committed); the output is
data/cbnu_tree_canopy.geojson.

    VWORLD_API_KEY=... VWORLD_DOMAIN=... python scripts/build_tree_canopy.py
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import shapely
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TILE_DIR = DATA_DIR / "raw" / "vworld_satellite"
OUTPUT_PATH = DATA_DIR / "cbnu_tree_canopy.geojson"

ZOOM = 19  # ~0.24 m per pixel at the campus latitude
TILE = 256
PAD_M = 120.0  # imagery fetched beyond the campus, so filters see whole crowns at the edge
# Crowns are kept only this far beyond the campus: a 13 m tree shades about
# 20 m at a 30° sun, and further out only campus buildings are masked, so the
# green roofs of the neighbourhood would pass as trees.
KEEP_M = 30.0

# Classification, tuned on the nine sensor sites (see the module docstring).
MIN_EXCESS_GREEN = 0.04  # (2G - R - B) / (R + G + B), smoothed over ~1.7 m
MAX_VALUE = 90.0  # mean of R, G, B, smoothed over ~2 m
MIN_TEXTURE = 3.5  # SD of the value over ~3 m
MIN_CROWN_M2 = 9.0
# Gaps inside a crown up to this size are sun flecks or dark leaves and get
# filled; anything larger (a lawn or plaza ringed by trees) stays open.
MAX_GAP_M2 = 30.0
BUILDING_MARGIN_M = 1.0
SIMPLIFY_M = 0.6

# Height from crown area: single young trees, mature trees, stands.
HEIGHT_BY_AREA = [(40.0, 7.0), (300.0, 10.0), (math.inf, 13.0)]


def load_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip() or None
    return None


def world_pixel(lon: float, lat: float) -> tuple[float, float]:
    n = 2**ZOOM * TILE
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def lonlat(x, y):
    n = 2**ZOOM * TILE
    lon = np.asarray(x) / n * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * np.asarray(y) / n))))
    return lon, lat


def fetch_tile(key: str, domain: str, x: int, y: int) -> Path:
    path = TILE_DIR / str(ZOOM) / str(y) / f"{x}.jpeg"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{ZOOM}/{y}/{x}.jpeg"
        subprocess.run(
            ["curl", "-s", "--fail", "--max-time", "30", "-H", f"Referer: {domain}", "-o", str(path), url],
            check=True,
        )
    return path


def mosaic(key: str, domain: str, west: float, south: float, east: float, north: float):
    x0, y0 = world_pixel(west, north)
    x1, y1 = world_pixel(east, south)
    tx0, ty0, tx1, ty1 = int(x0 // TILE), int(y0 // TILE), int(x1 // TILE), int(y1 // TILE)
    tiles = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        paths = list(pool.map(lambda t: fetch_tile(key, domain, *t), tiles))
    image = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE))
    for (tx, ty), path in zip(tiles, paths):
        image.paste(Image.open(path).convert("RGB"), ((tx - tx0) * TILE, (ty - ty0) * TILE))
    print(f"  {len(tiles)} tiles, {image.width}x{image.height} px")
    return np.asarray(image, dtype=np.float32), (tx0 * TILE, ty0 * TILE)


def metres_per_pixel(lat: float) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / 2**ZOOM


def window(metres: float, pixel_m: float) -> int:
    return max(3, int(round(metres / pixel_m)) | 1)


def building_mask(shape_hw, origin, pixel_m) -> np.ndarray:
    collection = json.loads((DATA_DIR / "cbnu_buildings.geojson").read_text(encoding="utf-8"))
    canvas = Image.new("L", (shape_hw[1], shape_hw[0]), 0)
    draw = ImageDraw.Draw(canvas)
    for feature in collection["features"]:
        geometry = shape(feature["geometry"])
        for polygon in getattr(geometry, "geoms", [geometry]):
            points = [world_pixel(lon, lat) for lon, lat in polygon.exterior.coords]
            draw.polygon([(x - origin[0], y - origin[1]) for x, y in points], fill=1)
    mask = np.asarray(canvas, dtype=bool)
    return ndi.binary_dilation(mask, iterations=max(1, int(BUILDING_MARGIN_M / pixel_m)))


def crowns(rgb: np.ndarray, buildings: np.ndarray, pixel_m: float) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    total = r + g + b + 1e-6
    value = total / 3.0
    excess_green = ndi.uniform_filter((2 * g - r - b) / total, window(1.7, pixel_m))
    texture_window = window(3.0, pixel_m)
    mean = ndi.uniform_filter(value, texture_window)
    texture = np.sqrt(np.maximum(ndi.uniform_filter(value * value, texture_window) - mean * mean, 0))
    dark = ndi.uniform_filter(value, window(2.0, pixel_m)) < MAX_VALUE
    tree = (excess_green > MIN_EXCESS_GREEN) & dark & (texture > MIN_TEXTURE) & ~buildings
    del r, g, b, total, value, excess_green, mean, texture, dark

    step = max(1, int(round(0.5 / pixel_m)))
    tree = ndi.binary_opening(tree, iterations=2 * step)
    tree = ndi.binary_closing(tree, iterations=4 * step)
    holes = ndi.binary_fill_holes(tree) & ~tree
    labels, count = ndi.label(holes)
    sizes = ndi.sum(holes, labels, range(1, count + 1)) * pixel_m * pixel_m
    tree = (tree | np.isin(labels, np.nonzero(sizes <= MAX_GAP_M2)[0] + 1)) & ~buildings
    labels, count = ndi.label(tree)
    sizes = ndi.sum(tree, labels, range(1, count + 1)) * pixel_m * pixel_m
    return np.isin(labels, np.nonzero(sizes >= MIN_CROWN_M2)[0] + 1)


def polygons(mask: np.ndarray, origin, pixel_m: float):
    """Mask -> WGS84 polygons, via 1 m runs along each row merged together."""
    factor = max(1, int(round(1.0 / pixel_m)))
    rows, cols = mask.shape[0] // factor, mask.shape[1] // factor
    coarse = mask[: rows * factor, : cols * factor].reshape(rows, factor, cols, factor).mean(axis=(1, 3)) >= 0.5
    boxes = []
    for row in range(rows):
        line = coarse[row]
        edges = np.flatnonzero(np.diff(np.concatenate([[0], line.astype(np.int8), [0]])))
        for start, stop in zip(edges[::2], edges[1::2]):
            boxes.append(shapely.box(start * factor, row * factor, stop * factor, (row + 1) * factor))
    merged = shapely.union_all(boxes)

    def to_lonlat(x, y, z=None):
        return lonlat(np.asarray(x) + origin[0], np.asarray(y) + origin[1])

    merged = transform(to_lonlat, merged)
    # Simplify in degrees: SIMPLIFY_M at this latitude.
    merged = merged.simplify(SIMPLIFY_M / 111_000.0, preserve_topology=True)
    return [p for p in getattr(merged, "geoms", [merged]) if not p.is_empty]


def height_for(area_m2: float) -> float:
    return next(height for limit, height in HEIGHT_BY_AREA if area_m2 < limit)


def main() -> None:
    key, domain = load_env("VWORLD_API_KEY"), load_env("VWORLD_DOMAIN") or "http://localhost"
    if not key:
        raise SystemExit("VWORLD_API_KEY is not set (see .env.example)")

    boundary = shape(json.loads((DATA_DIR / "cbnu_campus_boundary.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
    west, south, east, north = boundary.bounds
    lat0 = (south + north) / 2
    pad_lat = PAD_M / 110_540.0
    pad_lon = PAD_M / (111_320.0 * math.cos(math.radians(lat0)))
    print("fetching VWorld aerial tiles")
    rgb, origin = mosaic(key, domain, west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat)
    pixel_m = metres_per_pixel(lat0)

    print("finding crowns")
    mask = crowns(rgb, building_mask(rgb.shape[:2], origin, pixel_m), pixel_m)
    del rgb
    print(f"  crown share of the area: {mask.mean():.1%}")

    keep = boundary.buffer(KEEP_M / 111_000.0)
    features = []
    for polygon in polygons(mask, origin, pixel_m):
        polygon = polygon.intersection(keep)
        area = polygon.area * 111_320.0 * math.cos(math.radians(lat0)) * 110_540.0
        if polygon.is_empty or area < MIN_CROWN_M2:
            continue
        features.append(
            {
                "type": "Feature",
                # 6 decimals is ~0.1 m, well under the 2 m raster the model uses.
                "geometry": mapping(shapely.set_precision(polygon, 1e-6)),
                "properties": {"leaf": "broadleaf", "height_m": height_for(area), "area_m2": round(area, 1)},
            }
        )
    output = {
        "type": "FeatureCollection",
        "name": "cbnu_tree_canopy",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "VWorld 항공사진 (WMTS Satellite, zoom 19)에서 자동 추출",
            "method": "green, darker than lawn and rough; building footprints masked; see scripts/build_tree_canopy.py",
            "height": "guessed from crown area: <40 m² 7 m, <300 m² 10 m, else 13 m",
            "leaf": "all broadleaf: conifers cannot be told apart reliably from the photo",
            "area": f"campus boundary + {KEEP_M:.0f} m",
            "limits": "dark lawn in building shadow can pass as crown; crowns over roads are cut where the photo shows the road",
        },
        "features": features,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(f["properties"]["area_m2"] for f in features)
    print(f"wrote {OUTPUT_PATH.name}: {len(features)} crowns, {total / 10_000:.1f} ha")


if __name__ == "__main__":
    main()
