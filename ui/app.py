# ui/app.py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json, re
import streamlit as st
from typing import Any, Dict, List, Optional
from datetime import datetime

from chatbot.llm import LLM
from chatbot.mcp_runtime import MCPFleet
from chatbot.config import FS_ROOT, GITHUB_PERSONAL_ACCESS_TOKEN, WFM_JWT

st.set_page_config(page_title="MCP Chat UI", page_icon="🤖", layout="wide")

def pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)

def parse_tool_line(line: str):
    if not line.startswith(("!fs","!gh","!local","!invest","!inv","!wfm", "!anki")):
        return None
    prefix, rest = line.split(" ", 1)
    kind = prefix[1:]
    if kind == "inv":
        kind = "invest"
    try:
        return kind, json.loads(rest)
    except Exception:
        return None

def _prune_commits_for_ui(commits):
    if not isinstance(commits, list):
        return commits
    slim = []
    for c in commits:
        s = {
            "sha": c.get("sha"),
            "message": (c.get("commit", {}).get("message") or "").split("\n",1)[0],
            "author": c.get("commit", {}).get("author", {}).get("name"),
            "date": c.get("commit", {}).get("author", {}).get("date"),
            "html_url": c.get("html_url"),
        }
        slim.append(s)
    return slim

def _try_load_json(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None

def _norm_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(result, dict) and result.get("structuredContent") is not None:
        return {"kind": "structured", "data": result["structuredContent"]}

    texts: List[str] = []
    for c in result.get("content", []):
        if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str):
            texts.append(c["text"])
    blob = "\n".join(texts).strip()

    as_json = _try_load_json(blob)
    if as_json is not None:
        return {"kind": "json-text", "data": as_json}

    return {"kind": "plain", "data": blob}

def _render_commits(data: Any):
    if not isinstance(data, list):
        st.json(data)
        return
    rows = []
    for c in data:
        sha = (c.get("sha") or "")[:7]
        msg = (c.get("commit", {}).get("message") or "").split("\n", 1)[0]
        author = c.get("commit", {}).get("author", {}).get("name") or c.get("author", {}).get("login") or "—"
        date_iso = c.get("commit", {}).get("author", {}).get("date") or ""
        try:
            dt = datetime.fromisoformat(date_iso.replace("Z","+00:00"))
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_str = date_iso
        url = c.get("html_url") or c.get("url") or ""
        rows.append({
            "SHA": sha,
            "Mensaje": msg,
            "Autor": author,
            "Fecha": date_str,
            "Link": url
        })

    def _linkify(u: str, label: str) -> str:
        return f"[{label}]({u})" if u else "—"

    st.write("### Últimos commits")
    for r in rows:
        with st.container(border=True):
            st.markdown(f"**{r['SHA']}** — {r['Mensaje']}")
            st.caption(f"👤 {r['Autor']} · 🕒 {r['Fecha']} · {_linkify(r['Link'], 'ver')}")

def _render_files_listing(text_blob: str):
    lines = [ln.strip() for ln in text_blob.splitlines() if ln.strip()]
    if not lines:
        st.info("No hay elementos.")
        return
    file_re = re.compile(r"^\[(?P<kind>[A-Z]+)\]\s+(?P<name>.+)$")
    items = []
    for ln in lines:
        m = file_re.match(ln)
        if not m:
            items.append(("OTHER", ln))
        else:
            items.append((m.group("kind"), m.group("name")))

    st.write("### Contenido del directorio")
    for kind, name in items:
        icon = "📄" if kind == "FILE" else ("📁" if kind == "DIR" else "❔")
        with st.container(border=True):
            st.markdown(f"{icon} **{name}**  \n`{kind}`")

