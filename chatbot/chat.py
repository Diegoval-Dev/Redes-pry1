# chatbot/chat.py
import json
from typing import List, Dict, Any, Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from .llm import LLM
from .mcp_runtime import MCPFleet
from .config import CHAT_LOG_FILE

console = Console()

# ---------------- util/log ----------------
def log_chat(role: str, content: str):
    with open(CHAT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"role": role, "content": content}, ensure_ascii=False) + "\n")

def pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

def parse_tool_line(line: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Formatos aceptados:
      !fs {...}
      !gh {...}
      !local {...}
      !invest {...}
      !inv {...}  # alias de !invest

    Devuelve (kind, payload_dict) o None si no coincide.
    """
    if not line.startswith(("!fs", "!gh", "!local", "!invest", "!inv")):
        return None
    try:
        prefix, rest = line.split(" ", 1)
        kind = prefix[1:]
        if kind == "inv":
            kind = "invest"
        return kind, json.loads(rest)
    except Exception:
        return None

# -------- adaptador tolerante para json_validate --------
def _normalize_json_validate(kind: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza args para !local json_validate:

    - Si el LLM/usuario envía {"text":"<json en string>"}:
      intentamos json.loads y lo convertimos a {"data": {...}}.
    - Si falla el parseo, devolvemos un resultado "simulado" con
      {valid:false, errors:[...]} para no romper el flujo.
    - Si ya viene {"data":{...}}, no tocamos nada.
    """
    if kind != "local" or tool != "json_validate":
        return args

    # ya viene como data -> lo respetamos
    if "data" in args:
        return args

    # si viene text, intentamos parsear
    if "text" in args and isinstance(args["text"], str):
        try:
            parsed = json.loads(args["text"])
            return {**args, "data": parsed}
        except Exception as e:
            # resultado simulado (parse error) para no hacer RPC
            return {
                "_client_side_result": True,
                "_payload": {
                    "valid": False,
                    "errors": [f"JSON parse error: {e}"],
                    "raw": args["text"],
                }
            }
    return args

def _exec_with_adapter(fleet: MCPFleet, kind: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Punto único de invocación de herramientas con normalización previa.
    - Aplica _normalize_json_validate para !local/json_validate.
    - Si _normalize devuelve un resultado simulado, lo retorna sin llamar al servidor.
    - Falla amable si local-remote no está configurado.
    """
    args2 = _normalize_json_validate(kind, tool, args)

    # Si es resultado simulado (parse error de JSON), devolvemos payload como si fuera un tool result.
    if isinstance(args2, dict) and args2.get("_client_side_result"):
        payload = args2["_payload"]
        return {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "structuredContent": payload,
            "isError": False
        }

    # Despacho normal
    if kind == "fs":
        return fleet.fs.tools_call(tool, args2)
    if kind == "gh":
        return fleet.gh.tools_call(tool, args2)
    if kind == "local":
        if not getattr(fleet, "local", None):
            raise RuntimeError("Servidor MCP HTTP (local-remote) no configurado. Define REMOTE_MCP_URL en .env.")
        return fleet.local.tools_call(tool, args2)
    if kind == "invest":
        return fleet.invest.tools_call(tool, args2)

    raise ValueError(f"Tipo de servidor desconocido: {kind}")

# ---------------- main loop ----------------
def main():
    llm = LLM()
    fleet = MCPFleet()
    fleet.start_all()

    history: List[Dict[str, str]] = []

    console.print(Panel.fit(
        "Chat MCP listo.\n"
        "Comandos (ejemplos):\n"
        "  # Filesystem (camelCase)\n"
        "  !fs {\"tool\":\"listDirectory\",\"args\":{\"path\":\"D:/...\",\"recursive\":false}}\n"
        "  !fs {\"tool\":\"writeFile\",\"args\":{\"path\":\"D:/.../prueba.txt\",\"content\":\"hola\"}}\n"
        "\n"
        "  # GitHub (según herramientas disponibles en tu server)\n"
        "  !gh {\"tool\":\"listCommits\",\"args\":{\"owner\":\"...\",\"repo\":\"...\",\"sha\":\"main\"}}\n"
        "  !gh {\"tool\":\"createBranch\",\"args\":{\"owner\":\"...\",\"repo\":\"...\",\"from\":\"main\",\"name\":\"feat/prueba\"}}\n"
        "  !gh {\"tool\":\"createOrUpdateFile\",\"args\":{\"owner\":\"...\",\"repo\":\"...\",\"path\":\"prueba.txt\",\"content\":\"Hola\",\"branch\":\"feat/prueba\",\"message\":\"feat: add prueba.txt\"}}\n"
        "  !gh {\"tool\":\"createPullRequest\",\"args\":{\"owner\":\"...\",\"repo\":\"...\",\"title\":\"feat: add prueba.txt\",\"head\":\"feat/prueba\",\"base\":\"main\"}}\n"
        "\n"
        "  # MCP HTTP remoto simple (json_validate)\n"
        "  !local {\"tool\":\"json_validate\",\"args\":{\"data\":{\"hola\":\"Hola\"}}}\n"
        "  # o deja el JSON crudo y lo parseamos aquí:\n"
        "  !local {\"tool\":\"json_validate\",\"args\":{\"text\":\"{\\\"hola\\\":\\\"Hola\\\"}\"}}\n"
        "\n"
        "  # Inversiones\n"
        "  !invest {\"tool\":\"price_quote\",\"args\":{\"symbols\":[\"BTC\",\"ETH\",\"SPY\",\"GLD\"],\"useLive\":true}}\n"
        "  !invest {\"tool\":\"build_portfolio\",\"args\":{\"capital\":10000,\"riskLevel\":3,\"allowedSymbols\":[\"SPY\",\"QQQ\",\"GLD\",\"BTC\",\"ETH\"],\"useLive\":true}}\n",
        title="MCP Chat"
    ))

    try:
        while True:
            user = console.input("[bold cyan]tú> [/]")
            if user.strip().lower() in ("exit", "quit"):
                break

            # 1) Ejecutar comando directo (!fs/!gh/!local/!invest)
            cmd = parse_tool_line(user.strip())
            if cmd:
                kind, payload = cmd
                tool = payload.get("tool")
                args = payload.get("args", {})
                try:
                    res = _exec_with_adapter(fleet, kind, tool, args)
                    console.print(Panel.fit(pretty(res), title=f"{kind}:{tool} ✓"))
                    log_chat("tool", f"{kind}:{tool} -> {pretty(res)}")
                except Exception as e:
                    console.print(Panel.fit(str(e), title=f"{kind}:{tool} ✗"))
                    log_chat("tool_error", f"{kind}:{tool} -> {e}")
                continue

            # 2) Conversación con LLM
            history.append({"role": "user", "content": user})
            log_chat("user", user)

            answer = llm.chat(history, user)
            log_chat("assistant", answer)
            console.print(Panel(answer, title="asistente"))

            # 3) Auto-ejecutar comandos sugeridos por el LLM (si los hay)
            executed = False
            for line in answer.splitlines():
                cmd2 = parse_tool_line(line.strip())
                if not cmd2:
                    continue
                kind, payload = cmd2
                tool = payload.get("tool")
                args = payload.get("args", {})
                try:
                    res = _exec_with_adapter(fleet, kind, tool, args)
                    executed = True
                    console.print(Panel.fit(pretty(res), title=f"{kind}:{tool} ✓"))
                    log_chat("tool", f"{kind}:{tool} -> {pretty(res)}")
                    history.append({"role": "user", "content": f"[{kind}:{tool} RESULT]\n{pretty(res)}"})
                except Exception as e:
                    console.print(Panel.fit(str(e), title=f"{kind}:{tool} ✗"))
                    log_chat("tool_error", f"{kind}:{tool} -> {e}")

            # 4) Si se ejecutó algo, pedir una síntesis al modelo
            if executed:
                synth = llm.chat(history, "Resume y continúa.")
                log_chat("assistant", synth)
                console.print(Panel(synth, title="asistente (síntesis)"))
                history.append({"role": "assistant", "content": synth})
    finally:
        fleet.stop_all()

if __name__ == "__main__":
    main()
