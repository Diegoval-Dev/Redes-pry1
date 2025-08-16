import json, hashlib
from typing import Dict, Any, Tuple

def _require_type(obj: Any, expected: type, name: str) -> Tuple[bool, str]:
    if not isinstance(obj, expected):
        return False, f"'{name}' debe ser de tipo {expected.__name__}"
    return True, ""

DEF = {
    "name": "sha256",
    "title": "Hash SHA-256",
    "description": "Calcula el hash SHA-256 de una cadena UTF-8.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Texto de entrada"}},
        "required": ["text"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {"hex": {"type": "string"}},
        "required": ["hex"]
    }
}

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    ok, err = _require_type(args, dict, "arguments")
    if not ok:
        raise ValueError(err)
    text = args.get("text")
    ok, err = _require_type(text, str, "text")
    if not ok:
        raise ValueError(err)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload = {"hex": digest}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
