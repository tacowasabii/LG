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

# 시드는 빌드가 아니라 시작할 때 만든다 (scripts/docker_start.sh 주석 참고).
# 볼륨을 STATE_DIR에 마운트하면 빌드 때 만든 파일이 가려지기 때문이다.
COPY scripts/docker_start.sh ./scripts/docker_start.sh
RUN chmod +x scripts/docker_start.sh

# 상태(그래프·업로드·내보내기)는 여기에 쌓인다. 볼륨을 이 경로에 마운트한다.
# 읽기 전용 자산(data/metadata, data/photos)은 이미지에 그대로 남는다.
ENV STATE_DIR=/app/var
RUN mkdir -p /app/var

# 포트 설정
ENV PORT=8000
EXPOSE 8000

CMD ["./scripts/docker_start.sh"]
