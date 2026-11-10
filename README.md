# Campus Shade Map MVP

충북대학교 캠퍼스의 선택한 날짜·시각에 대해 **추정 체감온도(UTCI) 히트맵**, **건물 그림자**, **칸별 바람**과 **더위·추위를 피하는 보행 경로**를 지도에 보여 주는 Android + FastAPI MVP입니다. 체감온도는 지형·건물·나무가 만드는 그늘, 토지피복, 건물을 돌아가는 바람, 기상청 청주 ASOS 관측으로 계산합니다. 배포 주소는 `https://osd.locationfit.org`입니다.

현재 진행 상황:

| 기능 | 상태 |
|---|---|
| 캠퍼스 건물 105동 (높이 보유 67동), 3D 건물 / 2D 전환 | ✅ |
| 건물 평면 그림자 (`/api/shadows`) | ✅ |
| 체감온도 히트맵 v1: 지형·건물·나무 그늘 + 토지피복 + 칸별 바람 (`/api/microclimate`) | ✅ |
| 칸별 바람 화살표 (`/api/wind`) | ✅ |
| 그늘길(더울 때)·햇볕길(추울 때) 경로 (`/api/route`) | ✅ |
| 기상 스냅샷 2025-06-01 ~ 2026-10-05, API허브 키가 있으면 실시간 갱신, 현재 날씨 카드 | ✅ |
| 날짜 선택으로 과거 날 다시 보기 | ✅ |
| 위성 배경 지도, 건물 검색, 내 위치 체감온도 | ✅ |
| 환경 센서 위치 (`/api/sensors`, 측정값 없음) | ✅ |
| 가로수 입력 | 📝 파일만 있고 비어 있음 |
| 높이 없는 38동, 센서 측정값 표시, BLE | ⏸ 이후 계획 |

> 모든 값은 추정치입니다. 그림자는 단순화된 2D 근사이고, 체감온도는 기온·습도에 캠퍼스 전체에 같은 기상값을 쓰며 그늘·지면·바람 효과만 지점별로 반영합니다. 칸별 바람은 풍속계로 검증하지 않았습니다. 의사결정이나 안전 용도로 사용하면 안 됩니다.

## 시스템 구조

```text
Android (MapLibre)
        │ HTTPS REST / GeoJSON
        ▼
Cloudflare Tunnel (선택)
        │ http://api:8000
        ▼
FastAPI ─────────────── PostgreSQL + PostGIS (선택)
  │  Astral / Shapely / PyProj / SciPy / pythermalcomfort
  ├─ 태양 위치 및 2D 건물 그림자
  ├─ 2m 지표 모델 광선 추적 → 4m 격자 체감온도(UTCI)
  ├─ 바람 위쪽 차폐 + 2D 질량보존 흐름 → 칸별 풍속·풍향
  ├─ 체감온도를 비용으로 쓰는 보행 경로
  ├─ VWorld 항공사진 타일 중계 (키는 서버에만)
  └─ 기상청 API허브 (키가 있을 때만, 5분마다 새 관측)
```

PostgreSQL은 Compose 네트워크에만 연결되며 호스트의 `5432` 포트를 공개하지 않습니다. API 포트도 `127.0.0.1`에만 바인딩합니다(기본 `8000`, `API_PORT`로 변경).

공식 `postgis/postgis:17-3.5` tag는 현재 amd64 이미지이므로 Compose에 `linux/amd64`를 명시했습니다. Apple Silicon Docker Desktop에서는 에뮬레이션으로 실행되고 일반적인 Linux amd64 서버에서는 native로 실행됩니다.

## 디렉터리

```text
backend/   FastAPI 앱과 테스트
  app/api/routes.py        모든 엔드포인트
  app/main.py              시작 시 데이터 적재, 모델 구성, API허브 갱신 루프
  app/config.py            환경 변수와 기본 데이터 경로
  app/db/, app/models/     건물 저장소 (GeoJSON 스냅샷 또는 PostGIS)
  app/services/            계산 모듈 (아래 표)
  tests/                   pytest, tests/fakes.py는 상대편 계약의 대역
android/   Kotlin 네이티브 Android 앱 (View 기반)
  .../campusshade/         MainActivity, API 클라이언트, 응답 파싱·표시 로직
  .../campusshade/map/     지도 레이어 (건물, 그림자, 히트맵, 바람, 경로, 센서, 위성)
  .../campusshade/ui/      화면 부품 (시각 시트, 지도 설정, 검색, 경로 카드, 날씨 카드 등)
data/      커밋된 고정 데이터 스냅샷 (아래 "데이터와 PostGIS")
scripts/   data/ 스냅샷을 다시 만드는 수집·가공 스크립트와 분석 스크립트
infra/     Docker Compose, PostGIS 초기화
```

`scripts/`는 앱이나 API가 실행 중에 호출하지 않습니다. `data/`의 스냅샷을 재생성하거나 분석할 때만 사람이 직접 돌립니다. `docs/`는 개인 작업 노트용으로 `.gitignore`에 들어 있어 저장소에 없습니다.

`backend/app/services/`는 모델의 두 절반이 서로의 모듈을 import하지 않고 계약(`contracts.py`)과 격자(`grid.py`)로만 만나도록 나뉘어 있습니다.

| 구분 | 모듈 | 하는 일 |
|---|---|---|
| 공간 (P1) | `geometry_field.py`, `surfaces.py`, `terrain.py`, `shadow.py` | 지표 모델(지형+건물+수관), 태양 광선 추적, SVF, 지면 반사율·가열, 바람용 장애물 래스터, 평면 그림자 |
| 대기 (P2) | `weather.py`, `kma_hub.py`, `thermal.py`, `comfort.py`, `wind.py`, `sensors.py` | 기상 스냅샷·실시간 관측, 일사 분리, Tmrt·UTCI, 칸별 바람, 센서 파일 QC |
| 계약 | `contracts.py`, `grid.py`, `common.py` | `GeometryFields`·`ObstacleRaster`·`WeatherSample`, 공용 격자, 잎 계절·지면 가열 계수. 양쪽 합의로만 변경 |
| 공용 | `solar.py`, `geometry.py` | 태양 위치, WGS84 ↔ EPSG:5179 변환 |
| 통합 (P4) | `microclimate.py`, `routing.py`, `vworld_tiles.py` | 두 절반을 묶은 체감온도 모델, 보행 경로, 위성 타일 중계 |

