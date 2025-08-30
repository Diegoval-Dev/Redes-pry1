# invest_mcp/tools/price_quote.py
import json
from typing import Dict, Any, List
from .data import UNIVERSE, get_builtin_prices
from invest_mcp.lib.data_live import (
    get_history, last_and_returns, fetch_cg_simple_price, COINGECKO_IDS
)


DEF = {
    "name": "price_quote",
    "title": "Cotizaciones rápidas",
    "description": "Último precio y retornos 1d/7d/30d con live (yfinance/CoinGecko) y fallback por símbolo.",
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

    quotes: List[Dict[str, Any]] = []
    live_count = 0
    synthetic_count = 0

    hist = {}
    if use_live:
        try:
            hist = get_history(syms, days=max(days, 60)) or {}
        except Exception:
            hist = {}

    # 1) Si hay histórico de alguno, úsalo para retornos; last será sobreescrito por spot si cripto
    if hist:
        for q in last_and_returns(hist):
            sym = q["symbol"]
            q["name"] = UNIVERSE.get(sym, {}).get("name", sym)
            q["currency"] = "USD"
            q["source"] = "live-hist"
            quotes.append(q)
            live_count += 1

    have = {q["symbol"] for q in quotes}

    # 2) Para cualquier CRYPTO solicitada (tenga o no histórico), pedir spot a /simple/price
    crypto_syms = [s for s in syms if s in COINGECKO_IDS]
    need_spot = [s for s in crypto_syms if s not in have]
    if use_live and need_spot:
        spot = fetch_cg_simple_price(need_spot, vs="usd") or {}
        for s in need_spot:
            if s in spot:
                quotes.append({
                    "symbol": s,
                    "name": UNIVERSE.get(s, {}).get("name", s),
                    "last": float(spot[s]),
                    "ret1d": 0.0, "ret7d": 0.0, "ret30d": 0.0,  # sin hist no estimamos retornos
                    "currency": "USD",
                    "source": "live-spot"
                })
                live_count += 1

    have = {q["symbol"] for q in quotes}

    # 3) Completar lo que falte con sintético (como último recurso)
    missing = [s for s in syms if s not in have]
    if missing:
        prices = get_builtin_prices()
        for s in missing:
            ps = prices.get(s)
            if not ps or len(ps) < 22:
                continue
            def _ret(p, d): return (p[-1]/p[-1-d]-1.0) if len(p) > d else 0.0
            quotes.append({
                "symbol": s,
                "name": UNIVERSE.get(s, {}).get("name", s),
                "last": float(ps[-1]),
                "ret1d": _ret(ps,1),
                "ret7d": _ret(ps,5),
                "ret30d": _ret(ps,21),
                # currency del builtin puede no ser USD; por eso lo marcamos:
                "currency": UNIVERSE.get(s, {}).get("currency", "UNKNOWN"),
                "source": "synthetic"
            })
            synthetic_count += 1

    # 4) Etiqueta de dataSource global
    if live_count and synthetic_count:
        ds = "mixed"
    elif live_count:
        ds = "live"
    else:
        ds = "synthetic"

    payload = {"quotes": quotes, "dataSource": ds}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }