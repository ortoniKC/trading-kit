import pandas as pd

def atr(bars: pd.DataFrame, period: int = 14) -> float:
    prev = bars["close"].shift(1)
    tr = pd.concat([bars["high"] - bars["low"],
                    (bars["high"] - prev).abs(),
                    (bars["low"] - prev).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def stop_for(side: str, entry: float, atr_value: float, mult: float) -> float:
    return entry - mult * atr_value if side == "bull" else entry + mult * atr_value

def path_outcome(bars: pd.DataFrame, side: str, entry_ts, stop: float, horizon_ts):
    """Walk the bars after entry. Stop is hit intrabar, so a stop can fire before the horizon.
    Returns the horizon close (for signal scoring) and the trade exit (stop or horizon)."""
    window = bars[(bars.index > entry_ts) & (bars.index <= horizon_ts)]
    if window.empty:
        return None
    horizon_close = float(window["close"].iloc[-1])
    exit_px, reason = horizon_close, "horizon"
    for _, bar in window.iterrows():
        hit = bar["low"] <= stop if side == "bull" else bar["high"] >= stop
        if hit:
            exit_px, reason = stop, "stop"
            break
    return {"horizon_close": horizon_close, "exit": exit_px, "reason": reason}
