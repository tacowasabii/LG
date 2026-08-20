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

# 시드와 프로필을 한 프로세스에서 돌린다. 따로 띄우면 backend를 두 번
# import하고 그때마다 langchain·boto3·psycopg가 딸려 와서, 부팅 전에 같은 스택을
# 세 번 읽었다 (uvicorn까지). 그 시간이 헬스체크 창을 넘겨 배포가 실패했다.
# 프로필은 이미 있으면 건너뛴다 — 자세한 사정은 scripts/boot.py 주석에 있다.
python scripts/boot.py

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
