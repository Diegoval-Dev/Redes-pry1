import sys, json, traceback, os, time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from .tools import TOOLS, TOOL_IMPL

PROTOCOL_VERSION = "2025-06-18"

# -------- Config de logging ----------
LOG_FILE = os.environ.get("MCP_LOG_FILE", os.path.join("logs", "invest_mcp_server.log"))
LOG_LEVEL = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()  # INFO|DEBUG|ERROR

def _ensure_log_dir():
    d = os.path.dirname(LOG_FILE)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def _writeline(s: str) -> None:
    try:
        _ensure_log_dir()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass
    # También a stderr para anfitriones que leen logs de ahí
    sys.stderr.write(s + "\n")
    sys.stderr.flush()

def log_json(event: str, **fields: Any) -> None:
    rec = {"ts": now_ts(), "event": event}
    rec.update(fields)
    _writeline(json.dumps(rec, ensure_ascii=False))

def jprint(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def rsp_result(_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": _id, "result": result}

def rsp_error(_id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err = {"jsonrpc": "2.0", "id": _id, "error": {"code": code, "message": message}}
    if data is not None:
        err["error"]["data"] = data
    return err

# -------- Handler de requests MCP ----------
def handle_request(req: Dict[str, Any]) -> Optional[bool]:
    """
    Retorna True si se debe terminar (shutdown), None/False en caso contrario.
    """
    t0 = time.perf_counter()
    method = req.get("method")
    _id = req.get("id")
    is_notification = _id is None

    log_json("request", method=method, id=_id, has_params=("params" in req))

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}, "logging": {}},
                "serverInfo": {
                    "name": "uvg-invest-mcp-local",
                    "title": "UVG MCP Inversiones (Local) by Diegoval-dev",
                    "version": "0.1.0"
                },
                "instructions": (
                    "Servidor MCP local de inversiones con herramientas: "
                    "price_quote, risk_metrics, build_portfolio, rebalance_plan. "
                    "Todos los retornos incluyen structuredContent y content."
                )
            }
            jprint(rsp_result(_id, result))
            return None

        if method == "notifications/initialized":
            log_json("info", msg="Cliente indicó initialized.")
            return None

        if method in ("ping", "notifications/ping"):
            if not is_notification:
                jprint(rsp_result(_id, {"ok": True}))
            return None

        if method == "shutdown":
            if not is_notification:
                jprint(rsp_result(_id, {"ok": True}))
            log_json("info", msg="Recibido shutdown. Cerrando servidor.")
            return True

        if method == "tools/list":
            result = {"tools": TOOLS, "nextCursor": None}
            jprint(rsp_result(_id, result))
            return None

        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str):
                err = rsp_error(_id, -32602, "Invalid 'name' for tools/call")
                jprint(err)
                return None
            impl = TOOL_IMPL.get(name)
            if impl is None:
                err = rsp_error(_id, -32601, f"Unknown tool: {name}")
                jprint(err)
                return None
            result = impl(arguments)
            jprint(rsp_result(_id, result))
            return None

        if not is_notification:
            err = rsp_error(_id, -32601, f"Method not found: {method}")
            jprint(err)
        else:
            log_json("warn", msg="Notificación desconocida", method=method)

    except ValueError as ve:
        if _id is not None:
            err = rsp_error(_id, -32602, "Invalid params", {"detail": str(ve)})
            jprint(err)
        log_json("error", where="handle_request", method=method, id=_id, detail=str(ve))
    except Exception:
        tb = traceback.format_exc()
        if _id is not None:
            err = rsp_error(_id, -32000, "Internal server error")
            jprint(err)
        log_json("error", where="handle_request", method=method, id=_id, traceback=tb)
    finally:
        dt = time.perf_counter() - t0
        log_json("response", method=method, id=_id, duration_ms=round(dt * 1000, 3))

    return None
