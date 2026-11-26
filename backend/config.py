"""환경 설정 — 저장소 루트의 .env 또는 배포 플랫폼 환경 변수에서 로드."""
import os

from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
CATALOG_PATH = os.path.join(BACKEND_DIR, "data", "catalog.json")

# 실행 위치(cwd)와 무관하게 루트 .env를 읽는다. 이미 설정된 환경 변수가 우선.
load_dotenv(os.path.join(ROOT_DIR, ".env"))


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


APP_VERSION = "0.2.0"
IS_VERCEL = bool(os.getenv("VERCEL"))

# ── LLM ─────────────────────────────────────────────────────────
# auto: OPENROUTER_API_KEY → OpenRouter, 없으면 ANTHROPIC_API_KEY → Claude,
#       없으면 OPENAI_API_KEY → OpenAI, 모두 없으면 local(규칙 기반)
LLM_PROVIDER = _str("LLM_PROVIDER", "auto").lower()
OPENROUTER_API_KEY = _str("OPENROUTER_API_KEY")
OPENROUTER_MODEL = _str("OPENROUTER_MODEL", "anthropic/claude-opus-5.5")
OPENROUTER_BASE_URL = _str("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
ANTHROPIC_API_KEY = _str("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _str("ANTHROPIC_MODEL", "claude-opus-5-5")
# Claude effort: low | medium | high | xhigh | max (채팅 응답은 low로도 충분)
CLAUDE_EFFORT = _str("CLAUDE_EFFORT", "low").lower()
OPENAI_API_KEY = _str("OPENAI_API_KEY")
OPENAI_MODEL = _str("OPENAI_MODEL", "gpt-4o-mini")
ENABLE_WEB_SEARCH = _bool("ENABLE_WEB_SEARCH", True)
LLM_TIMEOUT_SECONDS = float(_str("LLM_TIMEOUT_SECONDS", "60") or 60)

# ── 저장소 ──────────────────────────────────────────────────────
# auto: Firebase 키가 있으면 firestore, Vercel이면 memory, 그 외(로컬)는 file
STORE_BACKEND = _str("STORE_BACKEND", "auto").lower()
DATA_FILE = _str("DATA_FILE", os.path.join(ROOT_DIR, ".data", "compass.json"))
FIREBASE_SERVICE_ACCOUNT_JSON = _str("FIREBASE_SERVICE_ACCOUNT_JSON")

# ── 서버 ────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [o.strip() for o in _str("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
HOST = _str("HOST", "127.0.0.1")
PORT = int(_str("PORT", "8000") or 8000)
