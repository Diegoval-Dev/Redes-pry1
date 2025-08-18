import os, json, time, subprocess, shutil, platform
from typing import Dict, Any, Optional, List
from .config import LOG_DIR, FS_ROOT

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

class MCPServer:
    def __init__(self, name: str, launch: List[str], env: Optional[Dict[str,str]] = None):
        self.name = name
        self.launch = launch
        self.env = {**os.environ, **(env or {})}
        self.proc: Optional[subprocess.Popen] = None
        self.seq = 0
        self.log_file = os.path.join(LOG_DIR, f"mcp_{name}.jsonl")

    def start(self):
        if self.proc and self.proc.poll() is None: return
        exe = _which(self.launch[0]) or self.launch[0]
        use_shell = False
        if not _which(self.launch[0]) and platform.system().lower().startswith("win"):
            use_shell = True
        self.proc = subprocess.Popen(
            ([exe] + self.launch[1:]) if not use_shell else " ".join(self.launch),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=self.env, shell=use_shell
        )
        self._initialize()

    def _send(self, obj: Dict[str, Any]):
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        _log_jsonl(self.log_file, {"dir":"out","obj":obj})

    def _recv(self, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
        assert self.proc and self.proc.stdout
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if not line:
                time.sleep(0.01); continue
            line = line.strip()
            if not line: continue
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
        _ = self._recv()
        self._send({"jsonrpc":JSONRPC,"method":"notifications/initialized"})

    def tools_call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        self.seq += 1
        self._send({"jsonrpc":JSONRPC,"id":self.seq,"method":"tools/call",
                    "params":{"name":tool,"arguments":args}})
        rsp = self._recv()
        if not rsp: raise RuntimeError(f"{self.name}: timeout")
        if "result" in rsp: return rsp["result"]
        if "error" in rsp: raise RuntimeError(f"{self.name}: {rsp['error']}")
        raise RuntimeError(f"{self.name}: unexpected {rsp}")

class MCPFleet:
    def __init__(self):
        self.fs = MCPServer("filesystem", ["npx","-y","@modelcontextprotocol/server-filesystem", FS_ROOT])
        self.gh = MCPServer("github", ["npx","-y","@modelcontextprotocol/server-github"])
        self.local = MCPServer("local", ["python","main.py"])
        self._started = False

    def start_all(self):
        if self._started: return
        self.fs.start(); self.gh.start(); self.local.start()
        self._started = True

    def stop_all(self):
        for s in (self.fs, self.gh, self.local):
            try:
                s.seq += 1
                s._send({"jsonrpc":JSONRPC,"id":s.seq,"method":"shutdown"})
            except Exception: pass
            try:
                if s.proc: s.proc.terminate()
            except Exception: pass
