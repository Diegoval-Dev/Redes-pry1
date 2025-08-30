from __future__ import annotations
import os, json, time, hashlib, requests
from typing import Dict, List, Tuple
import pandas as pd
import yfinance as yf

# -------- Config de cache simple (archivos JSON) --------
CACHE_DIR = os.environ.get("INVEST_MCP_CACHE_DIR", os.path.join(".cache","invest_mcp"))
os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_path(key: str) -> str:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.json")

def cache_load(key: str, ttl_seconds: int) -> dict | None:
    path = _cache_path(key)
    if not os.path.exists(path): return None
    try:
        st = os.stat(path)
        if time.time() - st.st_mtime > ttl_seconds:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def cache_save(key: str, obj: dict) -> None:
    path = _cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    except Exception:
        pass

# -------- Universo y mapeos --------
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    # añade más si lo necesitas
}

def split_symbols(symbols: List[str]) -> Tuple[List[str], List[str]]:
    """Devuelve (yf_tickers, cg_symbols). Si está en COINGECKO_IDS => crypto, si no => yfinance."""
    yf_list, cg_list = [], []
    for s in symbols:
        if s in COINGECKO_IDS:
            cg_list.append(s)
        else:
            yf_list.append(s)
    return yf_list, cg_list

# -------- Fetch Yahoo Finance --------
def fetch_yf_history(tickers: List[str], period: str = "1y", interval: str = "1d") -> Dict[str, List[float]]:
    """
    Devuelve dict: ticker -> lista de precios diarios (Adj Close).
    Usa cache 10 minutos.
    """
    if not tickers:
        return {}
    key = f"yf_hist:{','.join(sorted(tickers))}:{period}:{interval}"
    cached = cache_load(key, ttl_seconds=600)
    if cached is not None:
        return cached

    df = yf.download(tickers=tickers, period=period, interval=interval, auto_adjust=True, progress=False)
    # yfinance devuelve:
    # - multiindex columnas si hay varios tickers
    # - si es uno, columnas simples
    out: Dict[str, List[float]] = {}
    if isinstance(df.columns, pd.MultiIndex):
        # tomamos 'Close' (ya auto_adjusted)
        if ("Close" in df.columns.levels[0]) or ("Adj Close" in df.columns.levels[0]):
            level0 = "Close" if "Close" in df.columns.levels[0] else "Adj Close"
            sub = df[level0]
        else:
            # si fallo raro, intenta 'Close'
            sub = df["Close"]
        for t in sub.columns:
            ser = sub[t].dropna()
            if len(ser) >= 2:
                out[str(t)] = [float(x) for x in ser.tolist()]
    else:
        # un solo ticker
        col = "Close" if "Close" in df.columns else ("Adj Close" if "Adj Close" in df.columns else None)
        if col is None:
            return {}
        ser = df[col].dropna()
        if len(ser) >= 2:
            out[str(tickers[0])] = [float(x) for x in ser.tolist()]

    cache_save(key, out)
    return out

# -------- Fetch CoinGecko --------
def fetch_cg_history(symbols: List[str], days: int = 365, vs: str = "usd") -> Dict[str, List[float]]:
    """
    Devuelve dict: symbol -> lista de precios diarios (aprox) desde CoinGecko.
    Usa cache 10 minutos.
    """
    out: Dict[str, List[float]] = {}
    for sym in symbols:
        cg_id = COINGECKO_IDS.get(sym)
        if not cg_id:
            continue
        key = f"cg_hist:{cg_id}:{days}:{vs}"
        cached = cache_load(key, ttl_seconds=600)
        if cached is not None:
            out[sym] = cached
            continue

        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
        params = {"vs_currency": vs, "days": days}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        # data["prices"] ~ [[ms, price], ...]
        prices = [float(p[1]) for p in data.get("prices", [])]
        # Filtra NaNs/zeros raros
        prices = [p for p in prices if p is not None]
        if len(prices) >= 2:
            out[sym] = prices
            cache_save(key, prices)
    return out

# -------- Utilidades comunes --------
def align_min_length(series_dict: Dict[str, List[float]]) -> Dict[str, List[float]]:
    """Recorta todas las listas a la mínima longitud encontrada."""
    if not series_dict:
        return {}
    L = min(len(v) for v in series_dict.values())
    if L < 2:
        return {}
    return {k: v[-L:] for k, v in series_dict.items()}

def get_history(symbols: List[str], days: int = 252) -> Dict[str, List[float]]:
    """
    Obtiene históricos combinando yfinance (no-crypto) y CoinGecko (crypto).
    Devuelve dict symbol->lista de precios, alineados a misma longitud.
    """
    yf_syms, cg_syms = split_symbols(symbols)
    out: Dict[str, List[float]] = {}
    if yf_syms:
        out.update(fetch_yf_history(yf_syms, period="2y", interval="1d"))
    if cg_syms:
        out.update(fetch_cg_history(cg_syms, days=730, vs="usd"))
    out = align_min_length(out)
    # recorta a 'days' si hay de sobra
    if out:
        L = min(len(v) for v in out.values())
        K = min(L, days)
        out = {k: v[-K:] for k, v in out.items()}
    return out

def last_and_returns(series_dict: Dict[str, List[float]]) -> List[dict]:
    """
    A partir de series, computa último precio y retornos 1D/7D/30D aprox.
    """
    def _ret(pr: List[float], d: int) -> float:
        if len(pr) <= d: return 0.0
        return (pr[-1] / pr[-1 - d]) - 1.0

    quotes = []
    for sym, pr in series_dict.items():
        quotes.append({
            "symbol": sym,
            "last": float(pr[-1]),
            "ret1d": _ret(pr, 1),
            "ret7d": _ret(pr, 5),
            "ret30d": _ret(pr, 21),
        })
    return quotes
