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

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

FS_ROOT = os.getenv("FS_ROOT", os.path.join(PROJECT_ROOT, "Filesystem"))

os.makedirs(FS_ROOT, exist_ok=True)
LOG_DIR = os.getenv("CHAT_LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
CHAT_LOG_FILE = os.path.join(LOG_DIR, "chat_host.jsonl")
