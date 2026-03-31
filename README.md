# MarketLens — Mini Financial Data Platform

A full-stack mini financial data platform covering NSE/BSE stock data, REST APIs, and a visualization dashboard.


## Project Structure

marketlens/
├── main.py              # FastAPI backend (this file)
├── finplatform.html     # Standalone frontend dashboard
├── requirements.txt
├── Dockerfile
└── README.md


## Part 1 — Data Collection & Preparation

**Source**: `yfinance` (Yahoo Finance, NSE symbols with `.NS` suffix)  
**Fallback**: Seeded synthetic OHLCV data (reproducible, no API key needed)

### Transformations Applied

| Metric | Formula |
|---|---|
| Daily Return | `(Close − Open) / Open × 100` |
| 7-Day Moving Average | `rolling(7).mean()` on Close |
| 52W High / Low | `max/min` over last 252 trading days |
| Annualised Volatility | `std(log_returns) × √252 × 100` |
| Sentiment Index | `50 + momentum × 800`, clipped 0–100 |

### Custom Metrics (Creativity)
- **Volatility Score** — annualised vol with Low/Medium/High rating
- **Mock Sentiment Index** — momentum-based score per company
- **Pearson Correlation** — between any two company's 30-day price series (via `/compare`)


## Part 2 — REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/companies` | All companies with current price & change |
| `GET` | `/data/{symbol}?limit=30` | Last N days OHLCV + daily return + MA7 |
| `GET` | `/summary/{symbol}` | 52W high, low, avg, volatility |
| `GET` | `/compare?symbol1=INFY&symbol2=TCS` | Compare two stocks (return, correlation) |
| `GET` | `/volatility/{symbol}` | Custom volatility score & rating |
| `GET` | `/sentiment` | Mock sentiment index for all companies |
| `POST` | `/refresh/{symbol}` | Trigger fresh yfinance data pull |

**Swagger UI**: `http://localhost:8000/docs`  
**ReDoc**: `http://localhost:8000/redoc`


## Part 3 — Dashboard

Open `finplatform.html` in any browser. Features:
- Company sidebar with 30-day performance
- Closing price chart with 7D MA overlay
- **ML linear regression forecast** (next 7 days)
- Daily return bar chart (green/red)
- Built-in API Explorer — run all endpoints live
- Top Gainers / Losers leaderboard
- Volatility scorecards
- Mock Sentiment index bars
- Range filters: 30D / 90D / 180D / 1Y
- Compare mode: overlay two stocks on dual Y-axes


## Setup & Run

### Local (Python)

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Open finplatform.html in browser
```

### Docker

```bash
docker build -t marketlens .
docker run -p 8000:8000 marketlens
```


## requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.30.1
pandas==2.2.2
numpy==1.26.4
yfinance==0.2.40
httpx==0.27.0
```


## Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```


## Part 4 — Optional Add-ons Implemented

| Docker support      | ✅ Dockerfile included |
| ML forecast         | ✅ Linear regression (7-day) in dashboard |
| Async FastAPI       | ✅ All endpoints are `async def` |
| SQLite caching      | ✅ Data persisted in `marketlens.db` |
| Swagger / OpenAPI   | ✅ Auto-generated at `/docs` |
| Correlation metric  | ✅ Pearson via `/compare` |
| Sentiment index     | ✅ Custom momentum-based score |
| yfinance + fallback | ✅ Synthetic seeded data if offline |