def render_mcp_result(tool_key: str, result: Dict[str, Any]):
    norm = _norm_result(result)

    if tool_key == "invest:price_quote":
        data = norm["data"]
        quotes = (data or {}).get("quotes", [])
        if not quotes:
            st.json(data); return
        st.write("### Cotizaciones")
        for q in quotes:
            with st.container(border=True):
                st.markdown(f"**{q.get('symbol','?')}** — {q.get('name','')}")
                st.caption(f"{q.get('currency','USD')} · fuente: {q.get('source','?')}")
                if all(isinstance(q.get(k), (int,float)) for k in ["ret1d","ret7d","ret30d"]):
                    st.markdown(
                        f"- **Último:** {q.get('last')}\n"
                        f"- **Ret 1d:** {q.get('ret1d'):.4f}  ·  **Ret 7d:** {q.get('ret7d'):.4f}  ·  **Ret 30d:** {q.get('ret30d'):.4f}"
                    )
                else:
                    st.markdown(f"- **Último:** {q.get('last')}")
        return

    if tool_key == "invest:risk_metrics":
        data = norm["data"]
        metrics = (data or {}).get("metrics", [])
        if not metrics:
            st.json(data); return
        st.write("### Métricas de riesgo (anualizadas)")
        for r in metrics:
            with st.container(border=True):
                st.markdown(f"**{r.get('symbol','?')}**")
                if all(isinstance(r.get(k), (int,float)) for k in ["meanAnnual","volAnnual","sharpe"]):
                    st.markdown(
                        f"- **Media:** {r.get('meanAnnual'):.4f}  ·  "
                        f"**Vol:** {r.get('volAnnual'):.4f}  ·  "
                        f"**Sharpe:** {r.get('sharpe'):.3f}"
                    )
                else:
                    st.json(r)
        return

    if tool_key == "invest:build_portfolio":
        data = norm["data"] or {}
        st.write("### Portafolio sugerido")
        tw = data.get("targetWeights", [])
        al = data.get("allocations", [])
        if tw:
            st.markdown("**Pesos objetivo**")
            for w in tw:
                st.markdown(f"- {w.get('symbol')}: {w.get('weight'):.4f}")
        if al:
            st.markdown("**Asignaciones (USD)**")
            for a in al:
                st.markdown(f"- {a.get('symbol')}: {a.get('amount'):.2f}")
        extras = {k: data.get(k) for k in ["expectedAnnualReturn","volAnnual","sharpe"] if k in data}
        if extras:
            with st.container(border=True):
                if all(isinstance(extras.get(k),(int,float)) for k in extras):
                    st.markdown(
                        f"**Exp. Return:** {extras.get('expectedAnnualReturn'):.4f} · "
                        f"**Vol:** {extras.get('volAnnual'):.4f} · "
                        f"**Sharpe:** {extras.get('sharpe'):.3f}"
                    )
                else:
                    st.json(extras)
        with st.expander("Ver JSON crudo"):
            st.json(data)
        return

    if tool_key == "github:list_commits":
        data = norm["data"]
        _render_commits(data)
        return

    if tool_key == "filesystem:list_directory":
        if norm["kind"] == "plain" and isinstance(norm["data"], str):
            _render_files_listing(norm["data"])
        else:
            st.json(norm["data"])
        return

    # ---- Warframe Market: snapshot simple ----
    if tool_key == "wfm:wfm_price_snapshot":
        data = norm["data"] or {}
        st.write("### Warframe.Market — Price snapshot")
        st.markdown(f"**Item:** `{data.get('url_name','?')}` · **Platform:** `{data.get('platform','pc')}`")
        summary = data.get("summary") or {}
        with st.container(border=True):
            bs = summary.get("best_sell")
            bb = summary.get("best_buy")
            if bs:
                st.markdown(f"- **Best SELL:** {bs.get('platinum')}p · user: `{bs.get('user')}` · status: {bs.get('status')} · rep: {bs.get('reputation')}")
            if bb:
                st.markdown(f"- **Best BUY:** {bb.get('platinum')}p · user: `{bb.get('user')}` · status: {bb.get('status')} · rep: {bb.get('reputation')}")
            mids = summary.get("midpoints") or {}
            spread = summary.get("spread") or {}
            st.markdown(f"- **Mid SELL:** {mids.get('sell')}p · **Mid BUY:** {mids.get('buy')}p · **Spread%:** {spread.get('pct')}")
        with st.expander("Ver JSON crudo"):
            st.json(data)
        return

    # Fallback genérico
    if norm["kind"] in ("structured", "json-text"):
        st.json(norm["data"])
    else:
        st.code(str(norm["data"]), language="text")

