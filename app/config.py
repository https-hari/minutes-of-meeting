from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
WHISPER_MODEL = "base"
LLM_MODEL = "llama-3.3-70b-versatile"
