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
    timezone: str = "Asia/Seoul"
    projected_crs: str = "EPSG:5179"
    # Point used for the sun position and the extraterrestrial radiation of the
    # whole campus; the site spans about 1 km, far too little to matter.
    campus_latitude: float = 36.6282
    campus_longitude: float = 127.4567


settings = Settings()
