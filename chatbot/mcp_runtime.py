# chatbot/mcp_runtime.py
import os, json, time, subprocess, shutil, platform, io
from typing import Dict, Any, Optional, List
import requests

from .config import (
    LOG_DIR, FS_ROOT, REMOTE_MCP_URL, REMOTE_MCP_PATH,
    MCP_WARFRAME_COMMAND, MCP_WARFRAME_ARGS,
    WFM_JWT, WFM_BASE_URL, WFM_LANGUAGE, WFM_PLATFORM,
    FITNESS_SERVER_PATH
)

JSONRPC = "2.0"
PROTO = "2025-06-18"

# ---------------- utils ----------------

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _which(cmd: str) -> Optional[str]:
    p = shutil.which(cmd)
    if p:
        return p
    if platform.system().lower().startswith("win"):
        p = shutil.which(cmd + ".cmd")
        if p:
            return p
    return None

def _log_jsonl(path: str, obj: Dict[str, Any]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _read_all_safe(stream: Optional[io.TextIOBase]) -> str:
    try:
        if not stream:
            return ""
        return stream.read() or ""
    except Exception:
        return ""

def _find_local_wfm_entry() -> Optional[str]:
    """
    Busca el CLI del MCP de Warframe en modo local (desarrollo):
      - ./mwf-mcp/dist/cli.js
      - ./mwf-mcp/dist/index.js
      - ./node_modules/mcp-warframe-market/dist/cli.js (por si acaso)
    Devuelve la ruta absoluta si existe.
    """
    root = _project_root()
    candidates = [
        os.path.join(root, "mwf-mcp", "dist", "cli.js"),
        os.path.join(root, "mwf-mcp", "dist", "index.js"),
        os.path.join(root, "node_modules", "mcp-warframe-market", "dist", "cli.js"),
        os.path.join(root, "node_modules", "mcp-warframe-market", "dist", "index.js"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

# ---------------- MCP stdio (autodetección de framing) ----------------

class MCPServer:
    """
    Soporta ambos formatos por stdio:
      - LSP headers: 'Content-Length: N' + body JSON
      - NDJSON:      una línea JSON por mensaje
    """
    def __init__(self, name: str, launch: List[str], env: Optional[Dict[str,str]] = None):
        self.name = name
        self.launch = launch
        self.env = {**os.environ, **(env or {})}
        self.proc: Optional[subprocess.Popen] = None
        self.seq = 0
        self.log_file = os.path.join(LOG_DIR, f"mcp_{name}.jsonl")

    def start(self):
        if self.proc and self.proc.poll() is None:
            return

        exe = _which(self.launch[0])
        use_shell = False
        popen_cmd = None

        if exe:
            popen_cmd = [exe] + self.launch[1:]
        else:
            if platform.system().lower().startswith("win"):
                use_shell = True
                popen_cmd = " ".join(self.launch)
            else:
                raise FileNotFoundError(f"[{self.name}] Executable not found in PATH: {self.launch[0]}")

        self.proc = subprocess.Popen(
            popen_cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=self.env, shell=use_shell
        )

        time.sleep(0.05)
        if self.proc.poll() is not None:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] failed to start (exit={self.proc.returncode}). Stderr:\n{stderr_text}")

        self._initialize()

    # ----- I/O helpers -----

    def _send(self, obj: Dict[str, Any]):
        if not (self.proc and self.proc.stdin):
            raise RuntimeError(f"[{self.name}] process not running / stdin closed")
        line = json.dumps(obj, ensure_ascii=False)
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
            _log_jsonl(self.log_file, {"dir":"out","obj":obj})
        except OSError as e:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] write to stdin failed: {e}\nChild stderr:\n{stderr_text}") from e

    def _recv(self, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
        """
        Lee una respuesta. Si el server habla LSP, detecta 'Content-Length:' y
        luego consume 'N' caracteres de body. Si habla NDJSON, intenta json por línea.
        """
        if not (self.proc and self.proc.stdout):
            return None

        t0 = time.time()
        header_lines: List[str] = []
        content_length: Optional[int] = None
        saw_headers = False

        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if not line:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.01)
                continue

            s = line.rstrip("\r\n")
            if not s and not header_lines:
                continue

            # 1) JSON por línea
            if s and s[0] in "{[":
                try:
                    msg = json.loads(s)
                    _log_jsonl(self.log_file, {"dir":"in","obj":msg})
                    return msg
                except json.JSONDecodeError:
                    body = s
                    while time.time() - t0 < timeout:
                        more = self.proc.stdout.readline()
                        if not more:
                            if self.proc.poll() is not None:
                                break
                            time.sleep(0.01); continue
                        body += more
                        try:
                            msg = json.loads(body)
                            _log_jsonl(self.log_file, {"dir":"in","obj":msg})
                            return msg
                        except json.JSONDecodeError:
                            continue
                    _log_jsonl(self.log_file, {"dir":"in","garbage":body})
                    return None

            # 2) Headers LSP
            if s.lower().startswith("content-length:"):
                try:
                    content_length = int(s.split(":",1)[1].strip())
                except Exception:
                    content_length = None
                header_lines.append(s)
                saw_headers = True

                # consume headers hasta línea en blanco
                while time.time() - t0 < timeout:
                    h = self.proc.stdout.readline()
                    if not h:
                        if self.proc.poll() is not None:
                            break
                        time.sleep(0.01); continue
                    hs = h.rstrip("\r\n")
                    if hs == "":
                        break
                    header_lines.append(hs)

                if not content_length or content_length <= 0:
                    return None

                # leer body exacto
                body = ""
                while len(body) < content_length and (time.time() - t0) < timeout:
                    chunk = self.proc.stdout.read(content_length - len(body))
                    if not chunk:
                        time.sleep(0.005); continue
                    body += chunk

                if len(body) != content_length:
                    return None

                try:
                    msg = json.loads(body)
                    _log_jsonl(self.log_file, {"dir":"in","obj":msg})
                    return msg
                except json.JSONDecodeError:
                    _log_jsonl(self.log_file, {"dir":"in","garbage":body})
                    return None

            header_lines.append(s)
            if saw_headers and s == "":
                return None

        return None

    # ----- Protocolo -----

    def _initialize(self):
        self.seq += 1
        self._send({
            "jsonrpc": JSONRPC,
            "id": self.seq,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTO,
                "capabilities": {},
                "clientInfo": {"name": "ChatHost", "version": "0.1"}
            }
        })
        rsp = self._recv()
        if not rsp or "result" not in rsp:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] initialize failed. Child stderr:\n{stderr_text}")
        try:
            self._send({"jsonrpc": JSONRPC, "method": "notifications/initialized"})
        except RuntimeError:
            raise

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 12.0) -> Dict[str, Any]:
        self.seq += 1
        self._send({"jsonrpc": JSONRPC, "id": self.seq, "method": method, "params": (params or {})})
        rsp = self._recv(timeout=timeout)
        if not rsp:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] timeout waiting response for {method}. Child stderr:\n{stderr_text}")
        if "result" in rsp:
            return rsp["result"]
        if "error" in rsp:
            raise RuntimeError(f"[{self.name}] {json.dumps(rsp['error'], ensure_ascii=False)}")
        raise RuntimeError(f"[{self.name}] unexpected {rsp}")
    

    def tools_call(self, tool: str, args: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
        return self.request("tools/call", {"name": tool, "arguments": args}, timeout=timeout)

    def list_tools(self, timeout: float = 8.0) -> List[Dict[str, Any]]:
        self.seq += 1
        self._send({
            "jsonrpc": JSONRPC,
            "id": self.seq,
            "method": "tools/list",
            "params": {}
        })
        rsp = self._recv(timeout=timeout)
        if not rsp:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] timeout waiting response (tools/list). Child stderr:\n{stderr_text}")
        if "result" in rsp:
            res = rsp["result"]
            if isinstance(res, dict) and "tools" in res:
                return res["tools"] or []
            if isinstance(res, list):
                return res
            return []
        if "error" in rsp:
            raise RuntimeError(f"[{self.name}] {json.dumps(rsp['error'], ensure_ascii=False)}")
        return []

