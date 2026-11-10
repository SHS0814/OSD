"""Write where the campus sensors stand, for the API and the app's map.

The raw exports in data/raw/sensors/ are course data and stay uncommitted;
this keeps only each sensor's usual position and a summary of its record, so
the committed snapshot holds no readings.

    PYTHONPATH=backend python scripts/build_sensor_sites.py [data/raw/sensors]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from shapely.geometry import shape  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import sensors  # noqa: E402

# 실습 배정표 (2026-09-28 ~ 10-04): team -> sensor.
TEAMS = {
    "sensor 20": 1, "sensor 01": 2, "sensor 26": 3,
    "sensor 21": 4, "sensor 14": 5, "sensor 06": 6,
    "sensor 33": 7, "sensor 15": 8, "sensor 04": 9,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path, default=ROOT / "data" / "raw" / "sensors")
    args = parser.parse_args()

    collection = json.loads(settings.campus_boundary_path.read_text(encoding="utf-8"))
    campus = shape(collection["features"][0]["geometry"])
    flagged = sensors.flag_quality(sensors.load_directory(args.directory), campus)

    features = []
    for name, site in sensors.sites(flagged).iterrows():
        features.append(
            {
                "type": "Feature",
                "id": name,
                "geometry": {"type": "Point", "coordinates": [site["lon"], site["lat"]]},
                "properties": {
                    "sensor": name,
                    "team": TEAMS.get(name),
                    "start": site["start"].isoformat(timespec="seconds"),
                    "end": site["end"].isoformat(timespec="seconds"),
                    "readings": int(site["readings"]),
                    "temp_ok_pct": site["temp_ok_pct"],
                    "co2_ok_pct": site["co2_ok_pct"],
                },
            }
        )

    output = {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "충북대 환경 센서 네트워크 실습 데이터 (data/raw/sensors, 미커밋)",
            "position": "each sensor's most frequent reported lat/lon",
        },
        "features": features,
    }
    path = settings.sensors_data_path
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.name}: {', '.join(f['id'] for f in features)}")


if __name__ == "__main__":
    main()
