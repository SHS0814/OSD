from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import settings
from app.db.repository import BuildingRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.buildings = BuildingRepository(
        database_url=settings.database_url,
        snapshot_path=settings.building_data_path,
    )
    app.state.buildings.synchronize_snapshot()
    yield


app = FastAPI(
    title="Campus Shade Map API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
