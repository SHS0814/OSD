from contextlib import asynccontextmanager
import json

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
import numpy as np
from shapely.geometry import shape

from app.api.routes import router
from app.config import settings
from app.db.repository import BuildingRepository
from app.services.microclimate import MicroclimateModel
from app.services.thermal import utci
from app.services.weather import WeatherStore


def load_campus_boundary():
    collection = json.loads(settings.campus_boundary_path.read_text(encoding="utf-8"))
    return shape(collection["features"][0]["geometry"])


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
    # Rasterizes buildings and computes the sky view factor once; per-request
    # work is then only the shadows and the radiation for the requested instant.
    app.state.microclimate = MicroclimateModel(
        load_campus_boundary(), app.state.buildings.list_buildings()
    )
    # pythermalcomfort JIT-compiles UTCI on first use (~15 s); pay that here
    # rather than on the first user's request.
    utci(np.array([25.0]), np.array([25.0]), 1.0, np.array([50.0]))
    yield


app = FastAPI(
    title="Campus Shade Map API",
    version="0.1.0",
    lifespan=lifespan,
)
# The microclimate grid is a long list of repeating numbers; gzip shrinks it ~5x.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(router)