## 팀 / 모듈 담당

커밋 제목의 접두어가 담당을 나타냅니다(`[P1] feat(core): ...`).

| 담당 | 범위 |
|---|---|
| `[P1]` 공간 | 위 표의 공간 모듈, 건물·지형·토지피복·수관·보행로 스냅샷과 그 스크립트(`build_snapshot.py`, `heights.py`, `fetch_campus_*.py`, `fetch_building_ledger.py`, `build_terrain.py`, `build_landcover.py`, `build_tree_canopy.py`, `build_walk_network.py`) |
| `[P2]` 대기 | 위 표의 대기 모듈, 기상·센서 스냅샷과 그 스크립트(`fetch_kma_asos.py`, `build_sensor_sites.py`, `analyze_sensors.py`, `analyze_wind_effect.py`) |
| `[P3]` Android | `android/` 전체 |
| `[P4]` 통합 | API(`routes.py`, `main.py`, `config.py`), 통합 모듈, DB, `infra/`, Docker, CI, README |
| `[contract]`, `[common]` | 계약·공용 모듈. 양쪽이 합의해 바꿉니다 |

## 빠른 실행

### Docker Compose

루트에서 환경 파일을 만든 뒤 실행합니다. `.env`는 커밋하지 않습니다.

```bash
cp .env.example .env
docker compose --env-file .env -f infra/docker-compose.yml up --build
```

확인:

```bash
curl http://127.0.0.1:8000/health
curl 'http://127.0.0.1:8000/api/shadows?datetime=2026-09-09T14%3A00%3A00%2B09%3A00&lat=36.6268&lon=127.4583'
```

종료는 `docker compose --env-file .env -f infra/docker-compose.yml down`입니다. 데이터는 `postgres_data` 볼륨에, VWorld 타일 캐시는 `satellite_cache` 볼륨에 유지됩니다.

Compose 프로젝트 이름의 기본값은 compose 파일이 있는 폴더 이름(`infra`)입니다. 같은 기계에서 두 번째 스택(다른 체크아웃이나 worktree)을 띄우면 컨테이너와 볼륨이 섞이므로 `-p`로 이름을 나누고 `API_PORT`로 호스트 포트를 바꿉니다.

```bash
API_PORT=8001 docker compose -p campus-shade-dev --env-file .env -f infra/docker-compose.yml up --build
```

서버는 시작할 때 바람 지도 32장과 2D 흐름을 미리 계산하므로 `/health`가 응답하기까지 10~20초 걸립니다.

### 로컬 Backend

`DATABASE_URL`이 없으면 API는 커밋된 `data/cbnu_buildings.geojson` 스냅샷을 읽으므로 PostGIS 없이도 개발할 수 있습니다. Python 3.13 기준입니다(`backend/Dockerfile`, CI와 같음).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend uvicorn app.main:app --reload
PYTHONPATH=backend pytest backend/tests
```

`--reload`로 자주 다시 시작할 때는 `WIND_FIELD_PRECOMPUTE=0`을 주면 바람 지도를 첫 요청 때 만들어 시작이 빨라집니다(값은 같습니다).

로컬 실행은 `.env`를 자동으로 읽지 않습니다. 키가 없으면 커밋된 기상 스냅샷의 마지막 날로 동작합니다. 실시간 기상이 필요하면 키만 넘깁니다. `.env`를 통째로 `source`하면 Compose용 `DATABASE_URL`(`db` 호스트)까지 들어가 DB 연결이 깨질 수 있습니다.

```bash
KMA_APIHUB_KEY=$(grep '^KMA_APIHUB_KEY=' .env | cut -d= -f2-) PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`/api/weather/period`의 `realtime`이 `true`면 실시간 기상이 켜진 것입니다.

## Android 실행

1. Android Studio에서 `android/`를 엽니다.
2. JDK 17, Android SDK 35를 선택하고 Gradle Sync를 실행합니다.
3. Backend를 띄운 뒤 API 26 이상의 에뮬레이터/기기에서 `app`을 실행합니다.

CLI 빌드와 단위 테스트는 `cd android && ./gradlew assembleDebug testDebugUnitTest`입니다. Android Studio 밖에서 처음 빌드하면 `android/local.properties`에 `sdk.dir=<Android SDK 경로>`가 필요할 수 있습니다(커밋하지 않음).

기본 API 주소는 Android 에뮬레이터에서 호스트를 가리키는 `http://10.0.2.2:8000/`입니다. URL은 `/`로 끝나야 합니다.

앱 주소는 Gradle 속성 `API_BASE_URL`로 바꿉니다(`.env`가 아닙니다). **Android Studio의 Run 버튼은 `-P` 옵션을 붙일 수 없어 기본값인 `10.0.2.2`로 되돌아갑니다.** 홈 디렉터리의 `~/.gradle/gradle.properties`에 넣어두면 Run 버튼에도 적용되고, 커밋되지 않아 팀원 설정과 충돌하지 않습니다.

```bash
echo 'API_BASE_URL=http://localhost:8000/' >> ~/.gradle/gradle.properties   # adb reverse로 실기기 테스트
echo 'API_BASE_URL=https://osd.locationfit.org/' >> ~/.gradle/gradle.properties  # 배포 서버
```

CLI로 한 번만 지정할 수도 있습니다.

```bash
cd android
./gradlew installDebug -PAPI_BASE_URL=https://osd.locationfit.org/
```

로컬 HTTP 예외는 `10.0.2.2`와 `localhost`에만 허용됩니다. debug 빌드에는 `app/src/debug/`의 완화된 정책이 적용되어 임의 호스트로 평문 요청이 가능하고, release 빌드는 엄격한 정책을 유지합니다. 운영에서는 HTTPS 주소를 사용하십시오.

### 실기기로 테스트할 때

`10.0.2.2`는 에뮬레이터 전용 주소라 실기기에서는 닿지 않습니다. `adb reverse`로 폰의 `localhost`를 개발 PC에 연결하는 방식이 가장 안정적입니다. 공유기나 IP가 바뀌어도 영향을 받지 않고, `localhost`는 이미 cleartext 예외에 들어 있습니다. 앱 주소는 위처럼 `http://localhost:8000/`로 둡니다.

