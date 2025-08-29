# invest_mcp/tools/risk_metrics.py
import json, math, statistics
from typing import Dict, Any, List
from .data import get_builtin_prices

DEF = {
    "name": "risk_metrics",
    "title": "Métricas de riesgo y retorno",
    "description": "Calcula retorno esperado anualizado, volatilidad anual y Sharpe para símbolos.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbols": {"type":"array","items":{"type":"string"}},
            "riskFree": {"type":"number", "description":"Tasa libre anual (p.ej. 0.03)"},
            "lookbackDays": {"type":"integer", "description":"Ventana de cálculo", "default":252}
        },
        "required": ["symbols"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "metrics": {"type":"array","items":{"type":"object",
                "properties": {
                    "symbol":{"type":"string"},
                    "meanAnnual":{"type":"number"},
                    "volAnnual":{"type":"number"},
                    "sharpe":{"type":"number"}
                },
                "required":["symbol","meanAnnual","volAnnual","sharpe"]
            }}
        },
        "required":["metrics"]
    }
}

def _daily_returns(prices: List[float]) -> List[float]:
    return [(prices[i]/prices[i-1]-1.0) for i in range(1, len(prices))]

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(args, dict): raise ValueError("'arguments' debe ser object")
    syms = args.get("symbols")
    rf = float(args.get("riskFree", 0.02))
    lb = int(args.get("lookbackDays", 252))
    prices = get_builtin_prices()
    out = []
    for s in syms:
        if s not in prices: continue
        p = prices[s][-lb:]
        rets = _daily_returns(p)
        if len(rets) < 2: continue
        mu_d = statistics.mean(rets)
        vol_d = statistics.pstdev(rets)
        mu_a = (1+mu_d)**252 - 1
        vol_a = vol_d * (252**0.5)
        sharpe = (mu_a - rf) / vol_a if vol_a > 0 else 0.0
        out.append({"symbol": s, "meanAnnual": mu_a, "volAnnual": vol_a, "sharpe": sharpe})
    payload = {"metrics": out}
    return {
        "content": [{"type":"text","text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
