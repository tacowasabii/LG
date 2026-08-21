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
# 사진에서 미리 만들어 둔 미세 모션 클립 (scripts/build_motion_covers.py).
# 사진과 같이 읽기 전용 자산이다 — 시드가 MEDIA_DIR/motion으로 복사한다.
MOTION_DIR = DATA_DIR / "motion"
MOTION_MANIFEST_FILE = MOTION_DIR / "manifest.json"
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
# 런타임에 만든 미세 모션 클립의 목록과 지출 기록. data/ 는 배포에서 읽기
# 전용이라(이미지에 구워져 있다) 쓰는 것은 반드시 이쪽이어야 한다.
MOTION_RUNTIME_MANIFEST_FILE = STATE_DIR / "motion_manifest.json"
MOTION_LEDGER_FILE = STATE_DIR / "motion_spend.json"
# 추억마다 고른 대표 사진. 한 번 고른 것을 지켜야 한다 — 고를 때마다 달라지면
# 매번 다른 사진을 만들어 지출이 늘어난다 (cover_picker).
MOTION_COVERS_FILE = STATE_DIR / "motion_covers.json"
# 자동 생성에서 빼 둘 추억 (기능을 켠 시점에 이미 있던 것). 처음 물을 때 적힌다.
MOTION_BASELINE_FILE = STATE_DIR / "motion_baseline.json"
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


# --- Bedrock (선택) ---
# EXAONE은 한국어 서술·호칭 해석처럼 "말맛"이 필요한 곳에 쓰고, JSON 조각만 뽑는
# 기계적인 호출(질의 계획·답변 추출)은 이쪽으로 보낼 수 있다. 질의 계획은 채팅
# 응답 시간에 그대로 더해지므로 빠른 모델이 유리하다.
#
# 자격증명은 boto3 기본 순서를 따른다 (.env의 AWS_* -> 환경변수 -> ~/.aws).
AWS_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "").strip()
AWS_PROFILE = os.getenv("AWS_PROFILE", "").strip()

# us-east-1 기준. 다른 모델로 바꾸려면 이 한 줄만 고친다 (Nova·Llama도 같은 API다).
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
BEDROCK_TIMEOUT = float(os.getenv("BEDROCK_TIMEOUT", "30"))

# 용도별 제공자: bedrock | exaone
# 기본값이 bedrock이지만, 자격증명이 없으면 자동으로 EXAONE으로 돌아간다 —
# 설정하지 않은 사람의 화면이 깨지지 않게.
# FriendliAI — EXAONE을 공용 인터넷으로 서비스하는 경로.
# 사내망 게이트웨이(api.lgresearch.ai)는 사설 주소라서 배포 서버에서 닿지 않는다.
# 배포에서도 EXAONE으로 답하려면 이쪽을 쓴다. OpenAI 호환이고 인증은 Bearer다.
FRIENDLI_API_URL = os.getenv(
    "FRIENDLI_API_URL", "https://api.friendli.ai/dedicated/v1/chat/completions"
)
FRIENDLI_TOKEN = os.getenv("FRIENDLI_TOKEN", "").strip()
# 전용 엔드포인트 ID가 모델 이름 자리에 들어간다
FRIENDLI_MODEL = os.getenv("FRIENDLI_MODEL", "depe675tjc2rcpo").strip()
FRIENDLI_TEMPERATURE = float(os.getenv("FRIENDLI_TEMPERATURE", "1.0"))
FRIENDLI_TOP_P = float(os.getenv("FRIENDLI_TOP_P", "0.95"))
FRIENDLI_PRESENCE_PENALTY = float(os.getenv("FRIENDLI_PRESENCE_PENALTY", "0.0"))
FRIENDLI_ENABLE_THINKING = os.getenv("FRIENDLI_ENABLE_THINKING", "true").lower() == "true"
FRIENDLI_TIMEOUT = float(os.getenv("FRIENDLI_TIMEOUT", "120"))

# 채팅 답변을 어디로 보낼지. 기본은 EXAONE이다 — 사내망에서는 그게 동작하고,
# 프롬프톤 산출물이니 답변만은 EXAONE으로 두는 게 맞다. 다만 EXAONE 게이트웨이는
# 사내망 사설 주소(10.x)라서 공용 클라우드에 배포하면 닿지 않는다. 배포에서는
# 이 값을 bedrock으로 주면 답변도 모델이 만든다.
LLM_ANSWER_PROVIDER = os.getenv("LLM_ANSWER_PROVIDER", "exaone").strip().lower()
LLM_PLAN_PROVIDER = os.getenv("LLM_PLAN_PROVIDER", "bedrock").strip().lower()
LLM_EXTRACT_PROVIDER = os.getenv("LLM_EXTRACT_PROVIDER", "bedrock").strip().lower()