def exec_tool(fleet: MCPFleet, kind: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if kind == "fs":      return fleet.fs.tools_call(tool, args)
    if kind == "gh":      return fleet.gh.tools_call(tool, args)
    if kind == "local":   return fleet.local.tools_call(tool, args) if fleet.local else {"note":"local-remote deshabilitado"}
    if kind == "invest":  return fleet.invest.tools_call(tool, args)
    if kind == "wfm":     return fleet.wfm.tools_call(tool, args)
    raise ValueError(f"Tipo de servidor desconocido: {kind}")

# ---------- state ----------
if "fleet" not in st.session_state:
    st.session_state.fleet = MCPFleet()
    st.session_state.fleet.start_all()

if "llm" not in st.session_state:
    st.session_state.llm = LLM()

if "history" not in st.session_state:
    st.session_state.history: List[Dict[str,str]] = []

if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []

if "pending_text" not in st.session_state:
    st.session_state.pending_text = None

# ---------- sidebar ----------
with st.sidebar:
    st.markdown("## ⚙️ Config & Estado")
    st.markdown(f"- **FS_ROOT**: `{FS_ROOT}`")
    st.markdown(f"- **GitHub Token**: {'✅' if GITHUB_PERSONAL_ACCESS_TOKEN else '❌'}")
    st.markdown(f"- **WFM_JWT**: {'✅' if WFM_JWT else '❌'}")
    if st.button("🔄 Reiniciar servidores MCP"):
        try:
            st.session_state.fleet.stop_all()
        except Exception:
            pass
        st.session_state.fleet = MCPFleet()
        st.session_state.fleet.start_all()
        st.success("Servidores reiniciados.")

# ---------- main ----------
st.title("🤖 MCP Chat")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("kind") == "tool":
            title = m.get("tool_header") or m.get("tool_key") or "resultado"
            tool_key = m.get("tool_key", "")
            st.markdown(f"**{title}**")
            render_mcp_result(tool_key, m["result"])
            with st.expander("Ver JSON crudo" + (" (podado)" if tool_key == "github:list_commits" else "")):
                norm = _norm_result(m["result"])
                data = norm.get("data")
                if tool_key == "github:list_commits" and isinstance(data, list):
                    st.json(_prune_commits_for_ui(data))
                else:
                    st.json(m["result"])
        else:
            st.markdown(m["content"])

user_msg = st.chat_input("Pide cosas en lenguaje natural (ej. 'snapshot de galatine prime blade en pc')")
def queue_user_message(text: str):
    st.session_state.messages.append({"role": "user", "content": text})
    st.session_state.history.append({"role": "user", "content": text})
    st.session_state.pending_text = text
    st.rerun()

def process_pending_text():
    text = st.session_state.pending_text
    if not text:
        return

    try:
        parsed = parse_tool_line(text.strip())
        if parsed:
            kind, payload = parsed
            tool = payload.get("tool")
            args = payload.get("args", {})
            try:
                res = exec_tool(st.session_state.fleet, kind, tool, args)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "(resultado de herramienta)",
                    "kind": "tool",
                    "tool_key": f"{kind}:{tool}",
                    "tool_header": f"{kind}:{tool} ✓",
                    "result": res,
                })
            except Exception as e:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"{kind}:{tool} ✗\n\n```\n{e}\n```"
                })
        else:
            answer = st.session_state.llm.chat(st.session_state.history, text)
            st.session_state.messages.append({"role": "assistant", "content": answer})

            executed_any = False
            for line in answer.splitlines():
                cmd = parse_tool_line(line.strip())
                if not cmd:
                    continue
                kind, payload = cmd
                tool = payload.get("tool")
                args = payload.get("args", {})
                try:
                    res = exec_tool(st.session_state.fleet, kind, tool, args)
                    executed_any = True
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "(resultado de herramienta)",
                        "kind": "tool",
                        "tool_key": f"{kind}:{tool}",
                        "tool_header": f"{kind}:{tool} ✓",
                        "result": res,
                    })
                    st.session_state.history.append({
                        "role": "user",
                        "content": f"[{kind}:{tool} RESULT]\n{pretty(res)}"
                    })
                except Exception as e:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"{kind}:{tool} ✗\n\n```\n{e}\n```"
                    })

            if executed_any:
                synth = st.session_state.llm.chat(st.session_state.history, "Resume y continúa.")
                st.session_state.messages.append({"role": "assistant", "content": synth})
                st.session_state.history.append({"role": "assistant", "content": synth})

    finally:
        st.session_state.pending_text = None
        st.rerun()

if user_msg:
    queue_user_message(user_msg)

if st.session_state.pending_text:
    with st.spinner("Procesando..."):
        process_pending_text()
