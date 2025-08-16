import json
from typing import Dict, Any, Tuple, List

def _require_type(obj: Any, expected: type, name: str) -> Tuple[bool, str]:
    if not isinstance(obj, expected):
        return False, f"'{name}' debe ser de tipo {expected.__name__}"
    return True, ""

DEF = {
    "name": "grep_lines",
    "title": "Filtro de líneas",
    "description": "Devuelve las líneas que contienen un substring.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "needle": {"type": "string", "description": "Substring a buscar"},
            "lines": {"type": "array", "items": {"type": "string"}, "description": "Líneas a filtrar"}
        },
        "required": ["needle", "lines"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {"matches": {"type": "array", "items": {"type": "string"}}},
        "required": ["matches"]
    }
}

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    ok, err = _require_type(args, dict, "arguments")
    if not ok:
        raise ValueError(err)
    needle = args.get("needle")
    lines: List[str] = args.get("lines")
    ok, err = _require_type(needle, str, "needle")
    if not ok:
        raise ValueError(err)
    ok, err = _require_type(lines, list, "lines")
    if not ok:
        raise ValueError(err)
    for i, ln in enumerate(lines):
        if not isinstance(ln, str):
            raise ValueError(f"'lines[{i}]' debe ser string")
    matches = [ln for ln in lines if needle in ln]
    payload = {"matches": matches}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
