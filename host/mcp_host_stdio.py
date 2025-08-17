import json, subprocess, sys, os, time, shutil, shlex, platform
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv


JSONRPC = "2.0"
PROTOCOL_VERSION = "2025-06-18"

class MCPProcess:
    def __init__(self, popen: subprocess.Popen):
        self.proc = popen

    def send(self, obj: Dict[str, Any]) -> None:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        assert self.proc.stdin is not None
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def recv(self, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        assert self.proc.stdout is not None
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if not line:
                time.sleep(0.01)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                # Ignora líneas no-JSON extraviadas
                continue
        return None

    def close(self):
        try:
            self.send({"jsonrpc": JSONRPC, "id": 9999, "method": "shutdown"})
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass

def initialize(server: MCPProcess, client_name="UVG-Host", client_version="0.1.0") -> Dict[str, Any]:
    req = {
        "jsonrpc": JSONRPC,
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": client_version}
        }
    }
    server.send(req)
    rsp = server.recv()
    if not rsp or "result" not in rsp:
        raise RuntimeError("initialize failed")
    server.send({"jsonrpc": JSONRPC, "method": "notifications/initialized"})
    return rsp["result"]

def tools_list(server: MCPProcess) -> List[Dict[str, Any]]:
    server.send({"jsonrpc": JSONRPC, "id": 2, "method": "tools/list", "params": {}})
    rsp = server.recv()
    if rsp and "result" in rsp:
        return rsp["result"].get("tools", [])
    raise RuntimeError("tools/list failed")

def tools_call(server: MCPProcess, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    server.send({"jsonrpc": JSONRPC, "id": 3, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    rsp = server.recv()
    if not rsp:
        raise RuntimeError(f"tools/call {name} timed out")
    if "result" in rsp:
        return rsp["result"]
    if "error" in rsp:
        raise RuntimeError(f"tools/call {name} error: {json.dumps(rsp['error'], ensure_ascii=False)}")
    raise RuntimeError(f"tools/call {name} unexpected response: {json.dumps(rsp, ensure_ascii=False)}")


def _flatten_args(nested: List[List[str]]) -> List[str]:
    # Convierte [[-y], [@pkg], [path con espacios]] -> [-y, @pkg, path...]
    flat: List[str] = []
    for group in nested:
        if len(group) == 1 and (" " in group[0] or "\t" in group[0]):
            # Por compat con el viejo uso: "--arg 'cadena con espacios'"
            flat.extend(shlex.split(group[0], posix=False))
        else:
            flat.extend(group)
    return flat

def _resolve_executable(cmd: str) -> Optional[str]:
    p = shutil.which(cmd)
    if p:
        return p
    # En Windows, npx/npm suelen ser .cmd
    if platform.system().lower().startswith("win"):
        p = shutil.which(cmd + ".cmd")
        if p:
            return p
    return None

def main():
    load_dotenv()
    import argparse
    ap = argparse.ArgumentParser(description="Host MCP mínimo (stdio)")
    ap.add_argument("--cmd", required=True, help="Comando del servidor (ej. npx)")
    ap.add_argument("--arg", nargs="+", action="append", default=[], help="Argumento(s) del servidor (repetible)")
    ap.add_argument("--call", help="Nombre de herramienta a invocar (opcional)")
    ap.add_argument("--args", help="JSON con argumentos de la herramienta (opcional)", default="{}")
    ap.add_argument("--env", action="append", default=[], help="Variables env KEY=VALUE para el proceso hijo")
    args = ap.parse_args()

    env = os.environ.copy()
    for pair in args.env:
        if "=" in pair:
            k, v = pair.split("=", 1)
            env[k] = v

    flat_args = _flatten_args(args.arg)  # lista final de argumentos
    exe = _resolve_executable(args.cmd)

    full_cmd = [args.cmd] + flat_args
    print(f"[host] launching: {' '.join(full_cmd)}", file=sys.stderr)

    popen_kwargs = dict(
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env=env
    )

    if exe is not None:
        # Ejecuta directamente el ejecutable resuelto
        popen = subprocess.Popen([exe] + flat_args, **popen_kwargs)
    else:
        # Último recurso: usa shell en Windows para resolver shims
        if platform.system().lower().startswith("win"):
            popen = subprocess.Popen(" ".join(full_cmd), shell=True, **popen_kwargs)
        else:
            # En Unix, si no está, fallará — mejor error claro
            raise FileNotFoundError(f"No se encontró ejecutable para '{args.cmd}' en PATH")

    server = MCPProcess(popen)

    try:
        init_info = initialize(server)
        print("[host] initialize.ok:", json.dumps(init_info, ensure_ascii=False))
        tool_defs = tools_list(server)
        print("[host] tools:", json.dumps([t["name"] for t in tool_defs], ensure_ascii=False))

        if args.call:
            call_args = json.loads(args.args)
            result = tools_call(server, args.call, call_args)
            print("[host] call.result:", json.dumps(result, ensure_ascii=False))

    finally:
        server.close()


if __name__ == "__main__":
    main()
