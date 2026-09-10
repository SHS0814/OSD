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

`DATABASE_URL`이 없으면 API는 커밋된 `data/cbnu_buildings.geojson` 스냅샷을 읽으므로 PostGIS 없이도 개발할 수 있습니다.

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

timezone 없는 값은 `Asia/Seoul`로 해석합니다. offset이 있는 값은 같은 순간의 서울 시각으로 변환합니다. 결과는 현지 ISO datetime, 태양 고도·방위각, 그림자 GeoJSON과 전체/높이 보유/누락 건물 수를 포함합니다. 태양 고도가 0° 이하면 `features`가 빈 컬렉션이며, 직접 meter 높이가 없는 건물은 그림자 계산에서 제외됩니다.

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
- 직접 meter 높이가 없는 건물에는 층수 환산이나 임의 기본 높이를 적용하지 않으므로 그림자가 표시되지 않습니다.

## 데이터와 PostGIS

`data/cbnu_buildings.geojson`은 OpenStreetMap 충북대학교 relation `6705106` 경계 안에서 수집한 실제 건물 외곽선 117개의 고정 스냅샷입니다. geometry와 이름은 OSM을 기준으로 하며 이름은 `name:ko → name → ref → OSM ID` 순서로 선택합니다. 앱 실행 중에는 OSM이나 VWorld API를 호출하지 않습니다.

현재 커밋된 스냅샷에는 OSM `height`에 직접 meter 값이 있는 건물 20개만 높이가 있으며 나머지 97개는 `height_m=null`입니다. VWorld `LT_C_BLDGINFO` 결합은 수집 당시 `VWORLD_API_KEY`가 설정되지 않아 수행되지 않았고, 이 상태와 수집·매칭 통계는 `data/cbnu_buildings_match_report.json`에 기록했습니다. 추후 결합할 때는 EPSG:5179에서 면적 중첩률 70% 이상, 면적비 0.5–2.0, 중심점 거리 15m 이하인 일대일 대응만 허용하고 VWorld 직접 `height`를 우선합니다. 층수 환산값은 사용하지 않습니다.

PostGIS 사용 시 API 시작 과정이 스냅샷을 idempotent upsert합니다. 기존 `manual-mvp` 행과 스냅샷에서 사라진 이전 OSM 행은 제거되어 신규 DB와 기존 DB 모두 같은 117개로 수렴합니다.

OSM 데이터는 [Open Database License(ODbL)](https://www.openstreetmap.org/copyright)를 따르며 Android 지도에 `© OpenStreetMap contributors · ODbL` attribution을 표시합니다.

## 환경 변수

| 이름 | 기본값/역할 |
|---|---|
| `POSTGRES_DB` | `campus_shade` |
| `POSTGRES_USER` | `campus_shade` |
| `POSTGRES_PASSWORD` | 개발 기본값은 `change-me`; 배포 전 변경 |
| `DATABASE_URL` | API의 내부 PostgreSQL DSN |
| `BUILDING_DATA_PATH` | DB 미사용 및 DB 동기화에 사용할 GeoJSON 경로 |
| `VWORLD_API_KEY` | 일회성 VWorld 스냅샷 수집용 키; 저장소에 커밋 금지 |
| `VWORLD_DOMAIN` | VWorld 키 등록 도메인, 로컬 수집 기본값 `http://localhost` |
| `CLOUDFLARE_TUNNEL_TOKEN` | 선택적 Tunnel token; 저장소에 커밋 금지 |
| `API_BASE_URL` | Android build용 API base URL |

## Cloudflare Tunnel

Cloudflare에서 Tunnel과 public hostname을 만든 후 service를 `http://api:8000`으로 지정하고 토큰을 `.env`에 넣습니다. 그런 다음 profile을 켭니다.

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile tunnel up --build
```

토큰이 없는 기본 실행에서는 cloudflared profile이 시작되지 않습니다.

## 테스트 범위

테스트는 낮/밤 태양 고도, 태양 방위각 범위, 45°에서 20m 높이의 20m 그림자, 반대 방향 벡터, polygon translation/sweep, 건물 및 그림자 GeoJSON API, 야간 빈 응답을 검증합니다. 스냅샷 테스트는 정확히 117개의 유효한 Polygon/MultiPolygon, 중복 없는 OSM ID, 직접 높이 출처와 매칭 리포트 집계를 검사합니다.

## 이후 계획

1. VWorld API 키를 구성해 `LT_C_BLDGINFO` 직접 높이를 공간 매칭한 새 스냅샷 생성
2. 관측 좌표를 고정 캠퍼스 설정으로 제한하거나 요청 viewport로 필터링
3. 캐시, 공간 bbox 쿼리, 낮은 고도 최대 길이 정책 추가
4. 센서/BLE 업로드 모델을 별도 모듈로 추가
5. 실측 기후 정보와 보행 네트워크를 결합한 쾌적 경로 추천
