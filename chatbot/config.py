import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Falta OPENAI_API_KEY en .env")

GITHUB_PERSONAL_ACCESS_TOKEN = (
    os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    or os.getenv("GITHUB_TOKEN")
    or os.getenv("GH_TOKEN")
)

FS_ROOT = os.getenv("FS_ROOT", "D:/cosas/programass/UVG/Redes/pry1/Filesystem")

LOG_DIR = os.getenv("CHAT_LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
CHAT_LOG_FILE = os.path.join(LOG_DIR, "chat_host.jsonl")