```bash
PYTHONPATH=backend uvicorn app.main:app --port 8000

# 폰의 localhost:8000 -> PC의 8000
adb reverse tcp:8000 tcp:8000
```

같은 Wi-Fi에서 PC의 LAN 주소로 직접 붙으려면 `--host 0.0.0.0`으로 띄우고 debug 빌드를 씁니다(기본값 `127.0.0.1`로는 폰이 못 붙습니다).

터널은 폰을 다시 연결할 때마다 사라지므로 그때마다 `adb reverse`를 다시 실행해야 합니다.

`adb`는 macOS 기본 설치 기준 `~/Library/Android/sdk/platform-tools/adb`에 있으며 PATH에 없을 수 있습니다.

무선 디버깅(Android 11+, 같은 Wi-Fi)에서도 `adb reverse`가 그대로 동작합니다. 폰의 개발자 옵션 → 무선 디버깅 → "페어링 코드로 기기 페어링"에서 주소와 코드를 확인합니다. 페어링 포트와 연결 포트는 서로 다릅니다.

```bash
adb pair <IP>:<페어링 포트>      # 최초 1회, 6자리 코드 입력
adb connect <IP>:<연결 포트>     # 무선 디버깅 메인 화면의 포트
adb reverse tcp:8000 tcp:8000
```

### 앱 화면

- 처음에는 충북대학교로 이동해 건물을 3D로 세우고 **오늘**의 체감온도 히트맵을 불러옵니다. 서버에 실시간 기상(API허브 키)이 없으면 관측이 끝난 마지막 날을 씁니다. 어느 쪽인지는 `/api/weather/period`로 묻습니다.
- 오른쪽 아래 **시각 카드**를 누르면 06:00–20:00 슬라이더, 날짜 선택(기상 자료가 있는 날), `현재 시각`이 있는 시트가 열립니다. 슬라이더 입력은 400ms debounce 후 다시 계산합니다. 아직 관측 전인 시각을 고르면 히트맵을 숨기고 최근 관측 시각을 알려 줍니다.
- **지도 설정** 시트에서 3D/2D, 일반/위성 배경, 체감온도/그림자, 바람 화살표, 센서 위치를 바꿉니다. 히트맵에 그늘 효과가 이미 들어 있어 체감온도와 그림자는 겹치지 않고 둘 중 하나만 보입니다.
- **건물 검색**(이름·번호, 구역 칩)에서 고른 건물이나 지도를 길게 누른 곳을 출발·도착으로 정하면 경로를 찾습니다. 지도 위 출발·도착 핀은 끌어서 옮길 수 있습니다.
- **날씨 카드**는 `/api/weather`의 현재 관측이고, 위치 권한을 주면 지금 시각에 한해 화면 가장자리 색과 `내 위치 체감` 줄로 서 있는 칸의 체감온도를 보여 줍니다.
- 히트맵은 서버가 보낸 격자를 격자 한 칸당 한 픽셀인 비트맵으로 바꿔 `ImageSource`로 바닥에 깝니다. 지도 스타일 값은 `MapStyle.kt`, 체감온도 색상표는 `UtciHeatmap.kt`, 레이어 순서는 `map/MapLayers.kt`에 모았습니다.

## API

시각을 받는 엔드포인트(`/api/shadows`, `/api/microclimate`, `/api/wind`, `/api/route`)는 다음 중 한 형식을 씁니다.

```text
?datetime=2026-08-07T15:00:00+09:00
?date=2026-08-07&time=15:00
```

timezone 없는 값은 `Asia/Seoul`로 해석합니다. offset이 있는 값은 같은 순간의 서울 시각으로 변환합니다. 형식이 잘못되면 422, 기상 자료가 없는 시각이면 404입니다(스냅샷 시작 2025-06-01 이전과, 최근 관측으로부터 3시간이 지난 시각).

### `GET /health`

```json
{"status":"ok"}
```

### `GET /api/buildings`

건물을 GeoJSON `FeatureCollection`으로 반환합니다. 속성은 `id`, `name`, `height_m`(없으면 `null`), `source_geometry`, `source_height`, `osm_type`, `osm_id`, `vworld_id`입니다.

### `GET /api/shadows`

`lat`, `lon`(태양 위치를 구할 지점)과 시각을 받습니다.

```text
/api/shadows?datetime=2026-09-09T14:00:00+09:00&lat=36.6268&lon=127.4583
/api/shadows?date=2026-09-09&time=14:00&lat=36.6268&lon=127.4583
```

결과는 현지 ISO datetime, 태양 고도·방위각, 그림자 GeoJSON과 전체/높이 보유/누락 건물 수를 포함합니다. 태양 고도가 0° 이하면 `features`가 빈 컬렉션이며, 직접 meter 높이가 없는 건물은 그림자 계산에서 제외됩니다.

### `GET /api/microclimate`

4m 격자의 추정 체감온도입니다. 시각만 받고 좌표는 받지 않습니다. 자세한 내용은 아래 "체감온도 계산 (v1)"에 있습니다.

```text
/api/microclimate?datetime=2026-08-07T15:00:00+09:00
```

### `GET /api/wind`

칸별 바람을 화살표용 GeoJSON Point로 반환합니다. `step_m`(기본 24, 최소 8)마다 캠퍼스의 열린 땅 칸에 점을 놓고, 건물이 절반 넘게 덮은 칸은 뺍니다.

```text
/api/wind?datetime=2026-01-13T13:00:00+09:00&step_m=24
```

점마다 `speed_ms`, `factor`(ASOS 풍속 대비 배율), `direction_deg`(바람이 불어오는 방향, 북쪽 360)가 있고, 화살표는 그 반대쪽을 가리킵니다. `wind`에는 ASOS 풍속·풍향과 칸별 바람 사용 여부가 들어 있습니다. 무풍이거나 `WIND_FIELD_ENABLED=0`이면 점이 없습니다.

### `GET /api/route`

선택 시각의 체감온도로 **최단·균형·쾌적 경로**를 찾습니다.

