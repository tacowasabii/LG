import os
from pathlib import Path
from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent

# CWD와 무관하게 프로젝트 루트의 .env를 읽는다
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
MEDIA_DIR = DATA_DIR / "media"
GRAPH_FILE = DATA_DIR / "graph.json"
SAMPLE_DIR = DATA_DIR / "sample"

# Ensure directories exist
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

# EXAONE API - LG AI Research code-cli 게이트웨이
# 인증은 Authorization: Bearer가 아니라 x-api-key 헤더를 쓴다 (Bearer는 401).
EXAONE_API_URL = os.getenv("EXAONE_API_URL", "https://api.lgresearch.ai/v1/code-cli/chat/completions")
EXAONE_API_KEY = os.getenv("EXAONE_API_KEY", "")
# thinking / instant 두 종류. instant는 더 빠르고 추론을 하지 않는다.
EXAONE_MODEL = os.getenv("EXAONE_MODEL", "chatexaone-code-cli-claude-compatible-thinking")

# 샘플링 파라미터 - EXAONE CLI 가이드의 thinking 모델 권장값
EXAONE_TEMPERATURE = float(os.getenv("EXAONE_TEMPERATURE", "0.6"))
EXAONE_TOP_P = float(os.getenv("EXAONE_TOP_P", "0.8"))
EXAONE_TOP_K = int(os.getenv("EXAONE_TOP_K", "20"))
EXAONE_MIN_P = float(os.getenv("EXAONE_MIN_P", "0.0"))
EXAONE_PRESENCE_PENALTY = float(os.getenv("EXAONE_PRESENCE_PENALTY", "1.5"))
EXAONE_REPETITION_PENALTY = float(os.getenv("EXAONE_REPETITION_PENALTY", "1.0"))

# 추론(thinking) 모드. 끄면 응답이 빨라지지만 근거 추론 품질이 떨어진다.
EXAONE_ENABLE_THINKING = os.getenv("EXAONE_ENABLE_THINKING", "true").lower() == "true"
# 추론도 출력 토큰을 소모하므로 답변 예산에 여유분을 더해준다 (모델 출력 상한 20000)
EXAONE_THINKING_BUDGET = int(os.getenv("EXAONE_THINKING_BUDGET", "4096"))

EXAONE_TIMEOUT = float(os.getenv("EXAONE_TIMEOUT", "120"))

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
