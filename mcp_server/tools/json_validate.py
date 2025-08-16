import json, re
from typing import Dict, Any, Tuple, List, Union

Json = Union[dict, list, str, int, float, bool, None]

def _require_type(obj: Any, expected: type, name: str) -> Tuple[bool, str]:
    if not isinstance(obj, expected):
        return False, f"'{name}' debe ser de tipo {expected.__name__}"
    return True, ""

DEF = {
    "name": "json_validate",
    "title": "Validador JSON (mini-schema)",
    "description": "Valida un JSON contra un mini-schema (required, type, enum, pattern, min/max, minItems/maxItems, items, nullable, allowAdditionalProperties).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "data": {"type": "object", "description": "JSON a validar (objeto raíz)."},
            "schema": {
                "type": "object",
                "description": "Mini-schema: { required: string[], properties: { key: rules }, allowAdditionalProperties?: bool }.\nReglas: { type, enum, pattern, min, max, minItems, maxItems, items, nullable }"
            },
            "path": {"type": "string", "description": "Ruta inicial para mensajes (opcional)."}
        },
        "required": ["data", "schema"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "valid": {"type": "boolean"},
            "errors": {"type": "array", "items": {"type": "string"}},
            "checkedKeys": {"type": "integer"}
        },
        "required": ["valid","errors","checkedKeys"]
    }
}

# --- utilidades de validación ---
_PRIMITIVE_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}

def _type_name(pyval: Any) -> str:
    if pyval is None: return "null"
    if isinstance(pyval, bool): return "boolean"
    if isinstance(pyval, int) and not isinstance(pyval, bool): return "integer"
    if isinstance(pyval, float): return "number"
    if isinstance(pyval, str): return "string"
    if isinstance(pyval, list): return "array"
    if isinstance(pyval, dict): return "object"
    return type(pyval).__name__

def _validate_value(value: Json, rules: Dict[str, Any], path: str, errors: List[str]) -> None:
    if value is None:
        if not rules.get("nullable", False):
            errors.append(f"{path}: valor null no permitido")
        return

    rtype = rules.get("type")
    if rtype:
        expected = _PRIMITIVE_TYPES.get(rtype)
        if expected is None:
            errors.append(f"{path}: type desconocido '{rtype}'")
        else:
            if rtype == "integer" and isinstance(value, bool):
                errors.append(f"{path}: se recibió boolean, se esperaba integer")
            elif not isinstance(value, expected):
                errors.append(f"{path}: se esperaba {rtype}, se recibió {_type_name(value)}")
                return

    if "enum" in rules:
        enum_vals = rules["enum"]
        if value not in enum_vals:
            errors.append(f"{path}: valor '{value}' no está en enum {enum_vals}")

    if "pattern" in rules:
        if not isinstance(value, str):
            errors.append(f"{path}: pattern aplicable solo a string")
        else:
            try:
                if re.search(rules["pattern"], value) is None:
                    errors.append(f"{path}: no cumple pattern /{rules['pattern']}/")
            except re.error as e:
                errors.append(f"{path}: pattern inválido ({e})")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "min" in rules and value < rules["min"]:
            errors.append(f"{path}: {value} < min {rules['min']}")
        if "max" in rules and value > rules["max"]:
            errors.append(f"{path}: {value} > max {rules['max']}")

    if isinstance(value, str):
        if "min" in rules and len(value) < rules["min"]:
            errors.append(f"{path}: len={len(value)} < min {rules['min']}")
        if "max" in rules and len(value) > rules["max"]:
            errors.append(f"{path}: len={len(value)} > max {rules['max']}")

    # array: minItems/maxItems + items
    if isinstance(value, list):
        if "minItems" in rules and len(value) < rules["minItems"]:
            errors.append(f"{path}: items={len(value)} < minItems {rules['minItems']}")
        if "maxItems" in rules and len(value) > rules["maxItems"]:
            errors.append(f"{path}: items={len(value)} > maxItems {rules['maxItems']}")
        if "items" in rules and isinstance(rules["items"], dict):
            item_rules = rules["items"]
            for i, it in enumerate(value):
                _validate_value(it, item_rules, f"{path}[{i}]", errors)

    if isinstance(value, dict):
        props = rules.get("properties", {})
        allow_extra = rules.get("allowAdditionalProperties", True)

        required = rules.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: requerido y ausente")

        for key, subrules in props.items():
            if key in value:
                _validate_value(value[key], subrules, f"{path}.{key}", errors)

        if not allow_extra:
            extra = [k for k in value.keys() if k not in props]
            for k in extra:
                errors.append(f"{path}.{k}: propiedad no permitida (allowAdditionalProperties=false)")

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    ok, err = _require_type(args, dict, "arguments")
    if not ok:
        raise ValueError(err)

    data = args.get("data")
    schema = args.get("schema")
    path = args.get("path", "$")

    ok, err = _require_type(data, dict, "data")
    if not ok:
        raise ValueError(err)
    ok, err = _require_type(schema, dict, "schema")
    if not ok:
        raise ValueError(err)
    if not isinstance(path, str):
        raise ValueError("'path' debe ser string")

    errors: List[str] = []
    _validate_value(data, schema, path, errors)

    payload = {
        "valid": len(errors) == 0,
        "errors": errors,
        "checkedKeys": len(data.keys()) if isinstance(data, dict) else 0
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
