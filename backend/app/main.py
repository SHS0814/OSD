import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
import json
import logging

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
import numpy as np
from shapely.geometry import shape

from app.api.routes import router
from app.config import settings
from app.db.repository import BuildingRepository
from app.services import kma_hub
from app.services.microclimate import MicroclimateModel
from app.services.solar import SEOUL_TZ
from app.services.thermal import utci
from app.services.weather import WeatherStore

logger = logging.getLogger(__name__)

REVISION_WINDOW = timedelta(hours=2)


def load_campus_boundary():
    collection = json.loads(settings.campus_boundary_path.read_text(encoding="utf-8"))
    return shape(collection["features"][0]["geometry"])


async def keep_weather_current(store: WeatherStore, key: str) -> None:
    """Append API허브 hours after the snapshot, then poll for each new hour.

    Each round re-reads the last few hours too: an hour is first published with
    some values missing and corrected minutes later (청주 19:00 on 2026-09-27
    came out without a cloud amount, then with 6/10).
    """
    while True:
        now = datetime.now(SEOUL_TZ).replace(minute=0, second=0, microsecond=0)
        start = store.latest - REVISION_WINDOW
        if start <= now:
            try:
                rows = await asyncio.to_thread(kma_hub.fetch_hours, key, start, now)
                added = store.extend(rows)
                logger.info("weather: +%d hours from API허브, latest %s", added, store.latest)
            except Exception:  # keep serving the last known weather; retry next round
                logger.exception("weather: API허브 refresh failed")
        await asyncio.sleep(settings.weather_refresh_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.buildings = BuildingRepository(
        database_url=settings.database_url,
        snapshot_path=settings.building_data_path,
    )
    app.state.buildings.synchronize_snapshot()
    app.state.weather = WeatherStore(
        settings.weather_data_path, settings.campus_latitude, settings.campus_longitude
    )
    refresher = None
    if settings.kma_apihub_key:
        refresher = asyncio.create_task(
            keep_weather_current(app.state.weather, settings.kma_apihub_key)
        )
    # Rasterizes buildings and computes the sky view factor once; per-request
    # work is then only the shadows and the radiation for the requested instant.
    app.state.microclimate = MicroclimateModel(
        load_campus_boundary(), app.state.buildings.list_buildings()
    )
    # pythermalcomfort JIT-compiles UTCI on first use (~15 s); pay that here
    # rather than on the first user's request.
    utci(np.array([25.0]), np.array([25.0]), 1.0, np.array([50.0]))
    yield
    if refresher is not None:
        refresher.cancel()
        with suppress(asyncio.CancelledError):
            await refresher


app = FastAPI(
    title="Campus Shade Map API",
    version="0.1.0",
    lifespan=lifespan,
)
# The microclimate grid is a long list of repeating numbers; gzip shrinks it ~5x.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(router)