# --- 미세 모션 클립 ---
# Film을 만들 때 클립이 없는 사진을 그 자리에서 만들지 여부.
#
# 켜면 돈이 나간다. 그리고 이 API에는 인증이 없어서(CORS는 브라우저만 막는다)
# 주소를 아는 누구나 생성을 일으킬 수 있다. 그래서 상한을 함께 둔다 —
# MOTION_AUTOGEN_MAX 회를 넘으면 더 만들지 않고, 클립이 없는 사진은 원래대로
# CSS 카메라 움직임으로 돈다. 세는 값은 STATE_DIR에 남아 재시작에도 유지된다.
#
# FAL_KEY가 없거나 ffmpeg가 없으면 이 값과 무관하게 꺼진 것처럼 동작한다.
MOTION_AUTOGEN = os.getenv("MOTION_AUTOGEN", "false").lower() == "true"
# 480p 한 건이 약 $0.2다. 기본 50건 = 약 $10.
MOTION_AUTOGEN_MAX = int(os.getenv("MOTION_AUTOGEN_MAX", "50"))
# 추억 하나에서 움직이게 만들 대표 사진 수의 상한.
#
# 사진이 이 수보다 적으면 전부 만든다. 많으면 대표를 골라 그만큼만 만든다 —
# 사진 백 장인 앨범에서 전부 만들면 지출이 한 번에 튄다.
MOTION_COVERS_PER_EVENT = int(os.getenv("MOTION_COVERS_PER_EVENT", "3"))

# 앞으로 생기는 추억만 만들지 여부.
#
# 켜면(기본) 기능을 처음 쓰는 시점의 추억 목록을 기준선으로 적어 두고, 그 뒤에
# 만들어진 추억만 자동 생성한다. 이미 쌓인 앨범 전체를 한꺼번에 만들면 지출이
# 한 번에 튀기 때문이다 — 기존 추억에 클립을 넣으려면 스크립트로 미리 만든다
# (scripts/build_motion_covers.py).
#
# false로 두면 기존 추억도 대상이 된다.
MOTION_AUTOGEN_NEW_ONLY = os.getenv("MOTION_AUTOGEN_NEW_ONLY", "true").lower() == "true"

# 기준선을 환경변수로 직접 지정한다. 파일보다 우선한다.
#
# 배포 볼륨에 잘못 적힌 기준선을 고칠 때 쓴다 — 컨테이너에 들어가 파일을 지울 수
# 없으니 밖에서 덮을 길이 필요하다. 빈 값으로 두면("MOTION_BASELINE_EVENT_IDS=")
# 제외할 추억이 없다는 뜻이고, 그러면 모든 추억이 자동 생성 대상이 된다.
#
#   MOTION_BASELINE_EVENT_IDS="E01,E02,E03,E04,E05,E06,E07,E08"
_baseline_env = os.getenv("MOTION_BASELINE_EVENT_IDS")
MOTION_BASELINE_EVENT_IDS = (
    None if _baseline_env is None
    else [x.strip() for x in _baseline_env.split(",") if x.strip()]
)

# 생성·후처리 기본값. 왜 이 값인지는 README "미세 모션 클립" 절에 있다.
MOTION_RESOLUTION = os.getenv("MOTION_RESOLUTION", "480p")
MOTION_SOURCE_SECONDS = int(os.getenv("MOTION_SOURCE_SECONDS", "5"))
MOTION_USE_SECONDS = float(os.getenv("MOTION_USE_SECONDS", "2.0"))
# crossfade | pingpong | none
MOTION_LOOP_MODE = os.getenv("MOTION_LOOP_MODE", "none")
MOTION_CROSSFADE = float(os.getenv("MOTION_CROSSFADE", "0.5"))

# fal API 키. 없으면 런타임 생성이 꺼진다 (미리 만들어 커밋한 클립은 그대로 돈다).
FAL_KEY = os.getenv("FAL_KEY", "").strip()


# --- 저장소 ---
# 값이 있으면 Postgres, 없으면 graph.json 한 개를 쓴다.
# Railway에서 Postgres를 붙이면 DATABASE_URL이 자동으로 주입된다.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


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
