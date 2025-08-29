# invest_mcp/tools/rebalance_plan.py
import json
from typing import Dict, Any, List
from .data import get_builtin_prices

DEF = {
    "name": "rebalance_plan",
    "title": "Plan de rebalanceo (trades sugeridos)",
    "description": "Dado holdings actuales y pesos objetivo, propone trades en $ (aprox).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "current": {
                "type": "array",
                "items": {"type":"object","properties":{
                    "symbol":{"type":"string"},
                    "amount":{"type":"number"}
                },"required":["symbol","amount"]}
            },
            "targetWeights": {
                "type": "array",
                "items": {"type":"object","properties":{
                    "symbol":{"type":"string"},
                    "weight":{"type":"number"}
                },"required":["symbol","weight"]}
            }
        },
        "required": ["current","targetWeights"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "totalCurrent":{"type":"number"},
            "targetAmounts":{"type":"array","items":{"type":"object","properties":{
                "symbol":{"type":"string"},"targetAmount":{"type":"number"},"lastPrice":{"type":"number"}
            },"required":["symbol","targetAmount","lastPrice"]}},
            "trades":{"type":"array","items":{"type":"object","properties":{
                "symbol":{"type":"string"},"action":{"type":"string"},"delta":{"type":"number"}
            },"required":["symbol","action","delta"]}}
        },
        "required":["totalCurrent","targetAmounts","trades"]
    }
}

def IMPL(args: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(args, dict): raise ValueError("'arguments' debe ser object")
    curr = args.get("current") or []
    tgt = args.get("targetWeights") or []
    if not isinstance(curr, list) or not isinstance(tgt, list):
        raise ValueError("'current' y 'targetWeights' deben ser arrays")

    # Valor actual con último precio sintético (si amount ya viene en $, perfecto; asumimos $)
    # Para robustez, recalculamos target en $ a partir de suma actual.
    total = sum(float(x.get("amount",0)) for x in curr)
    if total <= 0:
        raise ValueError("El portafolio actual tiene total <= 0")

    prices = get_builtin_prices()
    target_amounts = []
    for t in tgt:
        s = t.get("symbol")
        w = float(t.get("weight", 0))
        if s not in prices or w < 0: continue
        last = float(prices[s][-1])
        target_amounts.append({"symbol": s, "targetAmount": w*total, "lastPrice": last})

    # Indexar current por símbolo
    by_sym = {x["symbol"]: float(x.get("amount",0)) for x in curr if isinstance(x.get("symbol"), str)}
    trades = []
    for ta in target_amounts:
        s = ta["symbol"]
        desired = ta["targetAmount"]
        current_amt = by_sym.get(s, 0.0)
        delta = desired - current_amt
        if abs(delta) < 1e-6: continue
        trades.append({"symbol": s, "action": "BUY" if delta>0 else "SELL", "delta": delta})

    payload = {"totalCurrent": total, "targetAmounts": target_amounts, "trades": trades}
    return {
        "content": [{"type":"text","text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False
    }
