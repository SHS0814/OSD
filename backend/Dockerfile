FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY data/cbnu_buildings.geojson data/cbnu_campus_boundary.geojson data/kma_asos_131_hourly.csv \
     data/cbnu_dtm_5m.npz data/cbnu_landcover.geojson data/cbnu_street_trees.geojson /data/


EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
