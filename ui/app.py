# ui/app.py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json, re
import streamlit as st
from typing import Any, Dict, List, Optional
from datetime import datetime
from chatbot.llm import LLM
from chatbot.mcp_runtime import MCPFleet, handle_command_line
from chatbot.config import FS_ROOT, GITHUB_PERSONAL_ACCESS_TOKEN, WFM_JWT

st.set_page_config(page_title="MCP Chat UI", page_icon="🤖", layout="wide")

# ------------------------- helpers -------------------------
TOOLS_ROUTING_GUIDE = """\
INSTRUCCIONES DE HERRAMIENTAS (IMPORTANTE):
1) Si alguna herramienta aplica claramente a la petición, emite EXACTAMENTE una línea con:
   !mcp {"tool":"<NOMBRE>", "server":"<SERVIDOR>", "args":{...}}
   - Nada más en esa línea. No añadas texto adicional.
2) Si ninguna herramienta aplica, responde normalmente en texto.
3) No preguntes al usuario qué herramienta usar; decide tú.
"""

def build_tool_router_prompt(tools_map: Dict[str, List[str]]) -> str:
    """
    Instrucciones para el LLM: no pidas al usuario qué servidor usar; elígelo tú.
    Cuando una herramienta sea útil, EMITE un !mcp ejecutable.
    """
    lines = []
    lines.append(
        "ERES UN ASISTENTE QUE USA HERRAMIENTAS (MCP). "
        "NUNCA preguntes en qué servidor ejecutar; decide tú. "
        "Cuando una herramienta sea útil, EMITE una línea que empiece EXACTAMENTE con:\n"
        "!mcp {\"tool\":\"<tool>\", \"args\":{...}, \"server\":\"<fs|gh|invest|wfm|local>\"}\n"
        "Después del/los !mcp puedes añadir una explicación breve si sirve, "
        "pero el comando debe ser ejecutable tal cual."
    )
    lines.append("\nREGLAS DE RUTEO (elige servidor según intención):")
    lines.append("- wfm: búsquedas/órdenes/snapshots/rivens en Warframe.Market.")
    lines.append("- gh: cambios en repos (crear/actualizar archivo, ramas, PRs, commits, listar).")
    lines.append("- fs: leer/escribir/crear/mover archivos y listar directorios bajo FS_ROOT.")
    lines.append("- invest: cotizaciones/metrics/portafolios.")
    lines.append("- local: servidor HTTP MCP si existe (solo si aplica).")
    lines.append("- fitness: métricas (BMI/BMR), recomendaciones de ejercicios, construir rutina semanal, recomendaciones por métricas.")
    lines.append("Si varias encajan, elige la más obvia. No pidas aclaraciones.")

    lines.append("\nINVENTARIO DE HERRAMIENTAS DISPONIBLES (por servidor):")
    for srv, tools in (tools_map or {}).items():
        lines.append(f"- {srv}: {', '.join(tools) if tools else '(sin tools)'}")

    lines.append("\nEJEMPLOS:")
    lines.append('Usuario: "Búscame el item galatine prime blade y dime su url_name."')
    lines.append('Asistente: !mcp {"tool":"wfm_search_items","server":"wfm","args":{"query":"galatine prime blade"}}')

    lines.append('Usuario: "Lista items que tengan la palabra ‘riven’ en el nombre."')
    lines.append('Asistente: !mcp {"tool":"wfm_search_items","server":"wfm","args":{"query":"riven"}}')

    lines.append('Usuario: "Crea un archivo notas.txt que diga Hola y súbelo a Git en rama notas."')
    lines.append('Asistente: !mcp {"tool":"create_or_update_file","server":"gh","args":{"owner":"<owner>","repo":"<repo>","path":"notas.txt","content":"Hola","message":"Agregar notas.txt","branch":"notas"}}')

    lines.append('Usuario: "Calcula mi BMI y BMR: hombre, 29 años, 175 cm, 85 kg."')
    lines.append('Asistente: !mcp {"tool":"compute_metrics","server":"fitness","args":{"sexo":"male","edad":29,"altura_cm":175,"peso_kg":85}}')

    lines.append('Usuario: "Recomiéndame 8 ejercicios de calistenia para hipertrofia."')
    lines.append('Asistente: !mcp {"tool":"recommend_exercises","server":"fitness","args":{"objetivo":"hipertrofia","deporte":"calistenia","limite":8}}')

    lines.append('Usuario: "Arma una rutina de 4 días para voleibol, 60 minutos por sesión."')
    lines.append('Asistente: !mcp {"tool":"build_routine_tool","server":"fitness","args":{"objetivo":"volleyball","dias_por_semana":4,"minutos_por_sesion":60,"experiencia":"intermedio"}}')

    lines.append('Usuario: "Mido 1.70 y peso 90 kg; quiero perder grasa. Dame 6 ejercicios."')
    lines.append('Asistente: !mcp {"tool":"recommend_by_metrics_tool","server":"fitness","args":{"sexo":"male","altura_cm":170,"peso_kg":90,"objetivo":"fat loss","limite":6}}')

    return "\n".join(lines)


