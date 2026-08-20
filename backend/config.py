import os
from pathlib import Path
from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent

# CWD와 무관하게 프로젝트 루트의 .env를 읽는다
load_dotenv(BASE_DIR / ".env")

# 저장소에 함께 들어오는 읽기 전용 자산 (metadata, photos, video, goldset)
DATA_DIR = BASE_DIR / "data"
METADATA_DIR = DATA_DIR / "metadata"
PHOTOS_DIR = DATA_DIR / "photos"
VIDEO_DIR = DATA_DIR / "video"
PROFILES_DIR = DATA_DIR / "profiles"
GOLDSET_FILE = DATA_DIR / "goldset.json"
SAMPLE_DIR = DATA_DIR / "sample"

# 실행 중에 쌓이는 상태. 배포에서는 볼륨을 여기에 마운트한다.
#
#   STATE_DIR=/app/var  +  /app/var 볼륨
#
# 읽기 전용 자산(data/)과 나눠 두지 않으면, data/ 위에 볼륨을 마운트하는 순간
# 시드 원본(metadata·photos)까지 가려져 첫 부팅에서 빈 그래프가 된다.
# 기본값은 data/ 라서 로컬 개발은 지금까지와 똑같이 동작한다.
STATE_DIR = Path(os.getenv("STATE_DIR", str(DATA_DIR)))

MEDIA_DIR = STATE_DIR / "media"
GRAPH_FILE = STATE_DIR / "graph.json"
EXPORT_DIR = STATE_DIR / "exports"
SPACE_FILE = STATE_DIR / "family_space.json"
TRUST_REPORT_FILE = STATE_DIR / "trust_report.json"

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

# 의도 분석(질의 계획)용 모델. 구조화 추출이라 추론 없는 instant가 빠르고 충분하다.
EXAONE_PLANNER_MODEL = os.getenv(
    "EXAONE_PLANNER_MODEL", "chatexaone-code-cli-claude-compatible-instant"
)

# LangGraph 기반 질의 계획 사용 여부.
# 끄면 기존 키워드 검색 경로로 동작한다 (LLM 호출 1회, 응답이 빠르다).
CHAT_QUERY_PLANNING = os.getenv("CHAT_QUERY_PLANNING", "true").lower() == "true"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# --- 앱 주소 ---
# 초대 링크에 쓰는 프론트 주소. 백엔드와 프론트가 다른 도메인에 올라가므로
# 서버는 자기 주소로 초대 링크를 만들 수 없다. 비워 두면 서버는 경로만 내려주고
# 화면이 자기 origin을 붙인다 (브라우저 안에서는 그게 항상 맞다).
#
#   APP_BASE_URL="https://my-homestory.vercel.app"
APP_BASE_URL = os.getenv("APP_BASE_URL", "").rstrip("/")


# --- CORS ---
# 배포된 프론트의 주소를 허용한다. 쉼표로 여러 개.
#   ALLOWED_ORIGINS="https://my-homestory.vercel.app"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

# Vercel은 커밋마다 프리뷰 도메인을 새로 만든다. 하나씩 등록할 수 없어 정규식으로 받는다.
# 이 API에는 인증이 없어서 CORS가 데이터를 지켜 주지는 않는다 (curl로는 그냥 열린다).
# 여기서 하는 일은 브라우저가 정상 동작하게 만드는 것뿐이다.
ALLOWED_ORIGIN_REGEX = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://.*\.vercel\.app")

# 개발 서버는 항상 허용한다
DEV_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
