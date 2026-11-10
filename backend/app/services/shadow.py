import math


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

