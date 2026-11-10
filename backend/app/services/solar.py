from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import azimuth, elevation


SEOUL_TZ = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class SolarPosition:
    altitude: float
    azimuth: float


def localize_datetime(value: datetime) -> datetime:
    """Return an Asia/Seoul aware datetime, preserving the represented instant."""
    if value.tzinfo is None:
        return value.replace(tzinfo=SEOUL_TZ)
    return value.astimezone(SEOUL_TZ)


def parse_requested_datetime(
    datetime_value: datetime | None,
    date_value: date | None,
    time_value: time | None,
) -> datetime:
    if datetime_value is not None:
        return localize_datetime(datetime_value)
    if date_value is None or time_value is None:
        raise ValueError("Provide either datetime or both date and time")
    return datetime.combine(date_value, time_value, tzinfo=SEOUL_TZ)


def calculate_solar_position(when: datetime, latitude: float, longitude: float) -> SolarPosition:
    localized = localize_datetime(when)
    observer = Observer(latitude=latitude, longitude=longitude)
    return SolarPosition(
        altitude=float(elevation(observer, localized)),
        azimuth=float(azimuth(observer, localized)),
    )

