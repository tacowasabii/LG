#!/bin/bash
# Family Memory Graph - 개발 서버 실행 스크립트

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🧠 Family Memory Graph - MVP 개발 서버"
echo "======================================="

# 1. Python venv 확인 및 생성
if [ ! -d "venv" ]; then
    echo "📦 Python 가상환경 생성 중..."
    python3 -m venv venv
fi

echo "📦 Python 의존성 설치 중..."
source venv/bin/activate
pip install --upgrade pip --quiet
# Python 3.14+ 호환을 위해 pydantic pre-release 허용
pip install -r backend/requirements.txt --pre --quiet

# 2. 샘플 데이터 시드 (graph.json이 없을 때만)
if [ ! -f "data/graph.json" ]; then
    echo "🌱 샘플 데이터 생성 중..."
    python scripts/seed_sample.py
fi

# 3. Frontend 의존성 확인
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Frontend 의존성 설치 중..."
    cd frontend && npm install && cd ..
fi

# 4. 서버 실행
echo ""
echo "🚀 서버 시작!"
echo "   Backend:  http://localhost:8000 (API docs: http://localhost:8000/docs)"
echo "   Frontend: http://localhost:5173"
echo ""
echo "   종료: Ctrl+C"
echo ""

# Backend와 Frontend 동시 실행
cd "$PROJECT_ROOT"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

cd frontend && npm run dev &
FRONTEND_PID=$!

# Ctrl+C 시 둘 다 종료
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
