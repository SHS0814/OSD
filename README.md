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
data/     캠퍼스 경계·건물·건축물대장 스냅샷 (커밋된 고정 데이터)
scripts/  스냅샷을 다시 만드는 일회성 수집 스크립트
docs/     조사 기록
infra/    Docker Compose, PostGIS 초기화
```

`scripts/`는 앱이나 API가 실행 중에 호출하지 않습니다. `data/`의 스냅샷을 재생성할 때만 사람이 직접 돌립니다.

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

기본 API 주소는 Android 에뮬레이터에서 호스트를 가리키는 `http://10.0.2.2:8000/`입니다. URL은 `/`로 끝나야 합니다.

### 실기기로 테스트할 때

`10.0.2.2`는 에뮬레이터 전용 주소라 실기기에서는 닿지 않습니다. `adb reverse`로 폰의 `localhost`를 개발 PC에 연결하는 방식이 가장 안정적입니다. 공유기나 IP가 바뀌어도 영향을 받지 않고, `localhost`는 이미 cleartext 예외에 들어 있습니다.

```bash
# 백엔드를 LAN에 바인딩 (기본값 127.0.0.1로는 폰이 못 붙습니다)
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000

# 폰의 localhost:8000 -> PC의 8000
adb reverse tcp:8000 tcp:8000
```

터널은 폰을 다시 연결할 때마다 사라지므로 그때마다 `adb reverse`를 다시 실행해야 합니다.

앱 주소는 Gradle 속성으로 바꿉니다. **Android Studio의 Run 버튼은 `-P` 옵션을 붙일 수 없어 기본값인 `10.0.2.2`로 되돌아갑니다.** 홈 디렉터리의 `~/.gradle/gradle.properties`에 넣어두면 Run 버튼에도 적용되고, 커밋되지 않아 팀원 설정과 충돌하지 않습니다.

```bash
echo 'API_BASE_URL=http://localhost:8000/' >> ~/.gradle/gradle.properties
```

CLI로 직접 지정할 수도 있습니다.

```bash
cd android
./gradlew installDebug -PAPI_BASE_URL=https://shade-api.example.com/
```

로컬 HTTP 예외는 `10.0.2.2`와 `localhost`에만 허용됩니다. debug 빌드에는 `app/src/debug/`의 완화된 정책이 적용되어 임의 호스트로 평문 요청이 가능하고, release 빌드는 엄격한 정책을 유지합니다. 운영에서는 HTTPS Tunnel URL을 사용하십시오.

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

## 체감온도 계산 (v0)

### `GET /api/microclimate`

캠퍼스를 10m 격자로 나눠 선택 시각의 **추정 체감온도(UTCI)** 를 계산합니다. 시간 형식은 `/api/shadows`와 같고 좌표는 받지 않습니다.

```text
/api/microclimate?datetime=2025-08-05T15:00:00+09:00
```

응답에는 사용한 기상값(`weather`), 직달·산란 일사(`irradiance`), 격자 정보(`grid`), 요약(`summary`)과 격자별 `utci`, `mrt`(평균복사온도), `sunlit`(양지 비율) 배열이 들어 있습니다. 배열은 북서쪽 모서리부터 행 우선 순서이며, 캠퍼스 밖이나 건물 안 셀은 `null`입니다. gzip 압축 시 약 16KB입니다.

계산은 세 단계입니다.

1. 기상청 청주 ASOS의 시간 일사량을 Erbs 모델로 직달과 산란으로 나눕니다. 일사량은 직전 1시간 누적값이라, 그 시간의 청명도를 유지한 채 요청 시각의 태양 고도에 맞춰 순간값으로 바꿉니다.
2. 건물 그림자(양지 비율)와 천공률(SVF)로 셀마다 평균복사온도를 계산합니다. SVF는 건물 배치에서 36방위·200m 범위로 한 번만 계산해 둡니다.
3. 기온·습도·바람과 함께 `pythermalcomfort`로 UTCI를 구합니다.

v0의 한계:

- 기온·습도·바람은 캠퍼스 전체에 같은 기상청 값을 씁니다. 지점별 차이는 복사(그늘) 효과만 반영됩니다.
- 지형, 나무, 지면 재질은 아직 반영하지 않습니다. 지면 반사율은 0.15로 고정입니다.
- 높이가 없는 건물은 그림자와 SVF 계산에서 빠집니다.
- 기상 스냅샷 기간(2025-06-01 ~ 2026-09-26) 밖의 시각은 404를 반환합니다.

지면 온도는 `기온 + 0.012 × 지면 일사량`으로 근사합니다. 계수는 청주 ASOS에서 일사 300W/m² 이상인 3,117시간의 `(지면온도 − 기온) / 일사량`으로 맞췄습니다(중앙값 0.0113, 최소제곱 0.0129).

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
- 직접 meter 높이가 없는 건물에는 층수 환산이나 임의 기본 높이를 적용하지 않으므로 그림자가 표시되지 않습니다. 현재 105동 중 38동이 여기에 해당합니다.

## 데이터와 PostGIS

`data/`의 파일은 모두 커밋된 고정 스냅샷입니다. **앱과 API는 실행 중에 OSM·VWorld·data.go.kr을 호출하지 않습니다.**

