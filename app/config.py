from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
# llama-3.3-70b-versatile was retired by Groq; gpt-oss-120b supports JSON and tool calling
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# vector | keyword | hybrid | hybrid_rerank
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid_rerank")
RETRIEVAL_CANDIDATES = int(os.getenv("RETRIEVAL_CANDIDATES", "20"))   # pulled from each search before fusing
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))
