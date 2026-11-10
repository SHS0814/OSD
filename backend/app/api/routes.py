from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from shapely.geometry import mapping

from app.config import settings
from app.services.geometry import to_wgs84
from app.services.shadow import building_shadows
from app.services.solar import calculate_solar_position, parse_requested_datetime


router = APIRouter()


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/buildings")
def buildings(request: Request) -> dict:
    records = request.app.state.buildings.list_buildings()
    return feature_collection(
        [
            {
                "type": "Feature",
                "id": building.id,
                "geometry": mapping(building.geometry),
                "properties": building.properties(),
            }
            for building in records
        ]
    )


@router.get("/api/shadows")
def shadows(
    request: Request,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    datetime_value: Annotated[datetime | None, Query(alias="datetime")] = None,
    date_value: Annotated[date | None, Query(alias="date")] = None,
    time_value: Annotated[time | None, Query(alias="time")] = None,
) -> dict:
    try:
        when = parse_requested_datetime(datetime_value, date_value, time_value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    solar = calculate_solar_position(when, lat, lon)
    records = request.app.state.buildings.list_buildings()
    eligible_records = [building for building in records if building.height_m is not None]
    features = [
        {
            "type": "Feature",
            "id": building.id,
            "geometry": mapping(to_wgs84(shadow)),
            "properties": {
                "building_id": building.id,
                "building_name": building.name,
                "building_height": building.height_m,
                "shadow_length": round(length, 3),
                "solar_altitude": round(solar.altitude, 6),
                "solar_azimuth": round(solar.azimuth, 6),
            },
        }
        for building, length, shadow in building_shadows(records, solar)
    ]

    return {
        "datetime": when.isoformat(),
        "timezone": "Asia/Seoul",
        "solar": _solar_payload(solar),
        "building_count": len(records),
        "eligible_building_count": len(eligible_records),
        "shadow_building_count": len(features),
        "skipped_missing_height": len(records) - len(eligible_records),
        "shadows": feature_collection(features),
    }


def _solar_payload(solar) -> dict:
    return {
        "altitude": round(solar.altitude, 6),
        "azimuth": round(solar.azimuth, 6),
    }