# ---------------- HTTP (opcional) ----------------

class MCPHttpServer:
    def __init__(self, name: str, base_url: str, rpc_path: str = "/rpc"):
        if not base_url:
            raise RuntimeError(f"[{name}] REMOTE_MCP_URL no configurado")
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.rpc_url = self.base_url + (rpc_path if rpc_path.startswith("/") else f"/{rpc_path}")
        self.seq = 0

    def _send(self, obj: dict) -> dict:
        resp = requests.post(self.rpc_url, headers={"Content-Type": "application/json"}, json=obj, timeout=12)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"[{self.name}] HTTP {resp.status_code} at {self.rpc_url}\nBody: {resp.text}") from e
        return resp.json()

    def start(self):
        self.seq += 1
        init_req = {
            "jsonrpc": "2.0",
            "id": self.seq,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTO,
                "capabilities": {},
                "clientInfo": {"name": "ChatHost", "version": "0.1"},
            },
        }
        _ = self._send(init_req)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def tools_call(self, tool: str, args: dict) -> dict:
        self.seq += 1
        req = {"jsonrpc": "2.0", "id": self.seq, "method": "tools/call", "params": {"name": tool, "arguments": args}}
        rsp = self._send(req)
        if "result" in rsp:
            return rsp["result"]
        if "error" in rsp:
            raise RuntimeError(f"{self.name}: {rsp['error']}")
        raise RuntimeError(f"{self.name}: unexpected {rsp}")

    def list_tools(self) -> List[Dict[str, Any]]:
        self.seq += 1
        req = {"jsonrpc": "2.0", "id": self.seq, "method": "tools/list", "params": {}}
        rsp = self._send(req)
        if "result" in rsp:
            res = rsp["result"]
            if isinstance(res, dict) and "tools" in res:
                return res["tools"] or []
            if isinstance(res, list):
                return res
        if "error" in rsp:
            raise RuntimeError(f"{self.name}: {rsp['error']}")
        return []

