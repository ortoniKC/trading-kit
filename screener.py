"""Equity screener: today's movers or most-traded NSE stocks from Kite quotes."""
import time, pandas as pd

MIN_PRICE = 50
MIN_TURNOVER_CR = 10
TOP_N = 25

def run(mode: str, adapter) -> pd.DataFrame:
    keys = [f"NSE:{s}" for s in sorted(adapter.equity_symbols())]
    quotes = {}
    for i in range(0, len(keys), 500):
        quotes.update(adapter.kite.quote(keys[i:i + 500]))
        time.sleep(1.1)  # stay under the quote rate limit
    rows = []
    for key, q in quotes.items():
        last, prev = q["last_price"], q["ohlc"]["close"]
        if not prev or last < MIN_PRICE:
            continue
        turnover_cr = last * q["volume"] / 1e7
        if turnover_cr < MIN_TURNOVER_CR:
            continue
        rows.append({"symbol": key.split(":")[1], "last": last,
                     "change_pct": round((last / prev - 1) * 100, 2),
                     "turnover_cr": round(turnover_cr, 1)})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    col = "change_pct" if mode == "movers" else "turnover_cr"
    return df.sort_values(col, ascending=False).head(TOP_N).reset_index(drop=True)
