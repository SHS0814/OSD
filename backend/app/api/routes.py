from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from shapely.geometry import mapping

from app.services.geometry import to_projected, to_wgs84
from app.services.shadow import calculate_shadow_length, create_shadow_polygon
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
    features: list[dict] = []
    if solar.altitude > 0:
        for building in request.app.state.buildings.list_buildings():
            length = calculate_shadow_length(building.height_m, solar.altitude)
            shadow = create_shadow_polygon(
                to_projected(building.geometry), length, solar.azimuth
            )
            features.append(
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
            )

    return {
        "datetime": when.isoformat(),
        "timezone": "Asia/Seoul",
        "solar": {
            "altitude": round(solar.altitude, 6),
            "azimuth": round(solar.azimuth, 6),
        },
        "shadows": feature_collection(features),
    }

