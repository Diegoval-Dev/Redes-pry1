# invest_mcp/tools/build_portfolio.py
import json, statistics
from typing import Dict, Any, List, Tuple
from .data import get_builtin_prices, UNIVERSE

DEF = {
    "name": "build_portfolio",
    "title": "Construcción de portafolio (Markowitz long-only, demo)",
    "description": "Genera pesos objetivo según riesgo (1-5), horizonte y universo permitido.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "capital": {"type":"number","description":"Capital total a invertir"},
            "riskLevel": {"type":"integer","description":"1=conservador ... 5=agresivo"},
            "horizonMonths": {"type":"integer","description":"Solo informativo (ajusta gamma)"},
            "allowedSymbols": {"type":"array","items":{"type":"string"}}
        },
        "required": ["capital","riskLevel"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "targetWeights":{"type":"array","items":{"type":"object",
                "properties":{
                    "symbol":{"type":"string"},
                    "weight":{"type":"number"}
                },
                "required":["symbol","weight"]
            }},
            "allocations":{"type":"array","items":{"type":"object",
                "properties":{
                    "symbol":{"type":"string"},
                    "amount":{"type":"number"}
                },
                "required":["symbol","amount"]
            }},
            "expectedAnnualReturn":{"type":"number"},
            "volAnnual":{"type":"number"},
            "sharpe":{"type":"number"}
        },
        "required":["targetWeights","allocations"]
    }
}

def _daily_returns(p: List[float]) -> List[float]:
    return [(p[i]/p[i-1]-1.0) for i in range(1,len(p))]

def _mean(rets: List[float]) -> float:
    return sum(rets)/len(rets)

def _pstdev(rets: List[float]) -> float:
    m = _mean(rets)
    return (sum((x-m)**2 for x in rets)/len(rets))**0.5

def _cov_matrix(series: List[List[float]]) -> List[List[float]]:
    """
    series: lista de n activos, cada uno con lista de retornos diarios.
    Devuelve covarianza muestral (poblacional) por día, alineando a T común.
    """
    n = len(series)
    if n < 2:
        raise ValueError("Se requieren al menos 2 series para covarianza")

    T = min(len(s) for s in series)
    if T < 2:
        raise ValueError("Cada serie debe tener al menos 2 puntos")

    S = [s[:T] for s in series]
    mus = [sum(s) / T for s in S]

    C = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            acc = 0.0
            mi, mj = mus[i], mus[j]
            si, sj = S[i], S[j]
            for t in range(T):
                acc += (si[t] - mi) * (sj[t] - mj)
            C[i][j] = acc / T
    return C


def _matvec(C: List[List[float]], w: List[float]) -> List[float]:
    return [sum(C[i][j]*w[j] for j in range(len(w))) for i in range(len(w))]

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x*y for x,y in zip(a,b))

def _project_simplex(v: List[float]) -> List[float]:
    # Proyección al simplex {w>=0, sum w = 1} (Michelot)
    n = len(v)
    u = sorted(v, reverse=True)
    css = 0.0; rho = -1; theta = 0.0
    for i in range(n):
        css += u[i]
        t = (css - 1.0) / (i+1)
        if u[i] - t > 0:
            rho = i; theta = t
    if rho == -1: theta = (sum(u)-1.0)/n
    return [max(0.0, x - theta) for x in v]

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(args, dict): raise ValueError("'arguments' debe ser object")
    capital = float(args.get("capital", 0))
    risk_level = int(args.get("riskLevel", 3))
    allowed = args.get("allowedSymbols") or list(UNIVERSE.keys())
    allowed = [s for s in allowed if s in UNIVERSE]

    if capital <= 0: raise ValueError("'capital' debe ser > 0")
    if not allowed: raise ValueError("No hay símbolos válidos en 'allowedSymbols'")

    prices = get_builtin_prices()
    # construir matriz de retornos diarios alineada
    series = {}
    for s in allowed:
        p = prices.get(s)
        if not p or len(p) < 253: continue
        series[s] = _daily_returns(p[-252:])  # último año hábil
    if len(series) < 2: raise ValueError("Se requieren >=2 símbolos con historial suficiente")

    symbols = list(series.keys())
    R = [series[s] for s in symbols]  # lista de listas (días) por símbolo
    # transponer a (día -> vector activos)
    # para cov var necesitamos por-asset listas; ya están como R[symbol][t]
    mus_d = [_mean(rets) for rets in R]
    sig_d = [_pstdev(rets) for rets in R]
    # anualizar
    mu_a = [(1+m)**252 - 1 for m in mus_d]

    # cov diaria entre activos
    # construir por día columnas
    T = len(R[0])
    per_asset = R
    # transponer a listas por activo ya está; cov usa esas listas
    C_d = _cov_matrix(per_asset)
    # anualizar cov
    C_a = [[c*252 for c in row] for row in C_d]

    # Gradiente proyectado para: max mu^T w - (gamma/2) w^T Σ w  s.a. w>=0, sum w=1
    # gamma depende del risk_level (más alto -> menos penaliza varianza)
    gamma_map = {1: 50.0, 2: 20.0, 3: 10.0, 4: 5.0, 5: 2.0}
    gamma = gamma_map.get(risk_level, 10.0)

    # f(w) = -mu^T w + (gamma/2) w^T Σ w  (minimización equivalente)
    # grad = -mu + gamma * Σ w
    n = len(symbols)
    w = [1.0/n]*n
    lr = 0.01
    for _ in range(1500):
        Cw = _matvec(C_a, w)
        grad = [ -mu_a[i] + gamma * Cw[i] for i in range(n) ]
        w = [w[i] - lr*grad[i] for i in range(n)]
        w = _project_simplex(w)

    exp_ret = _dot(mu_a, w)
    vol = (_dot(w, _matvec(C_a, w)))**0.5
    rf = 0.02
    sharpe = (exp_ret - rf)/(vol if vol>0 else 1e-9)

    weights = [{"symbol": s, "weight": float(wi)} for s, wi in zip(symbols, w)]
    allocs = [{"symbol": s, "amount": float(wi*capital)} for s, wi in zip(symbols, w)]
    payload = {
        "targetWeights": weights,
        "allocations": allocs,
        "expectedAnnualReturn": exp_ret,
        "volAnnual": vol,
        "sharpe": sharpe
    }
    return {
        "content": [{"type":"text","text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
