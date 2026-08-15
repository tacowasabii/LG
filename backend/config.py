import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MEDIA_DIR = DATA_DIR / "media"
GRAPH_FILE = DATA_DIR / "graph.json"
SAMPLE_DIR = DATA_DIR / "sample"

# Ensure directories exist
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

# EXAONE API
EXAONE_API_URL = os.getenv("EXAONE_API_URL", "https://api-cloud.lgresearch.ai/api/v1/chat/completions")
EXAONE_API_KEY = os.getenv("EXAONE_API_KEY", "")
EXAONE_MODEL = os.getenv("EXAONE_MODEL", "exaone-deep")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
