from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math, os, sqlite3

# ─── APP SETUP ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MarketLens API",
    description="NSE/BSE Financial Data Platform — REST API",
    version="1.0.0",
    contact={"name": "MarketLens", "url": "https://github.com/your-repo"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── COMPANIES ────────────────────────────────────────────────────────────────
COMPANIES = [
    {"sym": "RELIANCE.NS", "display": "RELIANCE", "name": "Reliance Industries", "sector": "Energy"},
    {"sym": "TCS.NS",      "display": "TCS",      "name": "Tata Consultancy Services", "sector": "IT"},
    {"sym": "INFY.NS",     "display": "INFY",     "name": "Infosys Ltd", "sector": "IT"},
    {"sym": "HDFCBANK.NS", "display": "HDFCBANK", "name": "HDFC Bank", "sector": "Banking"},
    {"sym": "WIPRO.NS",    "display": "WIPRO",    "name": "Wipro Ltd", "sector": "IT"},
    {"sym": "ITC.NS",      "display": "ITC",      "name": "ITC Ltd", "sector": "FMCG"},
    {"sym": "BAJFINANCE.NS","display":"BAJFINANCE","name": "Bajaj Finance", "sector": "NBFC"},
    {"sym": "HINDUNILVR.NS","display":"HINDUNILVR","name": "Hindustan Unilever", "sector": "FMCG"},
]

# ─── DATABASE (SQLite) ────────────────────────────────────────────────────────
DB_PATH = "marketlens.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_data (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol  TEXT NOT NULL,
            date    TEXT NOT NULL,
            open    REAL,
            high    REAL,
            low     REAL,
            close   REAL,
            volume  INTEGER,
            daily_return REAL,
            ma7     REAL,
            UNIQUE(symbol, date)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ─── DATA PIPELINE ────────────────────────────────────────────────────────────
def fetch_and_store(symbol: str, yf_sym: str, days: int = 365):
    """Fetch from yfinance, clean, compute metrics, store to SQLite."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period=f"{days}d")
        if df.empty:
            raise ValueError(f"No data for {yf_sym}")
    except Exception as e:
        # Fallback: generate synthetic data
        df = _synthetic_data(symbol, days)

    # ── Pandas cleaning ──────────────────────────────────────────────────────
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]

    # Rename yfinance columns
    rename = {"stock splits": "splits", "capital gains": "capgains"}
    df.rename(columns=rename, inplace=True)

    # Handle missing values
    df = df.dropna(subset=["close"])
    df["open"]  = df["open"].fillna(df["close"])
    df["high"]  = df["high"].fillna(df["close"])
    df["low"]   = df["low"].fillna(df["close"])
    df["volume"] = df["volume"].fillna(0).astype(int)

    # Parse dates
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # ── Calculated metrics ───────────────────────────────────────────────────
    df["daily_return"] = ((df["close"] - df["open"]) / df["open"] * 100).round(4)
    df["ma7"] = df["close"].rolling(window=7, min_periods=1).mean().round(2)

    # ── Store to DB ──────────────────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    for _, row in df.iterrows():
        conn.execute("""
            INSERT OR REPLACE INTO stock_data
            (symbol, date, open, high, low, close, volume, daily_return, ma7)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (symbol, row["date"], round(float(row["open"]),2),
              round(float(row["high"]),2), round(float(row["low"]),2),
              round(float(row["close"]),2), int(row["volume"]),
              float(row["daily_return"]), float(row["ma7"])))
    conn.commit()
    conn.close()
    return len(df)


def _synthetic_data(symbol: str, days: int = 365) -> pd.DataFrame:
    """Reproducible synthetic OHLCV data (fallback when yfinance unavailable)."""
    rng = np.random.default_rng(sum(ord(c) for c in symbol))
    bases = {"RELIANCE": 2850, "TCS": 3960, "INFY": 1780, "HDFCBANK": 1680,
             "WIPRO": 520, "ITC": 465, "BAJFINANCE": 7100, "HINDUNILVR": 2400}
    base = bases.get(symbol, 1000)
    vols = {"RELIANCE": 0.018, "TCS": 0.013, "INFY": 0.016, "HDFCBANK": 0.015,
            "WIPRO": 0.019, "ITC": 0.012, "BAJFINANCE": 0.022, "HINDUNILVR": 0.011}
    vol = vols.get(symbol, 0.015)

    dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    price = base
    now = datetime.now()
    for i in range(days - 1, -1, -1):
        d = now - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        shock = rng.normal(0.0003, vol)
        o = price
        c = price * (1 + shock)
        h = max(o, c) * (1 + rng.uniform(0, 0.008))
        l = min(o, c) * (1 - rng.uniform(0, 0.008))
        dates.append(d);  opens.append(round(o, 2));  highs.append(round(h, 2))
        lows.append(round(l, 2));  closes.append(round(c, 2))
        volumes.append(int(rng.uniform(1e6, 6e6)))
        price = c

    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                          "low": lows, "close": closes, "volume": volumes})


