import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Falta OPENAI_API_KEY en .env")

LOG_DIR = os.getenv("CHAT_LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
CHAT_LOG_FILE = os.path.join(LOG_DIR, "chat_host.jsonl")
