"""Pure functions on pandas data. Every value is measured from observed bars."""
import pandas as pd

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).rolling(period).mean()
    loss = (-d.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)

def atr(bars: pd.DataFrame, period: int = 14) -> float:
    prev = bars["close"].shift(1)
    tr = pd.concat([bars["high"] - bars["low"],
                    (bars["high"] - prev).abs(),
                    (bars["low"] - prev).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def vwap(bars: pd.DataFrame) -> pd.Series:
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3
    return (tp * bars["volume"]).cumsum() / bars["volume"].cumsum()

def vol_ratio(bars: pd.DataFrame, n: int = 20) -> float:
    """Last bar's volume divided by the average of the n bars before it."""
    return float(bars["volume"].iloc[-1] / bars["volume"].iloc[-(n + 1):-1].mean())

def first_30_high(today: pd.DataFrame) -> float:
    return float(today.between_time("09:15", "09:44")["high"].max())

def upper_wick_ratio(bar: pd.Series) -> float:
    body = abs(bar["close"] - bar["open"])
    upper = bar["high"] - max(bar["open"], bar["close"])
    if body == 0:
        return float("inf") if upper > 0 else 0.0
    return float(upper / body)
