import os

os.environ.pop("DATABASE_URL", None)
# Tests run on the committed weather snapshot, never against the live API허브.
os.environ.pop("KMA_APIHUB_KEY", None)
# ... and never call VWorld; satellite tests use their own cache folder.
os.environ.pop("VWORLD_API_KEY", None)
# Every TestClient starts the app; building all 32 wind maps each time would
# add ~19 s per test, so maps are built on first use instead (same values).
os.environ["WIND_FIELD_PRECOMPUTE"] = "0"