# ---------------- Fleet ----------------

class MCPFleet:
    def __init__(self, enabled: Optional[set] = None):
        """
        enabled: subconjunto de {'fs','gh','invest','local','wfm','fitness'}.
        Por defecto: {'fs','gh','invest'}.
        """
        all_keys = {"fs", "gh", "invest", "local", "wfm", "fitness"}
        if enabled is None:
            enabled = {"fs", "gh", "invest"}
        else:
            enabled = {k for k in enabled if k in all_keys}
        self.enabled = enabled

        self.fs = MCPServer("filesystem", ["npx","-y","@modelcontextprotocol/server-filesystem", FS_ROOT]) if "fs" in enabled else None
        self.gh = MCPServer("github", ["npx","-y","@modelcontextprotocol/server-github"]) if "gh" in enabled else None
        self.invest = MCPServer("invest", ["python","-m","invest_mcp.main"]) if "invest" in enabled else None
        self.local = MCPHttpServer("local-remote", REMOTE_MCP_URL, REMOTE_MCP_PATH) if ("local" in enabled and REMOTE_MCP_URL) else None
        self.fitness = None
        if "fitness" in enabled:
            if not FITNESS_SERVER_PATH or not os.path.exists(FITNESS_SERVER_PATH):
                raise RuntimeError(
                    f"fitness: no se encontró server.py en FITNESS_SERVER_PATH ({FITNESS_SERVER_PATH})"
                )
            self.fitness = MCPServer("fitness", ["python", FITNESS_SERVER_PATH, "stdio"])
        self.wfm = None
        if "wfm" in enabled:
            launch = None
            env = {}
            if MCP_WARFRAME_COMMAND:
                launch = [MCP_WARFRAME_COMMAND] + ([MCP_WARFRAME_ARGS] if MCP_WARFRAME_ARGS else [])
            else:
                entry = _find_local_wfm_entry()
                if entry:
                    launch = ["node", entry]
            if launch:
                if WFM_JWT: env["WFM_JWT"] = WFM_JWT
                if WFM_BASE_URL: env["WFM_BASE_URL"] = WFM_BASE_URL
                if WFM_LANGUAGE: env["WFM_LANGUAGE"] = WFM_LANGUAGE
                if WFM_PLATFORM: env["WFM_PLATFORM"] = WFM_PLATFORM
                self.wfm = MCPServer("warframe", launch, env=env)
            else:
                self.wfm = None
                self.enabled.discard("wfm")

        self._started = False

    def _iter_servers(self):
        for s in (self.fs, self.gh, self.invest, self.local, self.wfm, self.fitness):
            if s is not None:
                yield s

    def server_keys(self) -> List[str]:
        out = []
        if self.fs: out.append("fs")
        if self.gh: out.append("gh")
        if self.invest: out.append("invest")
        if self.local: out.append("local")
        if self.wfm: out.append("wfm")
        if self.fitness: out.append("fitness")
        return out

    def start_server(self, key: str):
        mp = {"fs": self.fs, "gh": self.gh, "invest": self.invest, "local": self.local, "wfm": self.wfm, "fitness": self.fitness}
        s = mp.get(key)
        if not s:
            raise KeyError(f"Servidor '{key}' no está habilitado.")
        if isinstance(s, MCPHttpServer):
            s.start()
        else:
            s.start()
        return True

    def start_all(self):
        if self._started:
            return
        for s in self._iter_servers():
            try:
                if isinstance(s, MCPHttpServer):
                    s.start()
                else:
                    s.start()
            except Exception as e:
                raise RuntimeError(f"Failed starting MCP server '{s.name}': {e}") from e
        self._started = True

    def stop_all(self):
        for s in self._iter_servers():
            try:
                if hasattr(s, "seq"):
                    s.seq += 1
                    if hasattr(s, "_send"):
                        s._send({"jsonrpc": JSONRPC, "id": s.seq, "method": "shutdown"})
            except Exception:
                pass
            try:
                if hasattr(s, "proc") and s.proc:
                    s.proc.terminate()
            except Exception:
                pass
        self._started = False

    def list_all_tools(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for key, srv in [
            ("fs", self.fs), ("gh", self.gh), ("invest", self.invest),
            ("local", self.local), ("wfm", self.wfm), ("fitness", self.fitness)
        ]:
            if not srv: 
                continue
            try:
                tools = srv.list_tools()
                names = [t.get("name") for t in tools if isinstance(t, dict)]
                out[key] = names
            except Exception:
                out[key] = []
        return out

def handle_command_line(line: str, fleet: "MCPFleet") -> Dict[str, Any]:
    """
    !mcp {"tool":"<tool>", "args":{...}, "server":"fs|gh|invest|local|wfm"}
    Si no se especifica 'server', intenta en orden fs -> gh -> invest -> local -> wfm.
    """
    if not line.lower().startswith("!mcp "):
        raise ValueError("Formato no reconocido. Usa: !mcp { ... }")
    payload = json.loads(line[4:].strip())

    tool = payload.get("tool")
    if not tool:
        raise ValueError("Falta 'tool' en el payload de !mcp")
    args = payload.get("args", {}) or {}
    server_key = payload.get("server")

    # 👇 SOPORTE META: listar herramientas desde el cliente
    if tool in ("list_tools", "__list_tools__", "tools", "__tools__"):
        try:
            fleet.start_all()   # por si aún no están iniciados
        except Exception:
            pass
        return {"tools": fleet.list_all_tools()}

    server_map: Dict[str, Any] = {
        "fs": getattr(fleet, "fs", None),
        "gh": getattr(fleet, "gh", None),
        "invest": getattr(fleet, "invest", None),
        "local": getattr(fleet, "local", None),
        "wfm": getattr(fleet, "wfm", None),
        "fitness": getattr(fleet, "fitness", None),
    }
    
    def _wrap_if_needed(server_key: Optional[str], args: Dict[str, Any]) -> Dict[str, Any]:
        if server_key == "fitness" and "params" not in args:
            return {"params": args}
        return args
    
    if server_key:
        s = server_map.get(server_key)
        if not s:
            raise ValueError(f"Servidor desconocido o no habilitado: {server_key}")
        return s.tools_call(tool, _wrap_if_needed(server_key, args))

    for key in ("fs", "gh", "invest", "local", "fitness"):
        s = server_map.get(key)
        if not s:
            continue
        try:
            return s.tools_call(tool, _wrap_if_needed(key, args))
        except Exception:
            continue

    raise RuntimeError("Ningún servidor aceptó la herramienta solicitada")

