from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
# fastembed runs the same two models with ONNX Runtime instead of PyTorch: ~300 MB of RAM instead
# of ~1.2 GB, so the API fits a free 512 MB server. "torch" uses sentence-transformers.
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "fastembed")
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR") or None
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
# llama-3.3-70b-versatile was retired by Groq; gpt-oss-120b supports JSON and tool calling
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# vector | keyword | hybrid | hybrid_rerank
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid_rerank")
RETRIEVAL_CANDIDATES = int(os.getenv("RETRIEVAL_CANDIDATES", "20"))   # pulled from each search before fusing
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))

# ---- auth (Supabase) ----
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")      # only for projects on the legacy HS256 secret
AUTH_DISABLED = os.getenv("AUTH_DISABLED") == "1"            # local development: everyone is user "local"

# ---- transcription ----
TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "groq")   # groq | local
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
MAX_AUDIO_MB = int(os.getenv("MAX_AUDIO_MB", "25"))              # Groq's upload limit on the free tier

# ---- web ----
# comma-separated, e.g. "http://localhost:3000,https://mom.vercel.app"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
