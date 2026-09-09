# Campus Shade Map MVP

충북대학교 캠퍼스의 건물 형상과 높이, 선택 시각의 태양 위치를 이용해 예상 그림자를 지도에 표시하는 Android + FastAPI MVP입니다. BLE, 센서, 사용자 측위, 길찾기와 쾌적 경로 추천은 현재 범위에 포함하지 않습니다.

> 현재 결과는 도시 3D 시뮬레이션이 아닌 단순화된 2D 그림자 근사치입니다. 의사결정이나 안전 용도로 사용하면 안 됩니다.

## 시스템 구조

```text
Android (MapLibre)
        │ HTTPS REST / GeoJSON
        ▼
Cloudflare Tunnel (선택)
        │ http://api:8000
        ▼
FastAPI ─────────────── PostgreSQL + PostGIS
  │  Astral / Shapely / PyProj
  └─ 태양 위치 및 2D 그림자 계산
```

PostgreSQL은 Compose 네트워크에만 연결되며 호스트의 `5432` 포트를 공개하지 않습니다. API 개발 포트도 `127.0.0.1:8000`에만 바인딩합니다.

공식 `postgis/postgis:17-3.5` tag는 현재 amd64 이미지이므로 Compose에 `linux/amd64`를 명시했습니다. Apple Silicon Docker Desktop에서는 에뮬레이션으로 실행되고 일반적인 Linux amd64 서버에서는 native로 실행됩니다.

## 디렉터리

```text
backend/  FastAPI, 공간·태양 계산 서비스, 테스트
android/  Kotlin 네이티브 Android 앱
data/     MVP 건물 GeoJSON
infra/    Docker Compose, PostGIS 초기화
```

## 빠른 실행

### Docker Compose

루트에서 환경 파일을 만든 뒤 실행합니다.

```bash
cp .env.example .env
docker compose --env-file .env -f infra/docker-compose.yml up --build
```

확인:

```bash
curl http://127.0.0.1:8000/health
curl 'http://127.0.0.1:8000/api/shadows?datetime=2026-09-09T14%3A00%3A00%2B09%3A00&lat=36.6268&lon=127.4583'
```

종료는 `docker compose --env-file .env -f infra/docker-compose.yml down`입니다. 데이터는 `postgres_data` 볼륨에 유지됩니다.

### 로컬 Backend

`DATABASE_URL`이 없으면 API는 `data/sample_buildings.geojson`을 읽으므로 PostGIS 없이도 개발할 수 있습니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend uvicorn app.main:app --reload
PYTHONPATH=backend pytest backend/tests
```

## Android 실행

1. Android Studio에서 `android/`를 엽니다.
2. JDK 17, Android SDK 35를 선택하고 Gradle Sync를 실행합니다.
3. Backend를 띄운 뒤 API 26 이상의 에뮬레이터/기기에서 `app`을 실행합니다.

기본 API 주소는 Android 에뮬레이터에서 호스트를 가리키는 `http://10.0.2.2:8000/`입니다. 실제 기기나 Cloudflare URL은 다음처럼 바꿉니다.

```bash
cd android
./gradlew assembleDebug -PAPI_BASE_URL=https://shade-api.example.com/
```

URL은 `/`로 끝나야 합니다. 로컬 HTTP 예외는 `10.0.2.2`와 `localhost`에만 허용됩니다. 운영에서는 HTTPS Tunnel URL을 사용하십시오.

앱은 충북대학교 좌표로 처음 이동하고 건물 및 현재 날짜의 그림자를 불러옵니다. 06:00–20:00 슬라이더 입력은 400ms debounce 후 다시 계산되며, `현재 시각`은 서울 현지 시각으로 즉시 갱신합니다. 지도 스타일 값은 `MapStyle.kt`에 모았습니다.

## API

### `GET /health`

```json
{"status":"ok"}
```

### `GET /api/buildings`

건물을 GeoJSON `FeatureCollection`으로 반환합니다.

### `GET /api/shadows`

다음 중 한 시간 형식을 사용합니다.

```text
/api/shadows?datetime=2026-09-09T14:00:00+09:00&lat=36.6268&lon=127.4583
/api/shadows?date=2026-09-09&time=14:00&lat=36.6268&lon=127.4583
```

timezone 없는 값은 `Asia/Seoul`로 해석합니다. offset이 있는 값은 같은 순간의 서울 시각으로 변환합니다. 결과는 현지 ISO datetime, 태양 고도·방위각, 그림자 GeoJSON을 포함합니다. 태양 고도가 0° 이하면 `features`가 빈 컬렉션입니다.

