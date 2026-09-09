import math

from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .geometry import iter_polygons


def calculate_shadow_length(building_height_m: float, solar_altitude_deg: float) -> float:
    if building_height_m < 0:
        raise ValueError("Building height must not be negative")
    if solar_altitude_deg <= 0:
        return 0.0
    return building_height_m / math.tan(math.radians(solar_altitude_deg))


def calculate_shadow_vector(shadow_length_m: float, solar_azimuth_deg: float) -> tuple[float, float]:
    """Return east/north displacement opposite the sun's clockwise-from-north azimuth."""
    shadow_azimuth = math.radians((solar_azimuth_deg + 180.0) % 360.0)
    return (
        shadow_length_m * math.sin(shadow_azimuth),
        shadow_length_m * math.cos(shadow_azimuth),
    )


def _swept_ring(coords: list[tuple[float, float]], dx: float, dy: float) -> list[Polygon]:
    quads: list[Polygon] = []
    for start, end in zip(coords, coords[1:]):
        quads.append(
            Polygon(
                [
                    start,
                    end,
                    (end[0] + dx, end[1] + dy),
                    (start[0] + dx, start[1] + dy),
                ]
            )
        )
    return quads


def create_shadow_polygon(
    projected_building: BaseGeometry,
    shadow_length_m: float,
    solar_azimuth_deg: float,
) -> BaseGeometry:
    if shadow_length_m <= 0:
        return projected_building.buffer(0)

    dx, dy = calculate_shadow_vector(shadow_length_m, solar_azimuth_deg)
    pieces: list[BaseGeometry] = [
        projected_building,
        affinity.translate(projected_building, xoff=dx, yoff=dy),
    ]
    for polygon in iter_polygons(projected_building):
        pieces.extend(_swept_ring(list(polygon.exterior.coords), dx, dy))
        for interior in polygon.interiors:
            pieces.extend(_swept_ring(list(interior.coords), dx, dy))
    return unary_union(pieces).buffer(0)