def get_data_from_db(symbol: str, limit: int = None) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM stock_data WHERE symbol=? ORDER BY date DESC"
    if limit:
        q += f" LIMIT {limit}"
    rows = conn.execute(q, (symbol,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── HELPER: ensure data exists ───────────────────────────────────────────────
def ensure_data(symbol: str):
    rows = get_data_from_db(symbol, limit=1)
    if not rows:
        comp = next((c for c in COMPANIES if c["display"] == symbol), None)
        if not comp:
            raise HTTPException(404, f"Symbol '{symbol}' not found")
        fetch_and_store(symbol, comp["sym"])


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.get("/companies", tags=["Market Data"],
         summary="List all available companies")
async def get_companies():
    """
    Returns a list of all companies in the platform with their current price.
    """
    result = []
    for comp in COMPANIES:
        sym = comp["display"]
        ensure_data(sym)
        rows = get_data_from_db(sym, limit=2)
        current = rows[0]["close"] if rows else None
        prev    = rows[1]["close"] if len(rows) > 1 else current
        change  = round((current - prev) / prev * 100, 2) if (current and prev) else 0
        result.append({
            "symbol":        sym,
            "name":          comp["name"],
            "sector":        comp["sector"],
            "current_price": current,
            "change_pct":    change,
        })
    return {"status": "ok", "count": len(result), "data": result}


@app.get("/data/{symbol}", tags=["Market Data"],
         summary="Get historical stock data (last N days)")
async def get_stock_data(
    symbol: str,
    limit: int = Query(default=30, ge=1, le=365, description="Number of trading days"),
):
    """
    Returns OHLCV data with calculated metrics:
    - **daily_return**: (Close - Open) / Open × 100
    - **ma7**: 7-day moving average of close price
    """
    symbol = symbol.upper()
    ensure_data(symbol)
    rows = get_data_from_db(symbol, limit=limit)
    if not rows:
        raise HTTPException(404, "No data found")
    return {
        "status": "ok",
        "symbol": symbol,
        "count":  len(rows),
        "data":   rows,
    }


@app.get("/summary/{symbol}", tags=["Market Data"],
         summary="52-week summary: high, low, avg close")
async def get_summary(symbol: str):
    """
    Returns 52-week statistics for the given symbol:
    - 52W High / Low
    - Average Close
    - Distance from high
    - Annualised volatility
    """
    symbol = symbol.upper()
    ensure_data(symbol)
    rows = get_data_from_db(symbol, limit=252)  # ~1 trading year
    if not rows:
        raise HTTPException(404, "No data found")

    closes = [r["close"] for r in rows]
    high52  = max(closes)
    low52   = min(closes)
    avg52   = round(sum(closes) / len(closes), 2)
    returns = [r["daily_return"] / 100 for r in rows]
    ann_vol = round(np.std(returns) * math.sqrt(252) * 100, 2)
    current = closes[0]

    return {
        "status":          "ok",
        "symbol":          symbol,
        "week52_high":     round(high52, 2),
        "week52_low":      round(low52, 2),
        "avg_close_52w":   avg52,
        "current_price":   round(current, 2),
        "dist_from_high_pct": round((current - high52) / high52 * 100, 2),
        "annualized_vol_pct": ann_vol,
    }


@app.get("/compare", tags=["Market Data"],
         summary="Compare two stocks' performance")
async def compare_stocks(
    symbol1: str = Query(..., description="First stock symbol, e.g. INFY"),
    symbol2: str = Query(..., description="Second stock symbol, e.g. TCS"),
    days:    int = Query(default=30, ge=7, le=365),
):
    """
    Bonus endpoint: compare two stocks.

    Returns:
    - Absolute & percentage return for each
    - **Pearson correlation** of closing prices (custom metric)
    - Winner (higher return)
    """
    s1, s2 = symbol1.upper(), symbol2.upper()
    if s1 == s2:
        raise HTTPException(400, "symbol1 and symbol2 must be different")

    for sym in [s1, s2]:
        ensure_data(sym)

    r1 = get_data_from_db(s1, limit=days)
    r2 = get_data_from_db(s2, limit=days)
    n  = min(len(r1), len(r2))

    c1 = [r["close"] for r in r1[:n]]
    c2 = [r["close"] for r in r2[:n]]

    ret1 = round((c1[0] - c1[-1]) / c1[-1] * 100, 2)
    ret2 = round((c2[0] - c2[-1]) / c2[-1] * 100, 2)

    # Pearson correlation
    mu1, mu2 = np.mean(c1), np.mean(c2)
    cov = np.mean([(c1[i]-mu1)*(c2[i]-mu2) for i in range(n)])
    corr = round(cov / (np.std(c1) * np.std(c2)), 4)

    return {
        "status":    "ok",
        "symbol1":   s1,
        "symbol2":   s2,
        "days":      n,
        "return_pct": {s1: ret1, s2: ret2},
        "correlation_pearson": corr,
        "correlation_label":   ("Strong positive" if corr > 0.7
                                else "Moderate" if corr > 0.3
                                else "Weak / negative"),
        "winner":    s1 if ret1 > ret2 else s2,
    }


@app.get("/volatility/{symbol}", tags=["Custom Metrics"],
         summary="Custom volatility score")
async def get_volatility(symbol: str, days: int = Query(default=30, ge=7, le=252)):
    """
    Custom metric: volatility score based on annualised standard deviation
    of daily log returns over the specified window.

    Rating: Low < 18% < Medium < 25% < High
    """
    symbol = symbol.upper()
    ensure_data(symbol)
    rows = get_data_from_db(symbol, limit=days)
    if len(rows) < 5:
        raise HTTPException(422, "Not enough data to compute volatility")

    log_returns = [math.log(rows[i]["close"] / rows[i+1]["close"])
                   for i in range(len(rows)-1)]
    ann_vol = round(np.std(log_returns) * math.sqrt(252) * 100, 2)
    rating = "Low" if ann_vol < 18 else "Medium" if ann_vol < 25 else "High"

    return {
        "status":            "ok",
        "symbol":            symbol,
        "days":              days,
        "daily_std_pct":     round(np.std(log_returns) * 100, 4),
        "annualized_vol_pct": ann_vol,
        "rating":            rating,
    }


@app.get("/sentiment", tags=["Custom Metrics"],
         summary="Mock sentiment index for all companies")
async def get_sentiment():
    """
    Custom metric: a mock 'sentiment index' derived from 7-day price momentum.

    Score 0–100: >60 Bullish, <40 Bearish, else Neutral.
    In a real system this would incorporate news NLP / social signals.
    """
    result = []
    for comp in COMPANIES:
        sym = comp["display"]
        ensure_data(sym)
        rows = get_data_from_db(sym, limit=7)
        if len(rows) < 2:
            continue
        ret = (rows[0]["close"] - rows[-1]["close"]) / rows[-1]["close"]
        score = min(100, max(0, round(50 + ret * 800)))
        label = "Bullish" if score > 60 else "Bearish" if score < 40 else "Neutral"
        result.append({"symbol": sym, "sentiment_score": score, "label": label})

    return {"status": "ok", "generated_at": datetime.now().isoformat(), "index": result}


@app.post("/refresh/{symbol}", tags=["Admin"],
          summary="Refresh data from yfinance")
async def refresh_data(symbol: str, days: int = 365):
    """Trigger a fresh data pull for the given symbol (admin use)."""
    symbol = symbol.upper()
    comp = next((c for c in COMPANIES if c["display"] == symbol), None)
    if not comp:
        raise HTTPException(404, f"Symbol '{symbol}' not found")
    n = fetch_and_store(symbol, comp["sym"], days)
    return {"status": "ok", "symbol": symbol, "rows_stored": n}


@app.get("/health", tags=["Admin"], include_in_schema=False)
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
