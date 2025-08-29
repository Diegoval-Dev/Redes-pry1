# invest_mcp/tools/data.py
from __future__ import annotations
import math, random
from typing import Dict, List, Tuple

# Universo base (acciones/índices/commodities/cripto)
UNIVERSE = {
    "SPY": {"name": "S&P 500 ETF", "class": "equity"},
    "QQQ": {"name": "Nasdaq-100 ETF", "class": "equity"},
    "DIA": {"name": "Dow Jones ETF", "class": "equity"},
    "GLD": {"name": "Gold Trust", "class": "commodity"},
    "BTC": {"name": "Bitcoin", "class": "crypto"},
    "ETH": {"name": "Ethereum", "class": "crypto"},
}

def _gen_series(seed: int, start_price: float, mu_annual: float, vol_annual: float, days: int = 756) -> List[float]:
    """
    Serie sintética GBM-like (3 años * 252 días = 756).
    mu_annual, vol_annual en términos anuales. Paso diario.
    """
    random.seed(seed)
    dt = 1.0 / 252.0
    mu_d = mu_annual
    vol_d = vol_annual
    price = start_price
    series = [price]
    for _ in range(days - 1):
        # dS/S = mu*dt + sigma*sqrt(dt)*Z
        z = random.gauss(0.0, 1.0)
        price *= math.exp((mu_d - 0.5 * vol_d * vol_d) * dt + vol_d * math.sqrt(dt) * z)
        series.append(price)
    return series

def get_builtin_prices() -> Dict[str, List[float]]:
    """
    Devuelve precios sintéticos reproducibles por símbolo.
    Parametrización conservadora/realista por clase de activo.
    """
    return {
        # start, mu anual aprox, vol anual aprox
        "SPY": _gen_series(42, 400.0, 0.09, 0.18),
        "QQQ": _gen_series(43, 350.0, 0.12, 0.28),
        "DIA": _gen_series(44, 340.0, 0.07, 0.16),
        "GLD": _gen_series(45, 180.0, 0.03, 0.12),
        "BTC": _gen_series(46, 50000.0, 0.35, 0.75),
        "ETH": _gen_series(47, 2500.0, 0.40, 0.95),
    }
