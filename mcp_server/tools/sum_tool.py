import json
from typing import Dict, Any, Tuple

def _require_type(obj: Any, expected: type, name: str) -> Tuple[bool, str]:
    if not isinstance(obj, expected):
        return False, f"'{name}' debe ser de tipo {expected.__name__}"
    return True, ""

DEF = {
    "name": "sum",
    "title": "Sumatoria segura",
    "description": "Suma una lista de números.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "values": {"type": "array", "items": {"type": "number"}, "description": "Lista de números a sumar"}
        },
        "required": ["values"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {"sum": {"type": "number"}},
        "required": ["sum"]
    }
}

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    ok, err = _require_type(args, dict, "arguments")
    if not ok:
        raise ValueError(err)
    values = args.get("values")
    ok, err = _require_type(values, list, "values")
    if not ok:
        raise ValueError(err)
    for i, v in enumerate(values):
        if not isinstance(v, (int, float)):
            raise ValueError(f"'values[{i}]' debe ser number")
    total = float(sum(values))
    payload = {"sum": total}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
