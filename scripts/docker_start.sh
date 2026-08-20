#!/bin/sh
# 컨테이너 시작 스크립트 (Railway)
#
# 시드를 빌드 시점이 아니라 시작 시점에 돌린다. 볼륨을 STATE_DIR에 마운트하면
# 이미지에 구워 둔 파일이 가려지기 때문이다 — 빌드에서 만든 graph.json은
# 첫 부팅에 사라지고 화면이 빈 채로 뜬다.
#
# "이미 데이터가 있나"는 파일 존재로 판정하지 않는다. DATABASE_URL이 있으면
# 그래프는 Postgres에 들어가고 graph.json은 아예 만들어지지 않아서, 파일로
# 판정하면 매 부팅마다 재시드 -> reset() -> TRUNCATE가 된다. 저장소에 직접
# 묻도록 판단을 시드 스크립트로 옮겼다 (--if-empty).
set -e

python scripts/seed_from_metadata.py --if-empty

# 프로필 크롭은 사진에서 다시 만들 수 있고, 같은 파일을 덮어쓴다.
# 볼륨이 새로 붙어 크롭만 사라진 경우에도 여기서 복구된다.
python scripts/generate_profiles.py

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
