from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str | None = os.getenv("DATABASE_URL")
    building_data_path: Path = Path(
        os.getenv(
            "BUILDING_DATA_PATH",
            Path(__file__).resolve().parents[2] / "data" / "sample_buildings.geojson",
        )
    )
    timezone: str = "Asia/Seoul"
    projected_crs: str = "EPSG:5179"


settings = Settings()
