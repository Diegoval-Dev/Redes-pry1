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

REMOTE_MCP_URL = os.getenv("REMOTE_MCP_URL")
REMOTE_MCP_PATH = os.getenv("REMOTE_MCP_PATH", "/rpc")

# ---- WARFRAME MCP (paths por defecto + env) ----
# Si no das MCP_WARFRAME_ARGS, intentamos <repo>/xavierlopez25-mwf-mcp/dist/index.js
WFM_DEFAULT_INDEX = os.path.join(PROJECT_ROOT, "mwf-mcp", "dist", "index.js")
MCP_WARFRAME_COMMAND = os.getenv("MCP_WARFRAME_COMMAND", "node")
MCP_WARFRAME_ARGS = os.getenv("MCP_WARFRAME_ARGS", WFM_DEFAULT_INDEX if os.path.exists(WFM_DEFAULT_INDEX) else "")

WFM_JWT = os.getenv("WFM_JWT")
WFM_BASE_URL = os.getenv("WFM_BASE_URL")          
WFM_LANGUAGE = os.getenv("WFM_LANGUAGE")
WFM_PLATFORM = os.getenv("WFM_PLATFORM")


# --------- Anki MCP ----------
# Recomendado: ejecutable local con Node
# MCP_ANKI_COMMAND=node
# MCP_ANKI_ARGS=D:/UVG/Redes/pry1/gxrco-anki-mcp/dist/cli.js
MCP_ANKI_COMMAND = os.getenv("MCP_ANKI_COMMAND", "node")
MCP_ANKI_ARGS = os.getenv("MCP_ANKI_ARGS", "D:/UVG/Redes/pry1/Anki-MCP/dist/cli.js")

# Rutas de base de datos y media (opcionales)
MCP_ANKI_DB_PATH = os.getenv("MCP_ANKI_DB_PATH", "")
MCP_ANKI_MEDIA_DIR = os.getenv("MCP_ANKI_MEDIA_DIR", "")