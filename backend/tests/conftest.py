import os

os.environ.pop("DATABASE_URL", None)
# Tests run on the committed weather snapshot, never against the live API허브.
os.environ.pop("KMA_APIHUB_KEY", None)