```text
/api/route?from_lat=36.630931&from_lon=127.454222&to_lat=36.626035&to_lon=127.456245&datetime=2026-08-07T15:00:00+09:00
```

보행로는 OpenStreetMap의 걸을 수 있는 길(`data/cbnu_walk_network.geojson`)이며 4m 이하 조각으로 나눠 조각마다 체감온도 격자 값을 읽습니다. 조각 비용은 `길이 × (1 + α × (더위 + 추위))`입니다.

- 더위: 그 시각 그늘의 체감온도(캠퍼스 하위 5%, 단 26°C 이상)보다 얼마나 더운지. 더우면 `mode`가 `heat`이고 `coolest`는 그늘길입니다.
- 추위: 그 시각 양지의 체감온도(캠퍼스 상위 5%, 단 9°C 이하)보다 얼마나 추운지. 추우면 `mode`가 `cold`이고 `coolest`는 햇볕길입니다.
- `coolest`는 최단 경로보다 최대 30%, `balanced`는 15%까지 길어질 수 있고, 최단 경로와 같으면 빠집니다. 밤이나 모두 쾌적한 시각(`mode`가 `none`)에는 최단 경로만 돌려줍니다.

각 경로에는 `kind`, `mode`, 거리(`length_m`), 최단 대비 추가 거리(`extra_m`), 걷는 시간(1.2 m/s), 평균 체감온도, 강한 더위·보통 이상 추위 속을 걷는 시간, 양지 비율과 햇빛 아래를 걷는 시간(`sun_minutes`)이 들어 있습니다. 출발·도착이 길에서 150m 넘게 떨어져 있으면 422, 보행로 파일이 없으면 503입니다.

### `GET /api/weather`

앱의 날씨 카드용으로 한 시각(`datetime`, 기본: 지금)의 ASOS 관측을 반환합니다. `date`+`time` 형식은 받지 않습니다. `datetime`을 생략했는데 지금이 아직 관측 전이면 최근 관측을 주고 `latest`를 `true`로 둡니다. `datetime`을 주었는데 관측이 없으면 404입니다.

### `GET /api/weather/period`

기상 자료가 있는 기간과 실시간 여부를 반환합니다. 앱은 이 값으로 처음 열 날짜와 날짜 선택 범위를 정합니다.

```json
{"start":"2025-06-01T00:00:00+09:00","end":"2026-10-05T23:00:00+09:00","latest_observation":"2026-10-05T23:00:00+09:00","latest_full_date":"2026-10-05","realtime":false,"station":"청주 ASOS (131)"}
```

`latest_full_date`는 24시간 관측이 모두 있는 마지막 날입니다. API허브 키가 있으면 `end`가 최근 관측까지 늘어납니다.

### `GET /api/sensors`

캠퍼스 환경 센서의 설치 위치를 GeoJSON Point로 반환합니다(`sensor`, `team`, 기록 기간, 판독 수, 유효율). 측정값은 담지 않습니다. 원본(`data/raw/sensors/`)은 커밋하지 않고, 위치만 뽑은 `data/cbnu_sensors.geojson`을 `scripts/build_sensor_sites.py`로 만듭니다. 앱은 이 위치를 점과 센서 이름으로 표시합니다.

### `GET /api/tiles/satellite/{z}/{x}/{y}.jpeg`

앱의 위성 배경 지도용 VWorld 항공사진 타일입니다. 앱이 VWorld를 직접 부르지 않고 서버를 거치므로 VWorld 키는 서버에만 있습니다. 캠퍼스 주변(경도 127.43–127.49, 위도 36.61–36.645), 줌 10–19 타일만 내주고 나머지는 404입니다. 받은 타일은 `SATELLITE_CACHE_DIR`(로컬 기본 `data/raw/vworld_satellite/`, 커밋하지 않음)에 저장해 다시 쓰고, `VWORLD_API_KEY`가 없으면 저장된 타일만 내줍니다.

## 체감온도 계산 (v1)

`/api/microclimate`는 캠퍼스를 4m 격자로 나눠 선택 시각의 **추정 체감온도(UTCI)** 를 계산합니다.

응답에는 사용한 기상값(`weather`), 반영한 입력(`inputs`: 지형 여부, 수관 비율, 잎이 있는 계절인지, 칸별 바람 사용 여부), 직달·산란 일사(`irradiance`), 격자 정보(`grid`), 요약(`summary`)과 격자별 `utci`, `mrt`(평균복사온도), `sunlit`(양지 비율) 배열이 들어 있습니다. 배열은 북서쪽 모서리부터 행 우선 순서이며, 캠퍼스 밖 셀은 `null`입니다. 건물이 절반 넘게 덮은 셀은 주변 바깥 셀의 평균으로 채워 보냅니다. 건물 외곽선이 격자와 맞지 않아 비워 두면 건물과 히트맵 사이로 배경 지도가 하얀 띠처럼 비치기 때문이며, 이 셀들은 3D 건물에 가려지고 `summary` 계산에서도 빠집니다. gzip 압축 시 약 130KB입니다.

계산은 다섯 단계입니다.

1. 서버가 시작할 때 **지표 모델**을 2m 격자로 만듭니다. 지형(5m DTM) 위에 건물(바닥면 최저 지면 + 높이)을 세우고 나무 수관(토지피복 숲 + 항공사진 수관 + 가로수)을 얹습니다. 캠퍼스 밖 100m까지 포함해 가장자리 그늘도 잡습니다. 같은 모델로 SVF를 36방위·200m 범위에서 한 번 계산해 둡니다 (`geometry_field.py`).
2. 기상청 청주 ASOS의 시간 일사량을 Erbs 모델로 직달과 산란으로 나눕니다. 일사량은 직전 1시간 누적값이라, 그 시간의 청명도를 유지한 채 요청 시각의 태양 고도에 맞춰 순간값으로 바꿉니다 (`weather.py`, `thermal.py`).
3. 요청마다 열린 땅의 2m 픽셀에서 태양 쪽으로 광선을 쏩니다. 지형이나 건물에 막히면 그늘, 수관을 지나면 그 수관의 투과율만큼만 통과합니다. 사람 가슴 높이(1.1m)에서 쏴서 보간된 지형의 삼각형 면이 제자리에 그늘을 만들지 않게 합니다. 셀마다 이 값을 평균해 양지 비율로 쓰고, 토지피복에 따른 지면 반사율·가열 계수와 함께 평균복사온도를 계산합니다 (`thermal.py` docstring에 식이 있습니다).
4. **칸별 풍속**은 `ASOS 풍속 × K`입니다. K는 개활지 관측소에서 캠퍼스로 오며 거칠어지는 배경 감속(약 0.82), 바람 위쪽 건물·수관 뒤의 차폐, 건물을 돌아가는 2D 질량보존 흐름(통로·모서리 가속)을 합친 값입니다. 16방위 × 잎 있음/없음 32장의 차폐 지도와 두 방향의 흐름을 시작할 때 계산해 두고 요청마다 조합합니다 (`wind.py`, 근거와 문헌은 모듈 docstring). `WIND_FIELD_ENABLED=0`이면 캠퍼스 전체에 ASOS 풍속을 씁니다.
5. 기온·습도와 함께 `pythermalcomfort`로 UTCI를 구합니다 (`comfort.py`).