def call_llm_with_router(history: List[Dict[str, str]], user_text: str, fleet) -> str:
    # Asegura MCP levantado para listar tools
    tools_map = fleet.list_all_tools()
    router_prompt = build_tool_router_prompt(tools_map)

    # Inyecta el router_prompt como “system” al historial para esta llamada
    combined_history = [{"role": "system", "content": router_prompt}] + history
    return st.session_state.llm.chat(combined_history, user_text)


def _schema_to_example_args(schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        props = (schema or {}).get("properties") or {}
        example = {}
        for k, v in props.items():
            t = (v.get("type") if isinstance(v, dict) else None) or "string"
            if t == "string":
                example[k] = "<texto>"
            elif t == "number":
                example[k] = 123
            elif t == "integer":
                example[k] = 1
            elif t == "boolean":
                example[k] = True
            elif t == "array":
                example[k] = []
            elif t == "object":
                example[k] = {}
            else:
                example[k] = None
        return example if example else None
    except Exception:
        return None

def build_tools_catalog_text(fleet) -> str:
    """
    Renderiza un catálogo compacto de tools reales + una pseudo-tool local de validación JSON.
    """
    detailed = fleet.list_all_tools_detailed()
    lines = []
    for server, tools in detailed.items():
        if not tools:
            continue
        lines.append(f"- Servidor: {server}")
        for t in tools:
            name = t.get("name")
            desc = (t.get("description") or "").strip()
            schema = t.get("inputSchema") or {}
            ex = _schema_to_example_args(schema) or {}
            # línea compacta + ejemplo args
            if desc:
                lines.append(f"  • tool={name} — {desc}")
            else:
                lines.append(f"  • tool={name}")
            if ex:
                lines.append(f"    args_ejemplo={json.dumps(ex, ensure_ascii=False)}")

    # Pseudo-tool local: json_validate
    lines.append("- Servidor: local")
    lines.append("  • tool=json_validate — Valida si un texto es JSON válido; devuelve {valid: bool, parsed|error}.")
    lines.append('    args_ejemplo={"value":"{ \\"hola\\": \\"mundo\\" }"}')

    return "\n".join(lines)

def pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)

