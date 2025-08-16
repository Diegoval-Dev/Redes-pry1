import sys, json
from .protocol import handle_request, log

def run_stdio_loop() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log(f"[MCP] JSON inválido: {line[:200]}")
            continue
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            log("[MCP] Mensaje no JSON-RPC 2.0")
            continue
        should_quit = handle_request(msg)
        if should_quit:
            break
