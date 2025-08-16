import sys, json, traceback
from typing import Dict, Any, List, Optional

PROTOCOL_VERSION = "2025-06-18"

def jprint(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def log(msg: str) -> None:
    sys.stderr.write(msg.strip() + "\n")
    sys.stderr.flush()

def rsp_result(_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": _id, "result": result}

def rsp_error(_id: Any, code: int, message: str, data: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
    err = {"jsonrpc": "2.0", "id": _id, "error": {"code": code, "message": message}}
    if data is not None:
        err["error"]["data"] = data
    return err

TOOLS = [
    {
        "name": "sum",
        "title": "Sumatoria segura",
        "description": "Suma una lista de números.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "values": {"type": "array", "items": {"type": "number"}}
            },
            "required": ["values"]
        },
        "outputSchema": {
            "type": "object",
            "properties": {"sum": {"type": "number"}},
            "required": ["sum"]
        }
    }
]

def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "sum":
        vals = args.get("values", [])
        total = float(sum(vals))
        return {
            "content": [{"type": "text", "text": json.dumps({"sum": total})}],
            "structuredContent": {"sum": total},
            "isError": False
        }
    raise KeyError(f"Unknown tool: {name}")

def handle_request(req: Dict[str, Any]) -> None:
    method = req.get("method")
    _id = req.get("id")
    is_notification = _id is None

    try:
        if method == "initialize":
            jprint(rsp_result(_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "uvg-mcp-local", "title": "UVG MCP Local Server", "version": "0.1.0"}
            }))
            return

        if method == "notifications/initialized":
            log("[MCP] Cliente indicó initialized.")
            return

        if method == "tools/list":
            jprint(rsp_result(_id, {"tools": TOOLS, "nextCursor": None}))
            return

        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            result = call_tool(name, arguments)
            jprint(rsp_result(_id, result))
            return

        if not is_notification:
            jprint(rsp_error(_id, -32601, f"Method not found: {method}"))

    except Exception as e:
        log("[MCP] Exception:\n" + traceback.format_exc())
        if _id is not None:
            jprint(rsp_error(_id, -32000, "Internal server error", {"detail": str(e)}))

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log(f"[MCP] JSON inválido: {line[:200]}")
            continue
        handle_request(msg)

if __name__ == "__main__":
    main()
