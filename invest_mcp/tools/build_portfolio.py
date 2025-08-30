# invest_mcp/tools/build_portfolio.py
import json
from typing import Dict, Any, List
from .data import get_builtin_prices, UNIVERSE
from invest_mcp.lib.data_live import get_history

DEF = {
    "name": "build_portfolio",
    "title": "Construcción de portafolio (Markowitz long-only, demo)",
    "description": "Genera pesos objetivo según riesgo (1-5), horizonte y universo permitido. Puede usar datos en vivo o sintéticos (fallback).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "capital": {"type": "number", "description": "Capital total a invertir"},
            "riskLevel": {"type": "integer", "description": "1=conservador ... 5=agresivo"},
            "horizonMonths": {"type": "integer", "description": "Solo informativo (ajusta gamma)"},
            "allowedSymbols": {"type": "array", "items": {"type": "string"}},
            "useLive": {"type": "boolean", "description": "Usar datos en vivo (default true)"}
        },
        "required": ["capital", "riskLevel"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "targetWeights": {"type": "array", "items": {"type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "weight": {"type": "number"}
                },
                "required": ["symbol", "weight"]
            }},
            "allocations": {"type": "array", "items": {"type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "amount": {"type": "number"}
                },
                "required": ["symbol", "amount"]
            }},
            "expectedAnnualReturn": {"type": "number"},
            "volAnnual": {"type": "number"},
            "sharpe": {"type": "number"}
        },
        "required": ["targetWeights", "allocations"]
    }
}

def _daily_returns(p: List[float]) -> List[float]:
    return [(p[i] / p[i - 1] - 1.0) for i in range(1, len(p))]

def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)

def _pstdev(xs: List[float]) -> float:
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5

def _cov_matrix(series: List[List[float]]) -> List[List[float]]:
    """
    series: lista de n activos, cada uno con lista de retornos diarios.
    Devuelve covarianza poblacional alineando por la longitud mínima T.
    """
    n = len(series)
    if n < 2:
        raise ValueError("Se requieren al menos 2 series para covarianza")

    T = min(len(s) for s in series)
    if T < 2:
        raise ValueError("Cada serie debe tener al menos 2 puntos")

    S = [s[-T:] for s in series]  # recorta por el final (últimos T)
    mus = [_mean(s) for s in S]

    C = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            acc = 0.0
            mi, mj = mus[i], mus[j]
            si, sj = S[i], S[j]
            for t in range(T):
                acc += (si[t] - mi) * (sj[t] - mj)
            C[i][j] = acc / T  # poblacional (consistente con pstdev)
    return C

def _matvec(C: List[List[float]], w: List[float]) -> List[float]:
    return [sum(C[i][j] * w[j] for j in range(len(w))) for i in range(len(w))]

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))

def _project_simplex(v: List[float]) -> List[float]:
    # Proyección al simplex {w>=0, sum w = 1} (Michelot)
    n = len(v)
    u = sorted(v, reverse=True)
    css = 0.0
    rho = -1
    theta = 0.0
    for i in range(n):
        css += u[i]
        t = (css - 1.0) / (i + 1)
        if u[i] - t > 0:
            rho = i
            theta = t
    if rho == -1:
        theta = (sum(u) - 1.0) / n
    return [max(0.0, x - theta) for x in v]

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(args, dict):
        raise ValueError("'arguments' debe ser object")

    capital = float(args.get("capital", 0))
    risk_level = int(args.get("riskLevel", 3))
    allowed = args.get("allowedSymbols") or list(UNIVERSE.keys())
    allowed = [s for s in allowed if s in UNIVERSE]
    use_live = bool(args.get("useLive", True))

    if capital <= 0:
        raise ValueError("'capital' debe ser > 0")
    if not allowed:
        raise ValueError("No hay símbolos válidos en 'allowedSymbols'")

    # 1) Obtener series de precios (en vivo => get_history; si falla o vacío => fallback sintético)
    hist: Dict[str, List[float]] = {}
    if use_live:
        try:
            hist = get_history(allowed, days=252)
        except Exception:
            hist = {}

    if not hist:
        prices = get_builtin_prices()
        hist = {s: prices[s][-252:] for s in allowed if s in prices}

    # 2) Retornos diarios por símbolo
    series_map = {s: _daily_returns(p) for s, p in hist.items() if len(p) >= 2}
    if len(series_map) < 2:
        raise ValueError("Se requieren >=2 símbolos con historial suficiente")

    symbols = list(series_map.keys())
    R = [series_map[s] for s in symbols]  # lista de listas (días) por símbolo

    # 3) Estadísticos diarios y anualización
    mus_d = [_mean(rets) for rets in R]
    # sig_d no se usa en el optimizador, pero lo mantenemos por claridad
    _ = [_pstdev(rets) for rets in R]
    mu_a = [(1 + m) ** 252 - 1 for m in mus_d]

    # 4) Covarianza diaria -> anual
    C_d = _cov_matrix(R)
    C_a = [[c * 252 for c in row] for row in C_d]

    # 5) Optimización Markowitz (max mu^T w - (gamma/2) w^T Σ w  s.a. w>=0, sum w=1)
    gamma_map = {1: 50.0, 2: 20.0, 3: 10.0, 4: 5.0, 5: 2.0}
    gamma = gamma_map.get(risk_level, 10.0)

    n = len(symbols)
    w = [1.0 / n] * n
    lr = 0.01
    for _ in range(1500):
        Cw = _matvec(C_a, w)
        grad = [-mu_a[i] + gamma * Cw[i] for i in range(n)]
        w = [w[i] - lr * grad[i] for i in range(n)]
        w = _project_simplex(w)

    exp_ret = _dot(mu_a, w)
    vol = (_dot(w, _matvec(C_a, w))) ** 0.5
    rf = 0.02
    sharpe = (exp_ret - rf) / (vol if vol > 0 else 1e-9)

    weights = [{"symbol": s, "weight": float(wi)} for s, wi in zip(symbols, w)]
    allocs = [{"symbol": s, "amount": float(wi * capital)} for s, wi in zip(symbols, w)]
    payload = {
        "targetWeights": weights,
        "allocations": allocs,
        "expectedAnnualReturn": exp_ret,
        "volAnnual": vol,
        "sharpe": sharpe
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
