import sys, json
from .protocol import handle_request, log_json

def run_stdio_loop() -> None:
    log_json("startup", msg="Servidor MCP stdio iniciado (invest)")
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log_json("error", where="transport_stdio", msg="JSON inválido", sample=line[:200])
            continue
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            log_json("error", where="transport_stdio", msg="Mensaje no JSON-RPC 2.0")
            continue
        should_quit = handle_request(msg)
        if should_quit:
            break
    log_json("shutdown", msg="Servidor MCP stdio detenido (invest)")
