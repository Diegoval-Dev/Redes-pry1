# invest_mcp/lib/data_live.py
from __future__ import annotations
import os, json, time, hashlib, requests, sys
from typing import Dict, List, Tuple
import pandas as pd
import yfinance as yf

DEBUG = os.environ.get("INVEST_MCP_DEBUG", "0") == "1"

def _d(msg: str):
    if DEBUG:
        print(f"[data_live] {msg}", file=sys.stderr)

# -------- Cache simple (archivos JSON) --------
CACHE_DIR = os.environ.get("INVEST_MCP_CACHE_DIR", os.path.join(".cache","invest_mcp"))
os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_path(key: str) -> str:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.json")

def cache_load(key: str, ttl_seconds: int):
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

def cache_save(key: str, obj):
    path = _cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    except Exception:
        pass

# -------- Universo / mapeos --------
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    # agrega más si quieres: "SOL":"solana", etc.
}

def split_symbols(symbols: List[str]) -> Tuple[List[str], List[str]]:
    yf_list, cg_list = [], []
    for s in symbols:
        if s in COINGECKO_IDS: cg_list.append(s)
        else: yf_list.append(s)
    return yf_list, cg_list

# -------- Base y auth CoinGecko --------
def _cg_base_and_auth() -> Tuple[str, dict, dict, str]:
    """
    Retorna (base_url, headers, query_params, mode_str).
    - Si hay COINGECKO_PRO_API_KEY => usa pro-api + x_cg_pro_api_key
    - Si no, usa público + demo si hay COINGECKO_API_KEY (header y query)
    """
    pro_key = os.environ.get("COINGECKO_PRO_API_KEY", "").strip()
    demo_key = os.environ.get("COINGECKO_API_KEY", "").strip()

    if pro_key:
        base = "https://pro-api.coingecko.com/api/v3"
        headers = {"accept": "application/json"}
        q = {"x_cg_pro_api_key": pro_key}
        _d("Auth mode: PRO (pro-api.coingecko.com)")
        return base, headers, q, "pro"

    base = "https://api.coingecko.com/api/v3"
    headers = {"accept": "application/json"}
    q = {}
    if demo_key:
        headers["x-cg-demo-api-key"] = demo_key
        q["x_cg_demo_api_key"] = demo_key
        _d("Auth mode: DEMO (api.coingecko.com) con demo key")
    else:
        _d("Auth mode: PUBLIC (api.coingecko.com) sin key")
    return base, headers, q, "pub"

# -------- Yahoo Finance (SPY/GLD/etc.) --------
def fetch_yf_history(tickers: List[str], period: str = "2y", interval: str = "1d") -> Dict[str, List[float]]:
    if not tickers: return {}
    key = f"yf_hist:{','.join(sorted(tickers))}:{period}:{interval}"
    cached = cache_load(key, ttl_seconds=600)
    if cached is not None:
        return cached
    _d(f"yfinance download tickers={tickers} period={period} interval={interval}")
    df = yf.download(tickers=tickers, period=period, interval=interval, auto_adjust=True, progress=False)
    out: Dict[str, List[float]] = {}
    if isinstance(df.columns, pd.MultiIndex):
        col = "Close" if "Close" in df.columns.levels[0] else ("Adj Close" if "Adj Close" in df.columns.levels[0] else None)
        if col:
            sub = df[col]
            for t in sub.columns:
                ser = sub[t].dropna()
                if len(ser) >= 2:
                    out[str(t)] = [float(x) for x in ser.tolist()]
    else:
        col = "Close" if "Close" in df.columns else ("Adj Close" if "Adj Close" in df.columns else None)
        if col:
            ser = df[col].dropna()
            if len(ser) >= 2:
                out[str(tickers[0])] = [float(x) for x in ser.tolist()]
    cache_save(key, out)
    return out

# -------- CoinGecko: simple/price (spot) --------
def fetch_cg_simple_price(symbols: List[str], vs: str = "usd") -> Dict[str, float]:
    if not symbols: return {}
    ids = [COINGECKO_IDS[s] for s in symbols if s in COINGECKO_IDS]
    if not ids: return {}

    base, headers, q, mode = _cg_base_and_auth()
    key = f"cg_simple:{','.join(sorted(ids))}:{vs}:{mode}"
    cached = cache_load(key, ttl_seconds=30)
    if cached is not None:
        return cached

    url = f"{base}/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": vs, **q}
    _d(f"GET {url} {params}")
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        _d(f"-> status={r.status_code}")
        r.raise_for_status()
        data = r.json()
        inv = {v: k for k, v in COINGECKO_IDS.items()}
        out: Dict[str, float] = {}
        for cg_id, obj in data.items():
            sym = inv.get(cg_id)
            if not sym: continue
            price = obj.get(vs)
            if isinstance(price, (int, float)):
                out[sym] = float(price)
        cache_save(key, out)
        return out
    except Exception as e:
        _d(f"simple/price error: {e}")
        return {}

# -------- CoinGecko: market_chart (histórico) --------
def fetch_cg_history(symbols: List[str], days: int = 365, vs: str = "usd") -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    base, headers, q, mode = _cg_base_and_auth()
    for sym in symbols:
        cg_id = COINGECKO_IDS.get(sym)
        if not cg_id: continue
        key = f"cg_hist:{cg_id}:{days}:{vs}:{mode}"
        cached = cache_load(key, ttl_seconds=600)
        if cached is not None:
            out[sym] = cached
            continue
        url = f"{base}/coins/{cg_id}/market_chart"
        params = {"vs_currency": vs, "days": days, **q}
        _d(f"GET {url} {params}")
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            _d(f"-> status={r.status_code}")
            r.raise_for_status()
            data = r.json()
            prices = [float(p[1]) for p in data.get("prices", []) if p and p[1] is not None]
            if len(prices) >= 2:
                out[sym] = prices
                cache_save(key, prices)
        except Exception as e:
            _d(f"market_chart error {sym}: {e}")
            continue
    return out

# -------- Utilidades --------
def align_min_length(series_dict: Dict[str, List[float]]) -> Dict[str, List[float]]:
    if not series_dict: return {}
    L = min(len(v) for v in series_dict.values())
    if L < 2: return {}
    return {k: v[-L:] for k, v in series_dict.items()}

def get_history(symbols: List[str], days: int = 252) -> Dict[str, List[float]]:
    yf_syms, cg_syms = split_symbols(symbols)
    out: Dict[str, List[float]] = {}

    # yfinance
    try:
        if yf_syms:
            out.update(fetch_yf_history(yf_syms, period="2y", interval="1d"))
    except Exception as e:
        _d(f"yfinance error: {e}")

    # CoinGecko
    try:
        if cg_syms:
            out.update(fetch_cg_history(cg_syms, days=730, vs="usd"))
    except Exception as e:
        _d(f"cg error: {e}")

    out = align_min_length(out)
    if not out: return {}
    L = min(len(v) for v in out.values())
    K = min(L, days)
    return {k: v[-K:] for k, v in out.items()}

def last_and_returns(series_dict: Dict[str, List[float]]) -> List[dict]:
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

    cg_syms = [s for s in series_dict.keys() if s in COINGECKO_IDS]
    if cg_syms:
        spot = fetch_cg_simple_price(cg_syms, vs="usd")
        if spot:
            for q in quotes:
                if q["symbol"] in spot:
                    q["last"] = float(spot[q["symbol"]])
    return quotes
