from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from shapely.geometry import mapping

from app.config import settings
from app.services.geometry import to_wgs84
from app.services.shadow import building_shadows
from app.services.solar import calculate_solar_position, parse_requested_datetime
from app.services.weather import WeatherUnavailable


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


@router.get("/api/weather/period")
def weather_period(request: Request) -> dict:
    """Range of the weather snapshot, so a client can pick a date it can ask about."""
    start, end = request.app.state.weather.period
    # The last date with all 24 hours observed.
    latest = end.date() if end.hour == 23 else end.date() - timedelta(days=1)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "latest_observation": end.isoformat(),
        "latest_full_date": latest.isoformat(),
        "realtime": settings.kma_apihub_key is not None,
        "station": "청주 ASOS (131)",
    }


@router.get("/api/microclimate")
def microclimate(
    request: Request,
    datetime_value: Annotated[datetime | None, Query(alias="datetime")] = None,
    date_value: Annotated[date | None, Query(alias="date")] = None,
    time_value: Annotated[time | None, Query(alias="time")] = None,
) -> dict:
    """Estimated UTCI (felt temperature) on a campus grid for one instant."""
    try:
        when = parse_requested_datetime(datetime_value, date_value, time_value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        weather = request.app.state.weather.at(when)
    except WeatherUnavailable as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    solar = calculate_solar_position(when, settings.campus_latitude, settings.campus_longitude)
    result = request.app.state.microclimate.compute(when, solar, weather)
    return {
        "datetime": when.isoformat(),
        "timezone": "Asia/Seoul",
        "solar": _solar_payload(solar),
        "weather": weather.as_dict(),
        **result,
        "note": "추정치입니다. v0은 건물 그림자와 천공률만 반영하며, 기온·습도·바람은 캠퍼스 전체에 같은 기상청 값을 씁니다.",
    }
