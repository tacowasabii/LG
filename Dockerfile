FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY backend/ ./backend/
COPY data/ ./data/
COPY scripts/ ./scripts/

# 시드 데이터 생성 (graph.json이 없으면)
RUN python scripts/seed_from_metadata.py

# 프로필 생성
RUN pip install --no-cache-dir pillow && python scripts/generate_profiles.py

# 포트 설정
ENV PORT=8000
EXPOSE 8000

# 실행 — Railway는 PORT를 주입한다. 고정하면 라우팅이 어긋날 수 있다.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
