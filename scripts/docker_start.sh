#!/bin/sh
# 컨테이너 시작 스크립트 (Railway)
#
# 시드를 빌드 시점이 아니라 시작 시점에 돌린다. 볼륨을 STATE_DIR에 마운트하면
# 이미지에 구워 둔 파일이 가려지기 때문이다 — 빌드에서 만든 graph.json은
# 첫 부팅에 사라지고 화면이 빈 채로 뜬다.
#
# 이미 그래프가 있으면 건드리지 않는다. 시드 스크립트는 기존 graph.json을 지우고
# 다시 만들기 때문에, 무조건 돌리면 가족이 쌓은 기억이 배포마다 날아간다.
set -e

STATE_DIR="${STATE_DIR:-data}"
GRAPH_FILE="$STATE_DIR/graph.json"

if [ -f "$GRAPH_FILE" ]; then
  echo "[start] 기존 그래프를 사용합니다: $GRAPH_FILE"
else
  echo "[start] 그래프가 없습니다. 시드를 만듭니다: $GRAPH_FILE"
  python scripts/seed_from_metadata.py
  python scripts/generate_profiles.py
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