| 파일 | 내용 |
|---|---|
| `cbnu_campus_boundary.geojson` | OSM relation `6705106` 경계 (outer 링만, 87.9 ha) |
| `cbnu_buildings.geojson` | 경계 안 건물 **105동** |
| `cbnu_building_ledger.json` | 건축물대장 표제부 132건 |
| `cbnu_campus_parcels.json` | 대장 조회용 필지(PNU) 24개 |
| `cbnu_building_aliases.json` | 자동 매칭이 닿지 않는 건물의 수동 대응표 |
| `cbnu_buildings_match_report.json` | 수집·필터·높이 출처 통계 |
| `kma_asos_131_hourly.csv` | 기상청 청주 ASOS(131) 시간자료 11,592시간 (2025-06-01 ~ 2026-09-26) |
| `kma_asos_131_hourly.meta.json` | 위 자료의 출처·기간·열 설명 |

지오메트리와 이름은 OSM을 기준으로 하며 이름은 `name:ko → name → ref → OSM ID` 순서로 선택합니다. 온실(`building=greenhouse`) 30동과 200㎡ 미만 22동은 제외했습니다. 제외된 52동 중 높이를 가진 건물은 하나도 없어 그림자는 줄지 않았습니다.

높이는 **국토교통부 건축물대장 표제부**를 우선하고 OSM `height` 태그를 보조로 씁니다. 양쪽에 값이 있는 22동을 비교하면 대장이 더 큰 경우가 19건, OSM 값은 22건 모두 정수인 반면 대장은 1건만 정수입니다. OSM 값이 매퍼의 내림 추정치이기 때문입니다. **층수는 미터로 환산하지 않습니다** — 추정값이 실측값과 구분 없이 지도에 나가는 것을 피하기 위해서입니다.

현재 105동 중 **67동**에 높이가 있습니다(대장 58, OSM 9). 나머지 38동 중 18동은 대장 레코드는 있으나 높이 칸이 비어 있어 공개 API로는 채울 수 없고, 4동은 대장에 값이 있으나 OSM에 건물이 없습니다.

출처별 판단 근거, VWorld API의 좌표계 함정, 매칭 과정에서 발생한 오류와 대응은 저장소에 포함하지 않는 작업 노트 `docs/building-heights.md`에 따로 정리했습니다.

PostGIS 사용 시 API 시작 과정이 스냅샷을 idempotent upsert합니다. 기존 `manual-mvp` 행과 스냅샷에서 사라진 이전 OSM 행은 제거되어 신규 DB와 기존 DB 모두 같은 내용으로 수렴합니다.

OSM 데이터는 [Open Database License(ODbL)](https://www.openstreetmap.org/copyright)를 따르며 Android 지도에 `© OpenStreetMap contributors · ODbL` attribution을 표시합니다.

## 환경 변수

| 이름 | 기본값/역할 |
|---|---|
| `POSTGRES_DB` | `campus_shade` |
| `POSTGRES_USER` | `campus_shade` |
| `POSTGRES_PASSWORD` | 개발 기본값은 `change-me`; 배포 전 변경 |
| `DATABASE_URL` | API의 내부 PostgreSQL DSN |
| `BUILDING_DATA_PATH` | DB 미사용 및 DB 동기화에 사용할 GeoJSON 경로 |
| `CAMPUS_BOUNDARY_PATH` | 체감온도 격자 범위로 쓰는 캠퍼스 경계 GeoJSON |
| `WEATHER_DATA_PATH` | 체감온도 계산에 쓰는 ASOS 시간자료 CSV |
| `VWORLD_API_KEY` | `scripts/fetch_campus_parcels.py` 전용 키; 저장소에 커밋 금지 |
| `VWORLD_DOMAIN` | VWorld 키 등록 도메인, 로컬 수집 기본값 `http://localhost` |
| `DATA_GO_KR_API_KEY` | `scripts/fetch_building_ledger.py`, `scripts/fetch_kma_asos.py`용 공공데이터포털 키(Decoding); 커밋 금지 |
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

스냅샷 테스트는 105개의 유효한 Polygon/MultiPolygon, 중복 없는 OSM ID, 허용된 높이 출처, 리포트 집계, 전 건물이 캠퍼스 경계 안에 있는지를 검사합니다. **층수가 미터로 환산되지 않았는지도 검증합니다** — 층수만 있는 건물은 `height_m`이 반드시 `null`이어야 합니다.

체감온도 테스트는 일사 분리가 전일사를 보존하는지, 양지와 그늘의 평균복사온도 차이가 문헌 범위(10~35°C)에 드는지, 이슬점으로 계산한 습도가 ASOS 관측과 맞는지, 기상값의 시간 보간과 야간 일사 0, 격자 응답 형식과 스냅샷 기간 밖 404를 검증합니다.

## 이후 계획

1. 센서/BLE 업로드 모델을 별도 모듈로 추가 (과제 요건)
2. 높이가 없는 38동 처리 방침 결정 — 층수 환산(26동 추가) 도입 여부, 대장에 값이 있으나 OSM에 건물이 없는 4동의 OSM 기여
3. 관측 좌표를 고정 캠퍼스 설정으로 제한하거나 요청 viewport로 필터링
4. 캐시, 공간 bbox 쿼리, 낮은 고도 최대 길이 정책 추가
5. 실측 기후 정보와 보행 네트워크를 결합한 쾌적 경로 추천
