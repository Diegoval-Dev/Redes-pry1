import json
from typing import List, Dict, Any
from rich.console import Console
from rich.panel import Panel
from .llm import LLM
from .mcp_runtime import MCPFleet
from .config import CHAT_LOG_FILE

console = Console()

def log_chat(role: str, content: str):
    with open(CHAT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"role":role,"content":content}, ensure_ascii=False) + "\n")

def parse_tool_line(line: str):
    if not line.startswith(("!fs","!gh","!local","!inv")): return None
    try:
        prefix, rest = line.split(" ",1)
        return prefix[1:], json.loads(rest)  
    except Exception:
        return None

def pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

def main():
    llm = LLM()
    fleet = MCPFleet()
    fleet.start_all()

    history: List[Dict[str,str]] = []
    console.print(Panel.fit(
        "Chat MCP listo.\n"
        "Comandos:\n"
        "  !fs {\"tool\":\"list_directory\",\"args\":{\"path\":\"D:/...\",\"recursive\":false}}\n"
        "  !gh {\"tool\":\"list_commits\",\"args\":{\"owner\":\"...\",\"repo\":\"...\",\"sha\":\"main\"}}\n"
        "  !local {\"tool\":\"json_validate\", ...}\n"
        "  !inv {\"tool\":\"price_quote\",\"args\":{\"symbols\":[\"BTC\",\"ETH\",\"SPY\",\"GLD\"],\"useLive\":true}}\n",  # 👈 ayuda
        title="MCP Chat")
    )

    try:
        while True:
            user = console.input("[bold cyan]tú> [/]")
            if user.strip().lower() in ("exit","quit"): break

            # Ejecutar comando directo
            cmd = parse_tool_line(user.strip())
            if cmd:
                kind, payload = cmd
                tool = payload.get("tool"); args = payload.get("args",{})
                try:
                    if kind=="fs":   res = fleet.fs.tools_call(tool, args)
                    elif kind=="gh": res = fleet.gh.tools_call(tool, args)
                    elif kind=="inv":res = fleet.invest.tools_call(tool, args)
                    else:            res = fleet.local.tools_call(tool, args)
                    console.print(Panel.fit(pretty(res), title=f"{kind}:{tool} ✓"))
                    log_chat("tool", f"{kind}:{tool} -> {pretty(res)}")
                except Exception as e:
                    console.print(Panel.fit(str(e), title=f"{kind}:{tool} ✗"))
                    log_chat("tool_error", f"{kind}:{tool} -> {e}")
                continue

            # Conversación con LLM
            history.append({"role":"user","content":user}); log_chat("user",user)
            answer = llm.chat(history, user)
            log_chat("assistant", answer)
            console.print(Panel(answer, title="asistente"))

            # Auto-ejecutar cualquier línea de comando sugerida por el LLM
            executed = False
            for line in answer.splitlines():
                cmd = parse_tool_line(line.strip())
                if not cmd: continue
                kind, payload = cmd
                tool = payload.get("tool"); args = payload.get("args",{})
                try:
                    if kind=="fs":   res = fleet.fs.tools_call(tool, args)
                    elif kind=="gh": res = fleet.gh.tools_call(tool, args)
                    elif kind=="inv":res = fleet.invest.tools_call(tool, args)
                    else:            res = fleet.local.tools_call(tool, args)
                    executed = True
                    console.print(Panel.fit(pretty(res), title=f"{kind}:{tool} ✓"))
                    log_chat("tool", f"{kind}:{tool} -> {pretty(res)}")
                    history.append({"role":"user","content":f"[{kind}:{tool} RESULT]\n{pretty(res)}"})
                except Exception as e:
                    console.print(Panel.fit(str(e), title=f"{kind}:{tool} ✗"))
                    log_chat("tool_error", f"{kind}:{tool} -> {e}")

            if executed:
                synth = llm.chat(history, "Resume y continúa.")
                log_chat("assistant", synth)
                console.print(Panel(synth, title="asistente (síntesis)"))
                history.append({"role":"assistant","content":synth})
    finally:
        fleet.stop_all()

if __name__ == "__main__":
    main()
