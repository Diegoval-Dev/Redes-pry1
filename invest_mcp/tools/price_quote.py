# invest_mcp/tools/price_quote.py
import json
from typing import Dict, Any, List
from .data import UNIVERSE, get_builtin_prices
from invest_mcp.lib.data_live import get_history, last_and_returns

DEF = {
    "name": "price_quote",
    "title": "Cotizaciones rápidas",
    "description": "Último precio y retornos 1d/7d/30d. Usa live (yfinance/CG) con fallback sintético por símbolo.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbols": {"type":"array","items":{"type":"string"}},
            "useLive": {"type":"boolean","description":"Usar datos live", "default": True},
            "days": {"type":"integer","description":"Lookback para retornos", "default": 60}
        },
        "required": ["symbols"]
    },
    "outputSchema": {
        "type":"object",
        "properties":{
            "quotes":{"type":"array","items":{"type":"object"}},
            "dataSource":{"type":"string"}
        },
        "required":["quotes","dataSource"]
    }
}

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    syms: List[str] = list(dict.fromkeys(args.get("symbols") or []))
    if not syms: raise ValueError("'symbols' requerido")
    use_live = bool(args.get("useLive", True))
    days = int(args.get("days", 60))

    payload = {"quotes": [], "dataSource": "synthetic"}

    hist = {}
    if use_live:
        try:
            hist = get_history(syms, days=max(days, 60))
        except Exception:
            hist = {}

    if hist:
        payload["dataSource"] = "live"
        quotes = last_and_returns(hist)
        for q in quotes:
            q["name"] = UNIVERSE.get(q["symbol"], {}).get("name", q["symbol"])
        payload["quotes"].extend(quotes)

    got = {q["symbol"] for q in payload["quotes"]}
    missing = [s for s in syms if s not in got]
    if missing:
        prices = get_builtin_prices()
        for s in missing:
            ps = prices.get(s)
            if not ps or len(ps) < 22:
                continue
            def _ret(p, d): return (p[-1]/p[-1-d]-1.0) if len(p) > d else 0.0
            payload["quotes"].append({
                "symbol": s,
                "name": UNIVERSE.get(s, {}).get("name", s),
                "last": float(ps[-1]),
                "ret1d": _ret(ps,1),
                "ret7d": _ret(ps,5),
                "ret30d": _ret(ps,21)
            })

    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
