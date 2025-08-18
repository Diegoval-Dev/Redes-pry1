import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json, time, re, os
import streamlit as st
from typing import Dict, Any, List, Optional
from chatbot.llm import LLM
from chatbot.mcp_runtime import MCPFleet
from chatbot.config import FS_ROOT, GITHUB_PERSONAL_ACCESS_TOKEN
from typing import Any, Dict, List, Optional
from datetime import datetime


st.set_page_config(page_title="MCP Chat UI", page_icon="🤖", layout="wide")

# ---------- util ----------
def pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)

def parse_tool_line(line: str):
    if not line.startswith(("!fs","!gh","!local")): return None
    try:
        prefix, rest = line.split(" ",1)
        return prefix[1:], json.loads(rest)  # ("fs"/"gh"/"local"), {"tool":..,"args":..}
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
    """
    Normaliza tu estructura MCP:
    - Si hay structuredContent: úsalo.
    - Si content[0].text tiene JSON, úsalo.
    - Si no, devolvemos el texto plano.
    """
    if isinstance(result, dict) and "structuredContent" in result and result["structuredContent"] is not None:
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
    """
    data esperado: lista de commits (GitHub API). Si no es lista, lo muestra en crudo.
    """
    if not isinstance(data, list):
        st.json(data)
        return
    rows = []
    for c in data:
        sha = (c.get("sha") or "")[:7]
        msg = (c.get("commit", {}).get("message") or "").split("\n", 1)[0]
        author = c.get("commit", {}).get("author", {}).get("name") or c.get("author", {}).get("login") or "—"
        date_iso = c.get("commit", {}).get("author", {}).get("date") or ""
        # Formato bonito de fecha si se puede
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

    # Links clicables en Markdown
    def _linkify(u: str, label: str) -> str:
        return f"[{label}]({u})" if u else "—"

    # Mostrar como tabla con links
    st.write("### Últimos commits")
    # Construimos columnas manualmente para link clicable
    for r in rows:
        with st.container(border=True):
            st.markdown(f"**{r['SHA']}** — {r['Mensaje']}")
            st.caption(f"👤 {r['Autor']} · 🕒 {r['Fecha']} · {_linkify(r['Link'], 'ver')}")

def _render_files_listing(text_blob: str):
    """
    Espera el formato:
      [FILE] hola.txt
      [FILE] test.txt
    Lo transforma a tarjetas con ícono.
    """
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
    """
    tool_key ejemplos:
      'github:list_commits'
      'filesystem:list_directory'
      'local:json_validate'
    """
    norm = _norm_result(result)

    # Render específico por tool
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

    # json_validate → mostrar status primero
    if tool_key == "local:json_validate":
        data = norm["data"]
        if isinstance(data, dict) and "valid" in data:
            valid = data.get("valid", False)
            if valid:
                st.success("✅ JSON válido")
            else:
                st.error("❌ JSON inválido")
                errs = data.get("errors") or []
                if errs:
                    with st.expander("Ver errores"):
                        for e in errs:
                            st.markdown(f"- {e}")
        st.json(data)
        return

    # Fallbacks genéricos
    if norm["kind"] in ("structured", "json-text"):
        st.json(norm["data"])
    else:
        # plain text
        st.code(str(norm["data"]), language="text")

def exec_tool(fleet: MCPFleet, kind: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if kind == "fs":   return fleet.fs.tools_call(tool, args)
    if kind == "gh":   return fleet.gh.tools_call(tool, args)
    if kind == "local":return fleet.local.tools_call(tool, args)
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
    st.session_state.messages: List[Dict[str, Any]] = []  # [{'role', 'content'} + opcionales]

if "pending_text" not in st.session_state:
    st.session_state.pending_text = None

# ---------- sidebar ----------
with st.sidebar:
    st.markdown("## ⚙️ Config & Estado")
    st.markdown(f"- **FS_ROOT**: `{FS_ROOT}`")
    st.markdown(f"- **GitHub Token**: {'✅' if GITHUB_PERSONAL_ACCESS_TOKEN else '❌'}")
    if st.button("🔄 Reiniciar servidores MCP"):
        try:
            st.session_state.fleet.stop_all()
        except Exception:
            pass
        st.session_state.fleet = MCPFleet()
        st.session_state.fleet.start_all()
        st.success("Servidores reiniciados.")

    st.markdown("---")
    st.markdown("### Comandos rápidos")
    if st.button("Listar FS_ROOT"):
        cmd = '!fs {"tool":"list_directory","args":{"path":"%s","recursive":false}}' % FS_ROOT.replace("\\","/")
        st.session_state.messages.append({"role":"user","content":cmd})

    if st.button("Commits (main)"):
        owner = st.text_input("Owner", value="Diegoval-Dev", key="owner_sidebar")
        repo  = st.text_input("Repo", value="Redes-pry1", key="repo_sidebar")
        if owner and repo:
            cmd = f'!gh {{"tool":"list_commits","args":{{"owner":"{owner}","repo":"{repo}","sha":"main","per_page":3}}}}'
            st.session_state.messages.append({"role":"user","content":cmd})

# ---------- main UI ----------
st.title("🤖 MCP Chat")

# historial visible
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("kind") == "tool":
            title = m.get("tool_header") or m.get("tool_key") or "resultado"
            tool_key = m.get("tool_key", "")
            st.markdown(f"**{title}**")

            # Vista bonita específica por herramienta
            render_mcp_result(tool_key, m["result"])

            # JSON crudo: para commits mostramos la versión PODADA,
            # para el resto mostramos el result tal cual
            with st.expander("Ver JSON crudo" + (" (podado)" if tool_key == "github:list_commits" else "")):
                norm = _norm_result(m["result"])
                data = norm.get("data")
                if tool_key == "github:list_commits" and isinstance(data, list):
                    st.json(_prune_commits_for_ui(data))
                else:
                    st.json(m["result"])
        else:
            # Mensajes del asistente o del usuario
            st.markdown(m["content"])


# input del chat
user_msg = st.chat_input("Escribe tu mensaje o pega un comando !fs/!gh/!local …")

def queue_user_message(text: str):
    """Encola el texto para procesarlo en el siguiente ciclo y hace eco inmediato."""
    # 1) Eco inmediato en el historial visible
    st.session_state.messages.append({"role": "user", "content": text})
    st.session_state.history.append({"role": "user", "content": text})

    # 2) Guardar en 'pending_text' y relanzar el script
    st.session_state.pending_text = text
    st.rerun()


def process_pending_text():
    """Procesa lo que esté en pending_text: comando directo o conversación con el LLM."""
    text = st.session_state.pending_text
    if not text:
        return

    try:
        # ¿Es un comando !fs/!gh/!local?
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
            # Chat con LLM
            answer = st.session_state.llm.chat(st.session_state.history, text)
            st.session_state.messages.append({"role": "assistant", "content": answer})

            # Auto-ejecutar comandos sugeridos por el LLM
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

            # Si ejecutó algo, pedir síntesis
            if executed_any:
                synth = st.session_state.llm.chat(st.session_state.history, "Resume y continúa.")
                st.session_state.messages.append({"role": "assistant", "content": synth})
                st.session_state.history.append({"role": "assistant", "content": synth})

    finally:
        # Limpia el pending y vuelve a renderizar
        st.session_state.pending_text = None
        st.rerun()

if user_msg:
    queue_user_message(user_msg)

if st.session_state.pending_text:
    with st.spinner("Procesando..."):
        process_pending_text()