요청 하나는 0.2~0.4초가 걸리고, 같은 시각의 결과는 캐시해 경로 요청이 다시 씁니다. 서버 시작은 바람 지도를 포함해 10~20초입니다.

표면 물리값은 `backend/app/services/surfaces.py`에 모았습니다. 잔디의 지면 가열 계수만 관측으로 맞췄고 나머지는 문헌의 대략값인 **가정**입니다. 나무가 얼마나 시원하게 나오는지는 이 값들이 정하므로 결과를 해석할 때 함께 봐야 합니다.

| 표면 | 반사율 | 지면 가열 (K per W/m²) |
|---|---|---|
| 포장 (시가화 지역 전체) | 0.12 | 0.020 |
| 잔디·밭 | 0.20 | 0.012 (ASOS로 맞춤) |
| 나지·운동장 | 0.20 | 0.015 |
| 물 | 0.08 | 0.005 |
| 숲 바닥 | 0.15 | 0.012 |

| 수관 | 높이 | 투과율 (잎 있음 / 없음) |
|---|---|---|
| 활엽수림 | 12m | 0.20 / 0.60 |
| 혼효림 | 12m | 0.20 / 0.40 |
| 침엽수림 | 12m | 0.20 / 0.20 |
| 가로수 (기본) | 8m | 0.25 / 0.65 (침엽 0.25) |

활엽수는 4월 20일부터 11월 10일까지 잎이 있는 것으로 봅니다(`common.py`). 측정된 나무 그늘 투과율은 0.18~0.60, 건물 그늘은 0.02~0.25로 보고되어 있습니다.

지면 온도는 `기온 + 0.012 × 지면 일사량`으로 근사합니다. 계수는 청주 ASOS에서 일사 300W/m² 이상인 3,117시간의 `(지면온도 − 기온) / 일사량`으로 맞췄습니다(중앙값 0.0113, 최소제곱 0.0129).

한계:

- 기온·습도는 캠퍼스 전체에 같은 기상청 값을 씁니다. 지점별 차이는 복사(그늘·지면)와 바람 효과만 반영됩니다. 캠퍼스 센서로 칸별 기온을 보정하는 방안은 센서 자체 발열과 기기별 편차(밤에도 ASOS보다 5~10°C 높음)가 미기후 신호보다 커서 보류했습니다(`scripts/analyze_sensors.py`).
- 칸별 바람은 건물 위로 넘는 흐름, 후류의 역류, 지형 차폐, 돌풍을 반영하지 않고 풍속계로 검증하지 않았습니다. 높이가 없는 건물은 바람에는 12m 장애물로 넣습니다.
- 토지피복지도는 캠퍼스 안 작은 숲·가로수·중정의 나무를 대부분 놓치므로, VWorld 항공사진에서 자동 추출한 수관(`data/cbnu_tree_canopy.geojson`, 약 35 ha)을 더합니다. 높이는 수관 면적으로 추정하고 모두 활엽수로 둡니다. 빠지거나 잘못 잡힌 나무는 `data/cbnu_street_trees.geojson`에 직접 입력하면 서버를 다시 시작할 때 반영됩니다(형식은 파일의 `metadata` 참고).
- 높이가 없는 건물(38동)과 수치지도에만 있는 건물·무벽건물은 아직 그늘을 만들지 않습니다.
- 앱의 `그림자` 모드는 여전히 건물만으로 계산한 평면 그림자(`/api/shadows`)입니다. 나무와 지형 그늘은 체감온도 히트맵에만 들어 있습니다.

### 실시간 기상

`KMA_APIHUB_KEY`(기상청 API허브, 지상관측 ASOS 시간자료 활용신청 필요)가 있으면 서버가 시작할 때 스냅샷 이후 빠진 시간을 API허브에서 채우고, 이후 `WEATHER_REFRESH_SECONDS`(기본 300초)마다 새 관측을 받아 메모리에 더합니다. 키가 없으면 커밋된 스냅샷만으로 동작하며 테스트도 이 모드로 돕니다.

- 정시 관측은 약 3분 뒤 API허브에 올라옵니다(2026-09-27 19:00 관측이 19:02:52에 조회됨). 값은 공공데이터포털 스냅샷과 같습니다.
- 한 시간의 관측은 처음에 일부 값이 빠진 채 올라왔다가 몇 분 뒤 채워지기도 합니다(같은 19:00의 운량). 그래서 매번 최근 2시간을 다시 받아 덮어씁니다.
- 이번 시간 관측은 그 시간이 끝나야 나오므로, 최근 관측 이후 3시간까지는 **최근 관측을 이어서** 씁니다. 응답의 `weather.observed_at`과 `weather.persisted`가 어느 관측을 썼는지 알려 줍니다.
- 한 시간의 값이 결측이면 직전 3시간 안의 마지막 값을 씁니다.
- API허브 호출은 `certifi` 인증서 묶음으로 검증합니다. python.org의 macOS용 Python은 인증서 설치 단계를 거치지 않으면 API허브 인증서 체인을 거부합니다.

## 좌표계와 그림자 계산

