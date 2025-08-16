import sys, json, traceback
from typing import Dict, Any, Optional
from .tools import TOOLS, TOOL_IMPL

PROTOCOL_VERSION = "2025-06-18"

# -------- Helpers JSON-RPC / logging ----------
def jprint(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def log(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
    sys.stderr.flush()

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
    method = req.get("method")
    _id = req.get("id")
    is_notification = _id is None

    try:
        if method == "initialize":
            jprint(rsp_result(_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": True},
                    "logging": {}
                },
                "serverInfo": {"name": "uvg-mcp-local", "title": "UVG MCP Local Server", "version": "0.3.0"},
                "instructions": "Servidor MCP de ejemplo (sum, grep_lines, sha256)."
            }))
            return None

        if method == "notifications/initialized":
            log("[MCP] Cliente indicó initialized.")
            return None

        if method in ("ping", "notifications/ping"):
            if not is_notification:
                jprint(rsp_result(_id, {"ok": True}))
            return None

        if method == "shutdown":
            if not is_notification:
                jprint(rsp_result(_id, {"ok": True}))
            log("[MCP] Recibido shutdown. Cerrando servidor.")
            return True

        if method == "tools/list":
            jprint(rsp_result(_id, {"tools": TOOLS, "nextCursor": None}))
            return None

        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str):
                jprint(rsp_error(_id, -32602, "Invalid 'name' for tools/call"))
                return None
            impl = TOOL_IMPL.get(name)
            if impl is None:
                jprint(rsp_error(_id, -32601, f"Unknown tool: {name}"))
                return None
            result = impl(arguments)
            jprint(rsp_result(_id, result))
            return None

        # Método desconocido
        if not is_notification:
            jprint(rsp_error(_id, -32601, f"Method not found: {method}"))
        else:
            log(f"[MCP] Notificación desconocida: {method}")

    except ValueError as ve:
        if _id is not None:
            jprint(rsp_error(_id, -32602, "Invalid params", {"detail": str(ve)}))
    except Exception:
        log("[MCP] Exception:\n" + traceback.format_exc())
        if _id is not None:
            jprint(rsp_error(_id, -32000, "Internal server error"))
    return None
