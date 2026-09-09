from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import settings
from app.db.repository import BuildingRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.buildings = BuildingRepository(
        database_url=settings.database_url,
        sample_path=settings.sample_data_path,
    )
    yield


app = FastAPI(
    title="Campus Shade Map API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)