PostGIS 원본 geometry는 교환과 지도 렌더링에 적합한 `EPSG:4326`으로 저장합니다. meter 단위 연산은 대한민국 전역을 위한 Korea 2000 / Unified CS인 `EPSG:5179`로 투영합니다. 충북대학교 주변에서 위경도에 meter 이동량을 직접 더하는 오류를 피하면서, 향후 국내 캠퍼스 데이터로 확장하기 쉬운 선택입니다. 응답 직전에 다시 `EPSG:4326`으로 변환합니다.

`/api/shadows`의 계산 순서:

1. Astral로 관측 좌표·서울 시각의 태양 고도와 북쪽 기준 시계방향 방위각을 구합니다.
2. `length = height / tan(altitude)`로 그림자 길이를 구합니다.
3. 태양 방위각의 반대 방향으로 east/north 이동 벡터를 만듭니다.
4. 원 건물, 이동된 건물, 각 경계 선분이 이동하며 만드는 사각형을 합집합합니다.

이 swept-polygon 방식은 단순 convex hull보다 오목한 건물 주변을 불필요하게 많이 채우지 않으면서도 MVP에 충분히 가볍습니다.

현재 한계 (`/api/shadows`와 앱의 `그림자` 모드에 해당하며, 체감온도 히트맵은 위의 광선 추적을 씁니다):

- 지형, 건물 지붕 모양, 나무와 시설물, 주변 건물에 의한 그림자 차폐를 고려하지 않습니다.
- 벽면의 정밀 3D ray tracing이나 그림자 중첩 강도를 계산하지 않습니다.
- 낮은 태양 고도에서는 그림자가 매우 길어지며 별도 최대 길이 제한이 없습니다.
- 직접 meter 높이가 없는 건물에는 층수 환산이나 임의 기본 높이를 적용하지 않으므로 그림자가 표시되지 않습니다. 현재 105동 중 38동이 여기에 해당합니다.

## 데이터와 PostGIS

`data/`의 파일은 모두 커밋된 고정 스냅샷입니다. **API는 실행 중에 OSM·data.go.kr을 호출하지 않습니다.** 실행 중 외부 호출은 키가 있을 때의 기상청 API허브와, 캐시에 없는 위성 타일을 받는 VWorld뿐입니다. 앱은 이 API 외에 기본 지도 스타일·타일만 OpenFreeMap에서 받습니다. 원본 자료는 `data/raw/`에 두고 커밋하지 않습니다(센서망 원본 내보내기 `data/opensrc_*.csv`도 마찬가지).

| 파일 | 내용 | 만드는 방법 |
|---|---|---|
| `cbnu_campus_boundary.geojson` | OSM relation `6705106` 경계 (outer 링만, 87.9 ha) | `scripts/fetch_campus_boundary.py` (Overpass) |
| `cbnu_campus_parcels.json` | 대장 조회용 필지(PNU) 24개 | `scripts/fetch_campus_parcels.py` (VWorld, `VWORLD_API_KEY`) |
| `cbnu_building_ledger.json` | 건축물대장 표제부 132건 | `scripts/fetch_building_ledger.py` (공공데이터포털, `DATA_GO_KR_API_KEY`) |
| `cbnu_building_aliases.json` | 자동 매칭이 닿지 않는 건물의 수동 대응표 | 직접 편집 |
| `cbnu_buildings.geojson` | 경계 안 건물 **105동** | `scripts/build_snapshot.py` (OSM + `scripts/heights.py`의 높이 판정) |
| `cbnu_buildings_match_report.json` | 수집·필터·높이 출처 통계 | `scripts/build_snapshot.py` |
| `kma_asos_131_hourly.csv` | 기상청 청주 ASOS(131) 시간자료 11,808시간 (2025-06-01 ~ 2026-10-05) | `scripts/fetch_kma_asos.py` (공공데이터포털, `DATA_GO_KR_API_KEY`) |
| `kma_asos_131_hourly.meta.json` | 위 자료의 출처·기간·열 설명 | `scripts/fetch_kma_asos.py` |
| `cbnu_dtm_5m.npz` | 캠퍼스 + 300m 지형 5m 격자. 수치지도 1:5,000 등고선·표고점을 삼각망으로 보간 | `scripts/build_terrain.py` (`data/raw/수치지도/`) |
| `cbnu_landcover.geojson` | 환경부 세분류 토지피복지도를 캠퍼스 + 100m로 잘라 표면 유형으로 묶은 것 | `scripts/build_landcover.py` (`data/raw/landcover/`) |
| `cbnu_tree_canopy.geojson` | VWorld 항공사진에서 자동 추출한 나무 수관 473개, 캠퍼스 + 30m | `scripts/build_tree_canopy.py` (VWorld 타일, `VWORLD_API_KEY`) |
| `cbnu_street_trees.geojson` | 가로수. 직접 입력하는 파일로 지금은 비어 있음 | 직접 편집 |
| `cbnu_walk_network.geojson` | 길찾기용 보행로, OSM에서 걸을 수 있는 길 중 가장 큰 연결망 | `scripts/build_walk_network.py` (Overpass) |
| `cbnu_sensors.geojson` | 환경 센서 9대의 위치 | `scripts/build_sensor_sites.py` (`data/raw/sensors/`, 미커밋) |

스크립트는 저장소 루트에서 `python scripts/<이름>.py`로 돌리고, `backend`를 import하는 스크립트(`build_sensor_sites.py`, `analyze_*.py`)는 `PYTHONPATH=backend`가 필요합니다. 건물 스냅샷은 `fetch_campus_boundary.py` → `fetch_campus_parcels.py` → `fetch_building_ledger.py` → `build_snapshot.py` 순서입니다. 수치지도·토지피복지도 원본을 받는 방법은 `build_terrain.py`, `build_landcover.py`의 docstring에 있습니다. 분석 스크립트(`analyze_sensors.py`, `analyze_wind_effect.py`)는 `matplotlib`이 더 필요하고 결과를 로컬 `docs/`에 씁니다.

지형은 국토지리정보원이 공개하는 DEM이 90m뿐이라(고해상도는 공개제한) 수치지도로 직접 만들었습니다. 캠퍼스 안 90m 격자 106칸에서 공개DEM과 비교하면 평균 차이 +0.8m, RMSE 2.9m이고(공개DEM 자체 RMSE 6.2m), 캠퍼스 고저차는 49~90m입니다. 수치지도 도엽이 캠퍼스 서쪽 경계에서 끝나서 그 서쪽 여백은 가장자리 값을 연장했습니다.

