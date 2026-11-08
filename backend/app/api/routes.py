from datetime import date, datetime, time, timedelta
from typing import Annotated

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request, Response
from shapely.geometry import mapping

from app.config import settings
from app.services import routing, vworld_tiles, wind
from app.services.geometry import to_wgs84
from app.services.microclimate import CELL_M
from app.services.shadow import building_shadows
from app.services.solar import SEOUL_TZ, calculate_solar_position, localize_datetime, parse_requested_datetime
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


@router.get("/api/sensors")
def sensor_sites(request: Request) -> dict:
    """Where the campus environment sensors stand; positions only, no readings."""
    return request.app.state.sensors


@router.get("/api/route")
def walking_route(
    request: Request,
    from_lat: Annotated[float, Query(ge=-90, le=90)],
    from_lon: Annotated[float, Query(ge=-180, le=180)],
    to_lat: Annotated[float, Query(ge=-90, le=90)],
    to_lon: Annotated[float, Query(ge=-180, le=180)],
    datetime_value: Annotated[datetime | None, Query(alias="datetime")] = None,
    date_value: Annotated[date | None, Query(alias="date")] = None,
    time_value: Annotated[time | None, Query(alias="time")] = None,
) -> dict:
    """Shortest, balanced and coolest walking routes for one instant.

    Balanced and coolest are left out when they coincide with a route already
    given, when the weather is comfortable everywhere, and at night, when sun
    and shade make no difference. ``mode`` says what the alternatives seek:
    "heat" - shade (그늘길), "cold" - sun (햇볕길), "none" - only the shortest.
    """
    network = request.app.state.walk_network
    if network is None:
        raise HTTPException(status_code=503, detail="walk network is not built (scripts/build_walk_network.py)")
    try:
        when = parse_requested_datetime(datetime_value, date_value, time_value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        weather = request.app.state.weather.at(when)
    except WeatherUnavailable as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    model = request.app.state.microclimate
    solar = calculate_solar_position(when, settings.campus_latitude, settings.campus_longitude)
    fields = model.fields(when, solar, weather, wind_direction_deg=weather.wind_direction_deg)
    utci = network.sample(model.fill_under_buildings(fields.utci), model.grid)
    sunlit = network.sample(model.fill_under_buildings(fields.sunlit), model.grid)
    try:
        start, end = network.snap(from_lon, from_lat), network.snap(to_lon, to_lat)
        heat_base = float(np.nanpercentile(fields.utci, routing.SHADE_PERCENTILE))
        cold_base = float(np.nanpercentile(fields.utci, routing.SUN_PERCENTILE))
        found = network.routes(
            start, end, utci, heat_base=heat_base, cold_base=cold_base, daylight=solar.altitude > 0
        )
    except routing.RouteUnavailable as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    shortest_m = float(network.length[found[0].edges].sum())
    return {
        "datetime": when.isoformat(),
        "timezone": "Asia/Seoul",
        "solar": _solar_payload(solar),
        "air_temp_c": round(weather.air_temp_c, 1),
        "mode": found[0].mode,
        "routes": feature_collection([network.describe(route, utci, sunlit, shortest_m) for route in found]),
        "note": "보행 속도 1.2 m/s 기준. mode가 heat이면 그늘길, cold이면 햇볕길이며, "
        "coolest는 최단 경로보다 최대 30%, balanced는 15%까지 길어질 수 있습니다. "
        "none이면 쾌적하거나 밤이라 최단 경로만 줍니다.",
    }


@router.get("/api/tiles/satellite/{z}/{x}/{y}.jpeg")
def satellite_tile(z: int, x: int, y: int) -> Response:
    """VWorld aerial photo tile for the app's base map (campus area only)."""
    try:
        data = vworld_tiles.get_tile(
            settings.vworld_api_key, settings.vworld_domain, settings.satellite_cache_dir, z, x, y
        )
    except vworld_tiles.TileUnavailable as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(status_code=502, detail="VWorld tile request failed") from error
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


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


@router.get("/api/weather")
def weather_now(
    request: Request,
    datetime_value: Annotated[datetime | None, Query(alias="datetime")] = None,
) -> dict:
    """ASOS weather for one instant (default: now), for the app's weather card.

    When "now" is past what has been observed (no API허브 key, or the hour is
    not reported yet), the latest observation is returned and ``latest`` says so.
    """
    store = request.app.state.weather
    when = localize_datetime(datetime_value) if datetime_value is not None else datetime.now(SEOUL_TZ)
    latest = False
    try:
        weather = store.at(when)
    except WeatherUnavailable:
        if datetime_value is not None:
            raise HTTPException(status_code=404, detail=f"no observation around {when.isoformat()}")
        when, latest = store.latest, True
        weather = store.at(when)
    solar = calculate_solar_position(when, settings.campus_latitude, settings.campus_longitude)
    return {
        "datetime": when.isoformat(),
        "latest": latest,
        "solar": _solar_payload(solar),
        "weather": weather.as_dict(),
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
    result = request.app.state.microclimate.compute(
        when, solar, weather, wind_direction_deg=weather.wind_direction_deg
    )
    return {
        "datetime": when.isoformat(),
        "timezone": "Asia/Seoul",
        "solar": _solar_payload(solar),
        "weather": weather.as_dict(),
        **result,
        "note": "추정치입니다. 그림자·천공률·지표면을 반영하고, 기온·습도는 캠퍼스 전체에 같은 기상청 값을, "
        "바람은 기상청 값에 칸별 풍속을 추정해(바람 위쪽 차폐 + 건물을 돌아가는 2D 질량보존 흐름; "
        "건물 위로 넘는 흐름·후류 역류 미반영, 풍속계 검증 없음) 씁니다.",
    }


@router.get("/api/wind")
def wind_arrows(
    request: Request,
    datetime_value: Annotated[datetime | None, Query(alias="datetime")] = None,
    date_value: Annotated[date | None, Query(alias="date")] = None,
    time_value: Annotated[time | None, Query(alias="time")] = None,
    step_m: Annotated[float, Query(ge=8)] = 24.0,
) -> dict:
    """Per-cell wind as points for drawing arrows, every ``step_m`` over open campus ground.

    Each point's ``direction_deg`` is where the wind blows *from* at that cell
    (ASOS convention, north 360) and ``factor`` its speed over the ASOS speed;
    an arrow points the other way. Both are estimates: a 2D mass-consistent
    flow round the buildings plus upwind sheltering, without flow over the
    roofs or reversed flow in a wake, and not checked against an anemometer.
    No point is placed on a cell that is mostly building. ``wind`` holds the
    ASOS values. No points when the wind field is off or the wind is calm.
    """
    try:
        when = parse_requested_datetime(datetime_value, date_value, time_value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        weather = request.app.state.weather.at(when)
    except WeatherUnavailable as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    model = request.app.state.microclimate
    field = model.wind_field
    direction = weather.wind_direction_deg
    features = []
    if field is not None and direction is not None:
        step_cells = max(1, round(step_m / CELL_M))
        features = wind.arrow_features(model, field, weather.wind_ms, direction, when.date(), step_cells)
    return {
        "type": "FeatureCollection",
        "datetime": when.isoformat(),
        "timezone": "Asia/Seoul",
        "wind": {
            "asos_speed_ms": round(weather.wind_ms, 2),
            "direction_deg": None if direction is None else round(direction, 1),
            "wind_field": field is not None,
        },
        "features": features,
        "note": "칸별 풍향·풍속은 2D 질량보존 흐름(건물을 돌아감)과 바람 위쪽 차폐로 추정한 값입니다. "
        "건물 위로 넘는 흐름·후류의 역류는 반영하지 않았고 풍속계로 검증하지 않았습니다.",
    }
