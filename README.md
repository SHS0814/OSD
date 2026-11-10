# Campus Shade Map MVP

충북대학교 캠퍼스의 그늘과 체감온도를 지도에 보여 주는 Android + FastAPI 프로젝트입니다. 지금은 저장소 뼈대와 `/health`만 있습니다.
  │  Astral / Shapely / PyProj
  └─ 태양 위치 및 2D 건물 그림자
### 로컬 Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend uvicorn app.main:app --reload
PYTHONPATH=backend pytest backend/tests
```
- 토지피복지도는 캠퍼스 안 작은 숲·가로수·중정의 나무를 대부분 놓치므로, 빠진 나무는 `data/cbnu_street_trees.geojson`에 직접 입력하면 서버를 다시 시작할 때 반영됩니다(형식은 파일의 `metadata` 참고).
현재 한계:
`data/`의 파일은 모두 커밋된 고정 스냅샷입니다. **앱과 API는 실행 중에 OSM·VWorld·data.go.kr을 호출하지 않습니다.**