지오메트리와 이름은 OSM을 기준으로 하며 이름은 `name:ko → name → ref → OSM ID` 순서로 선택합니다. 온실(`building=greenhouse`) 30동과 200㎡ 미만 22동은 제외했습니다. 제외된 52동 중 높이를 가진 건물은 하나도 없어 그림자는 줄지 않았습니다.

높이는 **국토교통부 건축물대장 표제부**를 우선하고 OSM `height` 태그를 보조로 씁니다. 양쪽에 값이 있는 22동을 비교하면 대장이 더 큰 경우가 19건, OSM 값은 22건 모두 정수인 반면 대장은 1건만 정수입니다. OSM 값이 매퍼의 내림 추정치이기 때문입니다. **층수는 미터로 환산하지 않습니다** — 추정값이 실측값과 구분 없이 지도에 나가는 것을 피하기 위해서입니다.

현재 105동 중 **67동**에 높이가 있습니다(대장 58, OSM 9). 나머지 38동 중 18동은 대장 레코드는 있으나 높이 칸이 비어 있어 공개 API로는 채울 수 없고, 4동은 대장에 값이 있으나 OSM에 건물이 없습니다. 매칭 규칙과 단지 단위 대장 처리는 `scripts/heights.py`와 `cbnu_building_aliases.json`의 `description`에 있습니다.

PostGIS 사용 시 API 시작 과정이 스냅샷을 idempotent upsert합니다. 기존 `manual-mvp` 행과 스냅샷에서 사라진 이전 OSM 행은 제거되어 신규 DB와 기존 DB 모두 같은 내용으로 수렴합니다.