def _try_load_json(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None

def parse_legacy_tool_line(line: str):
    """
    Acepta comandos estilo:
      !fs {"tool":"list_directory","args":{...}}
      !gh {"tool":"list_commits","args":{...}}
      !local {"tool":"json_validate","args":{...}}
      !invest {"tool":"price_quote","args":{...}}
      !wfm {"tool":"wfm_price_snapshot","args":{...}}
    """
    if not line.startswith(("!fs","!gh","!local","!invest","!inv","!wfm")):
        return None
    try:
        prefix, rest = line.split(" ", 1)
    except ValueError:
        return None
    kind = prefix[1:]
    if kind == "inv":
        kind = "invest"
    try:
        payload = json.loads(rest)
    except Exception:
        return None
    return kind, payload

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

def _render_commits_list(data: Any):
    if not isinstance(data, list):
        st.json(data)
        return
    st.write("### Últimos commits")
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
        st.markdown(f"**{sha}** — {msg}")
        st.caption(f"👤 {author} · 🕒 {date_str} · [{'ver'}]({url})" if url else f"👤 {author} · 🕒 {date_str}")

def _render_files_listing(text_blob: str):
    lines = [ln.strip() for ln in text_blob.splitlines() if ln.strip()]
    if not lines:
        st.info("No hay elementos.")
        return
    st.write("### Contenido del directorio")
    for ln in lines:
        # Formato esperado: "[FILE] foo.txt" / "[DIR] carpeta"
        if ln.startswith("[FILE]"):
            icon = "📄"; name = ln[6:].strip()
        elif ln.startswith("[DIR]"):
            icon = "📁"; name = ln[5:].strip()
        else:
            icon = "❔"; name = ln
        st.markdown(f"{icon} **{name}**")

def render_mcp_result(tool_key: str, result: Dict[str, Any]):
    norm = _norm_result(result)

    # Renderizados específicos útiles
    if tool_key == "github:list_commits":
        _render_commits_list(norm["data"])
        return

    if tool_key == "filesystem:list_directory":
        if norm["kind"] == "plain" and isinstance(norm["data"], str):
            _render_files_listing(norm["data"])
        else:
            st.json(norm["data"])
        return

    if tool_key == "invest:price_quote":
        data = norm["data"] or {}
        quotes = data.get("quotes", [])
        st.write("### Cotizaciones")
        if not quotes:
            st.json(data); return
        for q in quotes:
            st.markdown(f"**{q.get('symbol','?')}** — {q.get('name','')}")
            st.caption(f"{q.get('currency','USD')} · fuente: {q.get('source','?')}")
            last = q.get("last")
            ret1d, ret7d, ret30d = q.get("ret1d"), q.get("ret7d"), q.get("ret30d")
            if isinstance(ret1d,(int,float)) and isinstance(ret7d,(int,float)) and isinstance(ret30d,(int,float)):
                st.markdown(f"- **Último:** {last}\n- **Ret 1d:** {ret1d:.4f} · **Ret 7d:** {ret7d:.4f} · **Ret 30d:** {ret30d:.4f}")
            else:
                st.markdown(f"- **Último:** {last}")
        return

    if tool_key == "wfm:wfm_price_snapshot":
        data = norm["data"] or {}
        st.write("### Warframe.Market — Price snapshot")
        st.markdown(f"**Item:** `{data.get('url_name','?')}` · **Platform:** `{data.get('platform','pc')}`")
        st.json(data)
        return

    # Fallbacks
    if norm["kind"] in ("structured", "json-text"):
        st.json(norm["data"])
    else:
        st.code(str(norm["data"]), language="text")

def ensure_fleet_started():
    if not st.session_state.get("fleet_started"):
        with st.spinner("Arrancando servidores MCP..."):
            try:
                st.session_state.fleet.start_all()
            except Exception as e:
                st.warning(f"Algunos servidores no arrancaron: {e}")
        st.session_state.fleet_started = True

def exec_legacy_tool(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    tool = payload.get("tool"); args = payload.get("args", {}) or {}
    fleet = st.session_state.fleet
    if kind == "fs" and fleet.fs:      return fleet.fs.tools_call(tool, args)
    if kind == "gh" and fleet.gh:      return fleet.gh.tools_call(tool, args)
    if kind == "local" and fleet.local:   return fleet.local.tools_call(tool, args)
    if kind == "invest" and fleet.invest: return fleet.invest.tools_call(tool, args)
    if kind == "wfm" and fleet.wfm:     return fleet.wfm.tools_call(tool, args)
    raise ValueError(f"Servidor '{kind}' no está habilitado o iniciado.")

def maybe_execute_command_lines(answer: str):
    """
    Busca líneas de comandos en la respuesta del asistente y las ejecuta.
    Soporta:
      - ¡Legacy!: !fs / !gh / !invest / !wfm / !local
      - ¡Nuevo!:  !mcp { "tool": "...", "args": {...}, "server": "opcional" }

    Además intercepta:
      - list_tools  -> listado local (fleet.list_all_tools)
      - json_validate/validate_json/check_json -> validación local si aplica
    """
    executed = False
    for raw in answer.splitlines():
        line = raw.strip()
        if not line or not line.startswith("!"):
            continue

        # 1) Formatos legacy (sin cambios)
        legacy = parse_legacy_tool_line(line)
        if legacy:
            ensure_fleet_started()
            kind, payload = legacy
            tool = payload.get("tool", "")
            try:
                res = exec_legacy_tool(kind, payload)
                st.session_state.messages.append({
                    "role": "assistant",
                    "kind": "tool",
                    "tool_key": f"{kind}:{tool}",
                    "tool_header": f"{kind}:{tool} ✓",
                    "result": res,
                })
                executed = True
            except Exception as e:
                st.session_state.messages.append({"role":"assistant", "content": f"{kind}:{tool} ✗\n\n```\n{e}\n```"})
            continue

        # 2) Formato dinámico !mcp {...} con intercepts
        if line.lower().startswith("!mcp "):
            ensure_fleet_started()
            try:
                payload = json.loads(line[4:].strip())
            except Exception as e:
                st.session_state.messages.append({
                    "role":"assistant",
                    "content": f"!mcp ✗\n\n```\nJSON inválido en el comando: {e}\n```"
                })
                continue

            tool = (payload.get("tool") or "").lower()
            args = payload.get("args") or {}

            # --- intercept: list_tools -> local ---
            if tool in ("list_tools", "__list_tools__"):
                tools_map = st.session_state.fleet.list_all_tools()
                st.session_state.messages.append({
                    "role": "assistant",
                    "kind": "tool",
                    "tool_key": "mcp:__list_tools__",
                    "tool_header": "🔧 Herramientas disponibles",
                    "result": {"structuredContent": tools_map},
                })
                executed = True
                continue

            # --- intercept: json_validate -> local (fallback simple) ---
            if tool in ("json_validate", "validate_json", "check_json"):
                raw_json = (args.get("value") or args.get("text") or args.get("json") or "").strip()
                out = {}
                try:
                    parsed = json.loads(raw_json)
                    out = {"valid": True, "parsed": parsed}
                except Exception as e:
                    out = {"valid": False, "error": str(e), "input": raw_json}
                st.session_state.messages.append({
                    "role": "assistant",
                    "kind": "tool",
                    "tool_key": "local:json_validate",
                    "tool_header": "🧪 Validación de JSON",
                    "result": {"structuredContent": out},
                })
                executed = True
                continue

            # --- default: enviamos a los servers ---
            try:
                res = handle_command_line(line, st.session_state.fleet)
                server = payload.get("server")
                tool_key = f"{server}:{payload.get('tool','?')}" if server else f"mcp:{payload.get('tool','?')}"
                st.session_state.messages.append({
                    "role": "assistant",
                    "kind": "tool",
                    "tool_key": tool_key,
                    "tool_header": f"{tool_key} ✓",
                    "result": res,
                })
                executed = True
            except Exception as e:
                st.session_state.messages.append({"role":"assistant", "content": f"!mcp ✗\n\n```\n{e}\n```"})
            continue

    return executed

# ------------------------- state -------------------------
if "enabled_servers" not in st.session_state:
    # Por defecto: fs, gh, invest (wfm y local apagados)
    st.session_state.enabled_servers = {"fs", "gh", "invest"}
    
if "pending_text" not in st.session_state:
    st.session_state.pending_text = None

if "fleet" not in st.session_state:
    st.session_state.fleet = MCPFleet(enabled=st.session_state.enabled_servers)


if "fleet_started" not in st.session_state:
    st.session_state.fleet_started = False

if "llm" not in st.session_state:
    st.session_state.llm = LLM()

if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []

if "history" not in st.session_state:
    st.session_state.history: List[Dict[str, str]] = []

# ------------------------- sidebar -------------------------

with st.sidebar:
    st.markdown("## ⚙️ Configuración")
    st.markdown(f"- **FS_ROOT**: `{FS_ROOT}`")
    st.markdown(f"- **GitHub Token**: {'✅' if GITHUB_PERSONAL_ACCESS_TOKEN else '❌'}")
    st.markdown(f"- **WFM_JWT**: {'✅' if WFM_JWT else '❌'}")

    st.markdown("### Servidores MCP")
    col1, col2, col3 = st.columns(3)
    with col1:
        cb_fs = st.checkbox("fs", value=("fs" in st.session_state.enabled_servers))
        cb_gh = st.checkbox("gh", value=("gh" in st.session_state.enabled_servers))
    with col2:
        cb_invest = st.checkbox("invest", value=("invest" in st.session_state.enabled_servers))
        cb_wfm = st.checkbox("wfm", value=("wfm" in st.session_state.enabled_servers))
    with col3:
        cb_local = st.checkbox("local", value=("local" in st.session_state.enabled_servers))
        cb_fitness = st.checkbox("fitness", value=("fitness" in st.session_state.enabled_servers))

    selected = {k for k, v in [
        ("fs", cb_fs), ("gh", cb_gh), ("invest", cb_invest),
        ("wfm", cb_wfm), ("local", cb_local), ("fitness", cb_fitness)
    ] if v}

    colA, colB = st.columns(2)
    with colA:
        if st.button("▶️ Iniciar seleccionados"):
            try:
                st.session_state.enabled_servers = selected
                st.session_state.fleet.stop_all()
            except Exception:
                pass
            st.session_state.fleet = MCPFleet(enabled=st.session_state.enabled_servers)
            try:
                with st.spinner("Arrancando..."):
                    st.session_state.fleet.start_all()
                st.session_state.fleet_started = True
                st.success(f"Iniciados: {', '.join(st.session_state.fleet.server_keys())}")
            except Exception as e:
                st.warning(f"Algunos servidores no arrancaron: {e}")

    with colB:
        if st.button("⏹️ Detener"):
            try:
                st.session_state.fleet.stop_all()
                st.session_state.fleet_started = False
                st.success("Servidores detenidos.")
            except Exception as e:
                st.error(f"Error al detener: {e}")

    st.divider()
    st.markdown("### 🔧 Herramientas disponibles")
    if st.button("Listar herramientas"):
        try:
            tools = st.session_state.fleet.list_all_tools()
            st.json(tools)
        except Exception as e:
            st.error(str(e))


# ------------------------- main -------------------------

st.title("🤖 MCP Chat")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("kind") == "tool":
            title = m.get("tool_header") or m.get("tool_key") or "resultado"
            st.markdown(f"**{title}**")
            # Llama tus renderers como antes (omitidos aquí)
            st.json(m["result"])
        else:
            st.markdown(m["content"])

user_msg = st.chat_input("Escribe tu mensaje…")

if user_msg:
    with st.chat_message("user"):
        st.markdown(user_msg)
    st.session_state.messages.append({"role": "user", "content": user_msg})
    st.session_state.history.append({"role": "user", "content": user_msg})
    st.session_state.pending_text = user_msg
    st.rerun()

if st.session_state.pending_text:
    text = st.session_state.pending_text

    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            answer = call_llm_with_router(st.session_state.history, text, st.session_state.fleet)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.history.append({"role": "assistant", "content": answer})

    for raw in answer.splitlines():
        line = raw.strip()
        if not line.startswith("!"):
            continue

        if line.lower().startswith("!mcp "):
            try:
                res = handle_command_line(line, st.session_state.fleet)
                payload = json.loads(line[4:].strip())
                tool = payload.get("tool","?")
                server = payload.get("server")
                tool_key = f"{server}:{tool}" if server else f"mcp:{tool}"
                st.session_state.messages.append({
                    "role": "assistant",
                    "kind": "tool",
                    "tool_key": tool_key,
                    "tool_header": f"{tool_key} ✓",
                    "result": res,
                })
            except Exception as e:
                st.session_state.messages.append({"role":"assistant", "content": f"!mcp ✗\n\n```\n{e}\n```"})

        # legacy: !fs / !gh / !invest / !wfm / !local (si aún los usas)
        # (Puedes dejar tu lógica legacy aquí si la necesitas)

    st.session_state.pending_text = None
    st.rerun()