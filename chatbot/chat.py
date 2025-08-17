import json, os, sys
from typing import List, Dict, Any
from rich.console import Console
from rich.panel import Panel
from .llm import LLM
from .mcp_runtime import MCPFleet
from .config import CHAT_LOG_FILE

console = Console()

def log_chat(role: str, content: str):
    rec = {"role": role, "content": content}
    with open(CHAT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def parse_tool_line(line: str):
    # Formato: !fs {...} o !gh {...}
    if not line.startswith(("!fs", "!gh")):
        return None
    try:
        prefix, rest = line.split(" ", 1)
        payload = json.loads(rest)
        return prefix[1:], payload
    except Exception:
        return None

def pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

def main():
    llm = LLM()
    fleet = MCPFleet()
    fleet.start_all()

    history: List[Dict[str,str]] = []
    console.print(Panel.fit("Chat Host MCP listo. Usa !fs / !gh para llamar tools.\nEj: !fs {\"tool\":\"list_directory\",\"args\":{\"path\":\"D:/...\",\"recursive\":false}}", title="MCP Chat"))

    try:
        while True:
            user = console.input("[bold cyan]tú> [/]")
            if user.strip().lower() in ("exit","quit"):
                break

            maybe = parse_tool_line(user.strip())
            if maybe:
                kind, payload = maybe
                tool = payload.get("tool")
                args = payload.get("args", {})
                try:
                    if kind == "fs":
                        res = fleet.fs.tools_call(tool, args)
                    else:
                        res = fleet.gh.tools_call(tool, args)
                    console.print(Panel.fit(pretty(res), title=f"{kind}:{tool} ✓"))
                    log_chat("tool", f"{kind}:{tool} -> {pretty(res)}")
                except Exception as e:
                    console.print(Panel.fit(str(e), title=f"{kind}:{tool} ✗"))
                    log_chat("tool_error", f"{kind}:{tool} -> {e}")
                continue

            history.append({"role":"user","content":user})
            log_chat("user", user)
            answer = llm.chat(history, user)
            log_chat("assistant", answer)
            console.print(Panel(answer, title="asistente"))

            executed_any = False
            for line in answer.splitlines():
                cmd = parse_tool_line(line.strip())
                if not cmd:
                    continue
                kind, payload = cmd
                tool = payload.get("tool")
                args = payload.get("args", {})
                try:
                    if kind == "fs":
                        res = fleet.fs.tools_call(tool, args)
                    else:
                        res = fleet.gh.tools_call(tool, args)
                    executed_any = True
                    console.print(Panel.fit(pretty(res), title=f"{kind}:{tool} ✓"))
                    log_chat("tool", f"{kind}:{tool} -> {pretty(res)}")
                    history.append({"role":"user","content":f"[{kind}:{tool} RESULT]\n{pretty(res)}"})
                except Exception as e:
                    console.print(Panel.fit(str(e), title=f"{kind}:{tool} ✗"))
                    log_chat("tool_error", f"{kind}:{tool} -> {e}")

            if executed_any:
                synthesis = llm.chat(history, "Resume y continúa.")
                log_chat("assistant", synthesis)
                console.print(Panel(synthesis, title="asistente (síntesis)"))
                history.append({"role":"assistant","content":synthesis})

    finally:
        fleet.stop_all()

if __name__ == "__main__":
    main()