OSM 데이터는 [Open Database License(ODbL)](https://www.openstreetmap.org/copyright)를 따르며 Android 지도에 `© OpenStreetMap contributors` attribution을 표시합니다.

### 데이터 출처와 이용 조건

OSM 외의 데이터는 [공공누리 제1유형(출처표시)](https://www.kogl.or.kr/info/license.do)이거나 이용허락범위에 제한이 없는 공공데이터입니다. 제1유형은 출처를 밝히면 가공·재배포를 포함해 자유롭게 이용할 수 있어, 가공한 결과를 이 저장소에 커밋합니다. 원본은 `data/raw/`에 두고 커밋하지 않습니다.

| 데이터 | 저작권자 | 이용 조건 | 이 저장소의 파일 |
|---|---|---|---|
| OpenStreetMap (경계, 건물, 보행로) | OpenStreetMap contributors | ODbL | `cbnu_campus_boundary.geojson`, `cbnu_buildings.geojson`, `cbnu_walk_network.geojson` |
| 지상(종관, ASOS) 시간자료 | 기상청 | 공공누리 제1유형 | `kma_asos_131_hourly.csv` |
| 수치지도 v2.0 1:5,000 (36706049, 36706059) | 국토교통부 국토지리정보원 | 공공누리 제1유형 | `cbnu_dtm_5m.npz` (등고선·표고점에서 보간) |
| 공개DEM 90m | 국토교통부 국토지리정보원 | 이용허락범위 제한 없음 | 검증에만 사용, 커밋하지 않음 |
| 세분류 토지피복지도 2025 | 기후에너지환경부 | 공공누리 제1유형 | `cbnu_landcover.geojson` (캠퍼스로 자르고 분류를 묶음) |
| 건축물대장 표제부 | 국토교통부 | 이용허락범위 제한 없음 | `cbnu_building_ledger.json` |
| GIS건물통합정보 (필지) | 국토교통부 공간정보 오픈플랫폼(VWorld) | VWorld 오픈API 이용약관 | `cbnu_campus_parcels.json` |
| 항공사진 (WMTS Satellite) | 국토교통부 공간정보 오픈플랫폼(VWorld) | VWorld 오픈API 이용약관 (재배포 조건 확인 필요) | `cbnu_tree_canopy.geojson` (사진에서 추출한 수관 윤곽만; 타일은 커밋하지 않음) |
| 캠퍼스 환경 센서 실습 데이터 | 수업 센서망 | 원본 미커밋 | `cbnu_sensors.geojson` (위치와 기록 통계만) |

토지피복지도는 공개 등급 자료를 온라인 자료신청으로 받았습니다. 메타데이터의 보안 제약은 공개제한 자료에만 해당합니다. 앱 화면 하단에도 `OpenStreetMap · OpenFreeMap · OpenMapTiles · 기상청 · 국토지리정보원 · 기후에너지환경부 · VWorld 항공사진`을 출처로 표시합니다.

## 환경 변수

Compose는 `.env`(`.env.example` 참고)에서 `POSTGRES_*`, `DATABASE_URL`, `API_PORT`, `KMA_APIHUB_KEY`, `VWORLD_*`, `CLOUDFLARE_TUNNEL_TOKEN`을 읽고, 데이터 경로는 `infra/docker-compose.yml`에서 이미지 안의 `/data/...`로 직접 지정합니다. 로컬 실행에서는 아래 변수를 셸에서 주고, 없으면 기본값을 씁니다(`backend/app/config.py`).

| 이름 | 기본값/역할 |
|---|---|
| `POSTGRES_DB` | `campus_shade` |
| `POSTGRES_USER` | `campus_shade` |
| `POSTGRES_PASSWORD` | 개발 기본값은 `change-me`; 배포 전 변경 |
| `DATABASE_URL` | API의 PostgreSQL DSN. 없으면 GeoJSON 스냅샷만 씀 |
| `API_PORT` | Compose에서 API를 바인딩할 호스트 포트(`127.0.0.1`), 기본 `8000` |
| `BUILDING_DATA_PATH` | 건물 GeoJSON (DB 미사용 시 직접 읽고, DB 사용 시 동기화 원본) |
| `CAMPUS_BOUNDARY_PATH` | 체감온도 격자 범위로 쓰는 캠퍼스 경계 GeoJSON |
| `WEATHER_DATA_PATH` | ASOS 시간자료 CSV |
| `TERRAIN_DATA_PATH` | 지형 격자 (`cbnu_dtm_5m.npz`) |
| `LANDCOVER_DATA_PATH` | 토지피복 (`cbnu_landcover.geojson`) |
| `TREE_CANOPY_DATA_PATH` | 항공사진 수관 (`cbnu_tree_canopy.geojson`); 없으면 없이 계산 |
| `STREET_TREES_DATA_PATH` | 가로수 (`cbnu_street_trees.geojson`); 없으면 가로수 없이 계산 |
| `WALK_NETWORK_DATA_PATH` | 보행로 (`cbnu_walk_network.geojson`); 없으면 `/api/route`가 503 |
| `SENSORS_DATA_PATH` | 센서 위치 (`cbnu_sensors.geojson`); 없으면 빈 목록 |
| `SATELLITE_CACHE_DIR` | 위성 타일 저장 위치, 기본 `data/raw/vworld_satellite` |
| `WIND_FIELD_ENABLED` | 칸별 바람, 기본 켬. `0`이면 캠퍼스 전체에 ASOS 풍속 |
| `WIND_FIELD_PRECOMPUTE` | 바람 지도를 시작할 때 미리 계산, 기본 켬. `0`이면 첫 요청 때 계산(테스트가 씀) |
| `KMA_APIHUB_KEY` | 기상청 API허브 인증키. 있으면 실시간 기상을 이어 받음; 커밋 금지 |
| `WEATHER_REFRESH_SECONDS` | API허브 조회 간격(초), 기본 300 |
| `VWORLD_API_KEY` | VWorld 키. 위성 배경 타일(서버), 항공사진 수관 추출·필지 수집 스크립트에 사용; 커밋 금지 |
| `VWORLD_DOMAIN` | VWorld 키 등록 도메인, 기본값 `http://localhost` |
| `DATA_GO_KR_API_KEY` | `scripts/fetch_building_ledger.py`, `scripts/fetch_kma_asos.py`용 공공데이터포털 키(Decoding); 커밋 금지 |
| `CLOUDFLARE_TUNNEL_TOKEN` | 선택적 Tunnel token; 커밋 금지 |
| `VISITOR_HASH_SALT` | 접속 기록의 방문자 id를 만드는 salt. 비우면 재시작마다 새로 뽑혀 id가 바뀜; 커밋 금지 |

Android 앱의 API 주소 `API_BASE_URL`은 환경 변수가 아니라 Gradle 속성입니다(위 "Android 실행").

## Cloudflare Tunnel

Cloudflare에서 Tunnel과 public hostname을 만든 후 service를 `http://api:8000`으로 지정하고 토큰을 `.env`에 넣습니다. 그런 다음 profile을 켭니다.

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile tunnel up --build
```

토큰이 없는 기본 실행에서는 cloudflared profile이 시작되지 않습니다.

### 접속 기록

uvicorn 기본 access log는 끄고(`--no-access-log`), `backend/app/access_log.py`가 요청마다 JSON 한 줄을 남깁니다. IP는 기록하지 않고 `CF-Connecting-IP`에 `VISITOR_HASH_SALT`를 붙인 해시 앞 12자리(`visitor`)만 남기며, 쿼리의 위도·경도는 소수점 3자리(약 100 m)로 줄입니다. `/health`는 남기지 않습니다. Docker 로그는 10 MB × 3개까지만 보관합니다.

```json
{"t": "2026-11-10T22:10:45+09:00", "visitor": "3f9a1c0e7b2d", "method": "GET", "path": "/api/route", "query": {"from_lat": "36.626", "from_lon": "127.460", "to_lat": "36.628", "to_lon": "127.458", "datetime": "2026-11-10T11:54:00+09:00"}, "status": 200, "ms": 412, "ua": "okhttp/4.12.0"}
```

방문자 수는 `docker logs osd-api-1 | jq -r .visitor | sort -u | wc -l`처럼 셉니다. 컨테이너를 새로 만들면(재배포) 이전 로그는 사라집니다.

## 테스트

```bash
PYTHONPATH=backend pytest backend/tests          # 백엔드
cd android && ./gradlew testDebugUnitTest        # Android 단위 테스트
```

GitHub Actions(`.github/workflows/ci.yml`)가 `main`으로의 push와 PR마다 두 가지를 모두 돌립니다. 백엔드 테스트는 `conftest.py`가 `DATABASE_URL`과 API 키를 지우므로 DB와 네트워크 없이 커밋된 `data/`만으로 돕니다.

- 공간: 태양 위치와 그림자 기하, 건물 스냅샷의 유효성(층수를 미터로 환산하지 않았는지 포함), 광선 추적 그늘·수관 투과율·SVF·지형 보간, 공용 격자 (`test_solar`, `test_shadow`, `test_snapshot`, `test_geometry_field`, `test_grid`)
- 대기: 일사 분리와 Tmrt·UTCI, 기상 스냅샷·API허브 변환과 이어 쓰기, 칸별 바람(합성 장면과 실제 장애물 래스터), 센서 QC (`test_thermal`, `test_comfort`, `test_weather`, `test_kma_hub`, `test_wind`, `test_sensors`)
- 통합: 체감온도 모델, 경로 비용과 모드, 위성 타일 범위, 모든 엔드포인트의 응답 형식 (`test_microclimate`, `test_routing`, `test_vworld_tiles`, `test_repository`, `test_api`)

대기 쪽 테스트는 `tests/fakes.py`로 공간 쪽 계약을 직접 만들어, 광선 추적이나 캠퍼스 데이터 없이도 돕니다.

## 이후 계획

1. 캠퍼스 가로수를 `data/cbnu_street_trees.geojson`에 입력
2. 앱의 `그림자` 모드도 지형·나무를 반영한 v1 모델 그늘로 교체
3. 높이가 없는 38동 처리 방침 결정 — 층수 환산(26동 추가) 도입 여부, 대장에 값이 있으나 OSM에 건물이 없는 4동의 OSM 기여
4. 센서 측정값 표시 — 기기별 밤 오프셋을 뺀 상대 변화로, 차폐통을 갖춘 재설치 후
5. `/api/shadows`의 낮은 고도 최대 길이 정책, 공간 bbox 쿼리