## 좌표계와 그림자 계산

PostGIS 원본 geometry는 교환과 지도 렌더링에 적합한 `EPSG:4326`으로 저장합니다. meter 단위 연산은 대한민국 전역을 위한 Korea 2000 / Unified CS인 `EPSG:5179`로 투영합니다. 충북대학교 주변에서 위경도에 meter 이동량을 직접 더하는 오류를 피하면서, 향후 국내 캠퍼스 데이터로 확장하기 쉬운 선택입니다. 응답 직전에 다시 `EPSG:4326`으로 변환합니다.

계산 순서:

1. Astral로 관측 좌표·서울 시각의 태양 고도와 북쪽 기준 시계방향 방위각을 구합니다.
2. `length = height / tan(altitude)`로 그림자 길이를 구합니다.
3. 태양 방위각의 반대 방향으로 east/north 이동 벡터를 만듭니다.
4. 원 건물, 이동된 건물, 각 경계 선분이 이동하며 만드는 사각형을 합집합합니다.

이 swept-polygon 방식은 단순 convex hull보다 오목한 건물 주변을 불필요하게 많이 채우지 않으면서도 MVP에 충분히 가볍습니다.

현재 한계:

- 지형, 건물 지붕 모양, 나무와 시설물, 주변 건물에 의한 그림자 차폐를 고려하지 않습니다.
- 벽면의 정밀 3D ray tracing이나 그림자 중첩 강도를 계산하지 않습니다.
- 낮은 태양 고도에서는 그림자가 매우 길어지며 별도 최대 길이 제한이 없습니다.
- 샘플 건물은 기능 검증용 수동 직사각형이고 높이도 수동 추정치이므로 실제 캠퍼스 건물 경계가 아닙니다.

## 데이터와 PostGIS

`data/sample_buildings.geojson`에는 8개 MVP 테스트 건물이 있습니다. `source_geometry=manual-mvp`, `source_height=manual-estimate`로 출처를 분리했습니다. DB 없는 개발 모드에서는 GeoPandas가 이 교환 데이터를 정규화하고, Shapely가 geometry를 처리합니다. Compose가 새 DB 볼륨을 만들 때 `infra/db/init.sql`이 PostGIS extension, `buildings` 테이블, GiST 인덱스와 같은 샘플을 생성합니다.

실데이터 교체 우선순위는 공공데이터/국가공간정보 공개데이터 → OSM building polygon → 직접 보정입니다. OSM을 사용할 경우 ODbL 및 attribution 의무를 확인하고 `source_geometry`를 명확히 기록해야 합니다.

## 환경 변수

| 이름 | 기본값/역할 |
|---|---|
| `POSTGRES_DB` | `campus_shade` |
| `POSTGRES_USER` | `campus_shade` |
| `POSTGRES_PASSWORD` | 개발 기본값은 `change-me`; 배포 전 변경 |
| `DATABASE_URL` | API의 내부 PostgreSQL DSN |
| `SAMPLE_DATA_PATH` | DB 미사용 시 GeoJSON 경로 |
| `CLOUDFLARE_TUNNEL_TOKEN` | 선택적 Tunnel token; 저장소에 커밋 금지 |
| `API_BASE_URL` | Android build용 API base URL |

## Cloudflare Tunnel

Cloudflare에서 Tunnel과 public hostname을 만든 후 service를 `http://api:8000`으로 지정하고 토큰을 `.env`에 넣습니다. 그런 다음 profile을 켭니다.

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile tunnel up --build
```

토큰이 없는 기본 실행에서는 cloudflared profile이 시작되지 않습니다.

## 테스트 범위

테스트는 낮/밤 태양 고도, 태양 방위각 범위, 45°에서 20m 높이의 20m 그림자, 반대 방향 벡터, polygon translation/sweep, 건물 및 그림자 GeoJSON API, 야간 빈 응답을 검증합니다.

## 이후 계획

1. 검증된 OSM 또는 공공 건물 geometry와 실제 높이로 교체
2. 관측 좌표를 고정 캠퍼스 설정으로 제한하거나 요청 viewport로 필터링
3. 캐시, 공간 bbox 쿼리, 낮은 고도 최대 길이 정책 추가
4. 센서/BLE 업로드 모델을 별도 모듈로 추가
5. 실측 기후 정보와 보행 네트워크를 결합한 쾌적 경로 추천
