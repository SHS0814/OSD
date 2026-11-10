from collections.abc import Iterable

from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


WGS84 = "EPSG:4326"
CBNU_PROJECTED = "EPSG:5179"


def transform_geometry(
    geometry: BaseGeometry,
    source_crs: str,
    target_crs: str,
) -> BaseGeometry:
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(transformer.transform, geometry)


def to_projected(geometry: BaseGeometry) -> BaseGeometry:
    return transform_geometry(geometry, WGS84, CBNU_PROJECTED)


def to_wgs84(geometry: BaseGeometry) -> BaseGeometry:
    return transform_geometry(geometry, CBNU_PROJECTED, WGS84)


def iter_polygons(geometry: BaseGeometry) -> Iterable[BaseGeometry]:
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms
    else:
        raise ValueError(f"Expected Polygon or MultiPolygon, got {geometry.geom_type}")

