import json
from typing import Dict, Any, List
from .data import get_builtin_prices, UNIVERSE  # fallback sintético
from invest_mcp.lib.data_live import get_history, last_and_returns

DEF = {
    "name": "price_quote",
    "title": "Cotización (live con fallback)",
    "description": "Devuelve último precio y retornos 1D/7D/30D usando yfinance/CoinGecko (si useLive=true) o datos sintéticos.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbols": {"type": "array", "items": {"type": "string"}},
            "useLive": {"type": "boolean", "description": "Usar datos en vivo (default true)"},
            "days": {"type": "integer", "description": "Ventana histórica para retornos", "default": 252}
        },
        "required": ["symbols"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "quotes": {"type": "array", "items": {"type": "object",
                "properties": {"symbol":{"type":"string"}, "name":{"type":"string"},
                               "last":{"type":"number"}, "ret1d":{"type":"number"},
                               "ret7d":{"type":"number"}, "ret30d":{"type":"number"}},
                "required": ["symbol","last"]
            }}
        },
        "required": ["quotes"]
    }
}

def _daily_returns(prices: List[float]) -> List[float]:
    return [(prices[i]/prices[i-1]-1.0) for i in range(1, len(prices))]

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(args, dict): raise ValueError("'arguments' debe ser object")
    syms: List[str] = args.get("symbols") or []
    use_live = bool(args.get("useLive", True))
    days = int(args.get("days", 252))
    if not syms: raise ValueError("'symbols' no puede estar vacío")

    payload = {"quotes": []}

    if use_live:
        try:
            hist = get_history(syms, days=days)
            quotes = last_and_returns(hist)
            for q in quotes:
                q["name"] = UNIVERSE.get(q["symbol"], {}).get("name", q["symbol"])
            payload["quotes"] = quotes
            return {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                "structuredContent": payload,
                "isError": False
            }
        except Exception as e:
            # cae a sintético
            pass

    # Fallback sintético
    prices = get_builtin_prices()
    out = []
    for s in syms:
        if s not in prices: continue
        ps = prices[s]
        def _ret(p, d): return (p[-1]/p[-1-d]-1.0) if len(p)>d else 0.0
        out.append({
            "symbol": s,
            "name": UNIVERSE.get(s, {}).get("name", s),
            "last": float(ps[-1]),
            "ret1d": _ret(ps,1),
            "ret7d": _ret(ps,5),
            "ret30d": _ret(ps,21),
        })
    payload["quotes"] = out
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
