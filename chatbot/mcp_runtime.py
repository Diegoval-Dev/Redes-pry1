# chatbot/mcp_runtime.py
import os, json, time, subprocess, shutil, platform, io
from typing import Dict, Any, Optional, List
from .config import LOG_DIR, FS_ROOT, REMOTE_MCP_URL, REMOTE_MCP_PATH, \
    MCP_WARFRAME_COMMAND, MCP_WARFRAME_ARGS, WFM_JWT, WFM_BASE_URL, WFM_LANGUAGE, WFM_PLATFORM, \
    MCP_ANKI_COMMAND, MCP_ANKI_ARGS, MCP_ANKI_DB_PATH, MCP_ANKI_MEDIA_DIR
import requests

JSONRPC = "2.0"
PROTO = "2025-06-18"

def _which(cmd: str) -> Optional[str]:
    p = shutil.which(cmd)
    if p: return p
    if platform.system().lower().startswith("win"):
        p = shutil.which(cmd + ".cmd")
        if p: return p
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

class MCPServer:
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

    def _send(self, obj: Dict[str, Any]):
        if not (self.proc and self.proc.stdin):
            raise RuntimeError(f"[{self.name}] process not running / stdin closed")
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
            _log_jsonl(self.log_file, {"dir":"out","obj":obj})
        except OSError as e:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] write to stdin failed: {e}\nChild stderr:\n{stderr_text}") from e

    def _recv(self, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
        if not (self.proc and self.proc.stdout):
            return None
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if not line:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.01)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                _log_jsonl(self.log_file, {"dir":"in","obj":msg})
                return msg
            except json.JSONDecodeError:
                _log_jsonl(self.log_file, {"dir":"in","garbage":line})
        return None

    def _initialize(self):
        self.seq += 1
        self._send({"jsonrpc":JSONRPC,"id":self.seq,"method":"initialize",
                    "params":{"protocolVersion":PROTO,"capabilities":{},
                              "clientInfo":{"name":"ChatHost","version":"0.1"}}})
        rsp = self._recv()
        if not rsp or "result" not in rsp:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] initialize failed. Child stderr:\n{stderr_text}")
        try:
            self._send({"jsonrpc":JSONRPC,"method":"notifications/initialized"})
        except RuntimeError:
            raise

    def tools_call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        self.seq += 1
        self._send({"jsonrpc":JSONRPC,"id":self.seq,"method":"tools/call",
                    "params":{"name":tool,"arguments":args}})
        rsp = self._recv()
        if not rsp:
            stderr_text = _read_all_safe(self.proc.stderr)
            raise RuntimeError(f"[{self.name}] timeout waiting response. Child stderr:\n{stderr_text}")
        if "result" in rsp: return rsp["result"]
        if "error" in rsp: raise RuntimeError(f"[{self.name}] {json.dumps(rsp['error'], ensure_ascii=False)}")
        raise RuntimeError(f"[{self.name}] unexpected {rsp}")

class MCPHttpServer:
    def __init__(self, name: str, base_url: str, rpc_path: str = "/rpc"):
        if not base_url:
            raise RuntimeError(f"[{name}] REMOTE_MCP_URL no configurado")
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.rpc_url = self.base_url + (rpc_path if rpc_path.startswith("/") else f"/{rpc_path}")
        self.seq = 0

    def _send(self, obj: dict) -> dict:
        try:
            resp = requests.post(
                self.rpc_url,
                headers={"Content-Type": "application/json"},
                json=obj,
                timeout=20,
            )
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                raise RuntimeError(
                    f"[{self.name}] HTTP {resp.status_code} at {self.rpc_url}\nBody: {resp.text}"
                ) from e
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"[{self.name}] HTTP request failed: {e}") from e

    def _initialize(self):
        self.seq += 1
        init_req = {
            "jsonrpc": "2.0",
            "id": self.seq,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "ChatHost", "version": "0.1"},
            },
        }
        _ = self._send(init_req)
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._send(notif)

    def start(self):
        self._initialize()

    def tools_call(self, tool: str, args: dict) -> dict:
        self.seq += 1
        req = {
            "jsonrpc": "2.0",
            "id": self.seq,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
        rsp = self._send(req)
        if "result" in rsp:
            return rsp["result"]
        if "error" in rsp:
            raise RuntimeError(f"{self.name}: {rsp['error']}")
        raise RuntimeError(f"{self.name}: unexpected {rsp}")

class MCPFleet:
    def __init__(self):
        self.fs = MCPServer("filesystem", ["npx","-y","@modelcontextprotocol/server-filesystem", FS_ROOT])
        self.gh = MCPServer("github", ["npx","-y","@modelcontextprotocol/server-github"])

        # local-remote HTTP (si está configurado)
        self.local = MCPHttpServer("local-remote", REMOTE_MCP_URL, REMOTE_MCP_PATH) if REMOTE_MCP_URL else None

        # Invest MCP (Python stdio)
        self.invest = MCPServer("invest", ["python","-m","invest_mcp.main"])

        # Warframe Market MCP (Node stdio)
        # 1) Si MCP_WARFRAME_ARGS está vacío y no existe el dist/index.js, caemos a npx mcp-warframe-market
        if MCP_WARFRAME_ARGS:
            wfm_launch = [MCP_WARFRAME_COMMAND, MCP_WARFRAME_ARGS]
        else:
            wfm_launch = ["npx", "-y", "mcp-warframe-market"]

        wfm_env = {}
        if WFM_JWT: wfm_env["WFM_JWT"] = WFM_JWT
        if WFM_BASE_URL: wfm_env["WFM_BASE_URL"] = WFM_BASE_URL
        if WFM_LANGUAGE: wfm_env["WFM_LANGUAGE"] = WFM_LANGUAGE
        if WFM_PLATFORM: wfm_env["WFM_PLATFORM"] = WFM_PLATFORM

        self.wfm = MCPServer("warframe", wfm_launch, env=wfm_env)
        self._started = False

    def start_all(self):
        if self._started: return
        servers = [self.fs, self.gh, self.invest, self.wfm]
        if self.local:
            servers.insert(2, self.local)  # mantener orden parecido al anterior

        for s in servers:
            try:
                s.start()
            except Exception as e:
                raise RuntimeError(f"Failed starting MCP server '{s.name}': {e}") from e
        self._started = True

    def stop_all(self):
        servers = [self.fs, self.gh, self.invest, self.wfm]
        if self.local:
            servers.insert(2, self.local)
        for s in servers:
            try:
                s.seq += 1
                s._send({"jsonrpc":JSONRPC,"id":s.seq,"method":"shutdown"})
            except Exception:
                pass
            try:
                if hasattr(s, "proc") and s.proc:
                    s.proc.terminate()
            except Exception:
                pass
