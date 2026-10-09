from dataclasses import dataclass
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _data_path(env_name: str, filename: str) -> Path:
    return Path(os.getenv(env_name, DATA_DIR / filename))


@dataclass(frozen=True)
class Settings:
    database_url: str | None = os.getenv("DATABASE_URL")
    building_data_path: Path = _data_path("BUILDING_DATA_PATH", "cbnu_buildings.geojson")
    campus_boundary_path: Path = _data_path("CAMPUS_BOUNDARY_PATH", "cbnu_campus_boundary.geojson")
    weather_data_path: Path = _data_path("WEATHER_DATA_PATH", "kma_asos_131_hourly.csv")
    terrain_data_path: Path = _data_path("TERRAIN_DATA_PATH", "cbnu_dtm_5m.npz")
    landcover_data_path: Path = _data_path("LANDCOVER_DATA_PATH", "cbnu_landcover.geojson")
    street_trees_data_path: Path = _data_path("STREET_TREES_DATA_PATH", "cbnu_street_trees.geojson")
    tree_canopy_data_path: Path = _data_path("TREE_CANOPY_DATA_PATH", "cbnu_tree_canopy.geojson")
    walk_network_data_path: Path = _data_path("WALK_NETWORK_DATA_PATH", "cbnu_walk_network.geojson")
    sensors_data_path: Path = _data_path("SENSORS_DATA_PATH", "cbnu_sensors.geojson")
    # 기상청 API허브 key; without it the weather stays at the committed snapshot.
    kma_apihub_key: str | None = os.getenv("KMA_APIHUB_KEY") or None
    # VWorld key for the satellite base map; without it only cached tiles are served.
    vworld_api_key: str | None = os.getenv("VWORLD_API_KEY") or None
    vworld_domain: str = os.getenv("VWORLD_DOMAIN") or "http://localhost"
    satellite_cache_dir: Path = Path(os.getenv("SATELLITE_CACHE_DIR", DATA_DIR / "raw" / "vworld_satellite"))
    weather_refresh_seconds: int = int(os.getenv("WEATHER_REFRESH_SECONDS", "300"))
    timezone: str = "Asia/Seoul"
    projected_crs: str = "EPSG:5179"
    # Point used for the sun position and the extraterrestrial radiation of the
    # whole campus; the site spans about 1 km, far too little to matter.
    campus_latitude: float = 36.6282
    campus_longitude: float = 127.4567


settings = Settings()
