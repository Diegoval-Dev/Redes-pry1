import json
from typing import Dict, Any, Tuple, List
from statistics import mean, median, pvariance, pstdev, quantiles

def _require_type(obj: Any, expected: type, name: str) -> Tuple[bool, str]:
    if not isinstance(obj, expected):
        return False, f"'{name}' debe ser de tipo {expected.__name__}"
    return True, ""

DEF = {
    "name": "timeseries_stats",
    "title": "Estadística descriptiva de series",
    "description": "Calcula media, mediana, varianza, desviación estándar, cuartiles (Q1, Q3), IQR y outliers (regla de Tukey).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Serie numérica."
            },
            "iqrMultiplier": {
                "type": "number",
                "description": "Multiplicador para detección de outliers (por defecto 1.5)."
            }
        },
        "required": ["values"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "min": {"type": "number"},
            "max": {"type": "number"},
            "mean": {"type": "number"},
            "median": {"type": "number"},
            "variance": {"type": "number"},
            "stdev": {"type": "number"},
            "q1": {"type": "number"},
            "q3": {"type": "number"},
            "iqr": {"type": "number"},
            "lowerFence": {"type": "number"},
            "upperFence": {"type": "number"},
            "outliers": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "index": {"type": "integer"},
                    "value": {"type": "number"}
                }, "required": ["index","value"]}
            }
        },
        "required": ["count","min","max","mean","median","variance","stdev","q1","q3","iqr","lowerFence","upperFence","outliers"]
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
    if len(values) == 0:
        raise ValueError("'values' no debe estar vacío")

    xs: List[float] = []
    for i, v in enumerate(values):
        if not isinstance(v, (int, float)):
            raise ValueError(f"'values[{i}]' debe ser number")
        xs.append(float(v))

    k = args.get("iqrMultiplier", 1.5)
    if not isinstance(k, (int, float)):
        raise ValueError("'iqrMultiplier' debe ser number")

    xs_sorted = sorted(xs)
    q = quantiles(xs_sorted, n=4, method='inclusive') if len(xs_sorted) >= 2 else [xs_sorted[0], xs_sorted[0], xs_sorted[0]]
    q1, q2, q3 = q[0], q[1], q[2]
    q2 = median(xs_sorted)

    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr

    outs = [{"index": i, "value": v} for i, v in enumerate(xs) if v < lower or v > upper]

    payload = {
        "count": len(xs),
        "min": min(xs),
        "max": max(xs),
        "mean": mean(xs),
        "median": q2,
        "variance": pvariance(xs) if len(xs) > 1 else 0.0,
        "stdev": pstdev(xs) if len(xs) > 1 else 0.0,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "lowerFence": lower,
        "upperFence": upper,
        "outliers": outs
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
