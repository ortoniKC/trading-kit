from dataclasses import dataclass
from typing import Callable
from config import SEGMENTS, PRIOR_RATE, PRIOR_WEIGHT, MIN_EDGE, MARGIN

@dataclass
class Rule:
    id: str
    segment: str
    side: str        # "bull" or "bear"
    name: str
    test: Callable[[dict], bool]

RULES = [
    Rule("S1", "swing", "bull", "Trend up: SMA50 > SMA200 and close > SMA50",
         lambda f: f["sma_50"] > f["sma_200"] and f["close"] > f["sma_50"]),
    Rule("S2", "swing", "bear", "Trend down: SMA50 < SMA200 and close < SMA50",
         lambda f: f["sma_50"] < f["sma_200"] and f["close"] < f["sma_50"]),
    Rule("S3", "swing", "bear", "Overheated: RSI14 > 70", lambda f: f["rsi_14"] > 70),
    Rule("I1", "intraday", "bull", "Close above VWAP with volume > 1.5x 20-bar average",
         lambda f: f["close"] > f["vwap"] and f["vol_ratio"] > 1.5),
    Rule("I2", "intraday", "bear", "Close below VWAP with volume > 1.5x 20-bar average",
         lambda f: f["close"] < f["vwap"] and f["vol_ratio"] > 1.5),
    # I3 and I4 can fire together with I1, so the arbiter weighs them against each other.
    Rule("I3", "intraday", "bull", "Close above first-30-minute high",
         lambda f: f["close"] > f["first30_high"]),
    Rule("I4", "intraday", "bear", "Last 5-min bar has upper wick > 2x its body (rejection)",
         lambda f: f["wick_ratio"] > 2.0),
]
RULE_SIDE = {r.id: r.side for r in RULES}

def seed_rules(conn):
    for r in RULES:
        conn.execute("INSERT OR IGNORE INTO rules(id,segment,side,name) VALUES (?,?,?,?)",
                     (r.id, r.segment, r.side, r.name))
    conn.commit()

def fired_rules(segment: str, fields: dict) -> list:
    out = []
    for r in RULES:
        if r.segment != segment:
            continue
        try:
            if r.test(fields):
                out.append(r)
        except KeyError:
            pass  # missing field: the rule cannot fire
    return out

def stats(conn, rule_id: str):
    """Total trials and wins: backtest counts plus live outcomes, and status."""
    r = conn.execute("SELECT bt_wins, bt_trials, status FROM rules WHERE id=?",
                     (rule_id,)).fetchone()
    live = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(side_correct),0) w "
                        "FROM rule_outcomes WHERE rule_id=?", (rule_id,)).fetchone()
    return r["bt_wins"] + live["w"], r["bt_trials"] + live["n"], r["status"]

def edge(wins: int, trials: int) -> float:
    """Shrunk win rate minus 0.5, so small samples stay near zero."""
    return (wins + PRIOR_RATE * PRIOR_WEIGHT) / (trials + PRIOR_WEIGHT) - PRIOR_RATE

def best_side(conn, segment, fired, side):
    best = (0.0, None)
    min_trials = SEGMENTS[segment]["min_trials"]
    for r in fired:
        if r.side != side:
            continue
        w, n, status = stats(conn, r.id)
        if status != "active" or n < min_trials:
            continue
        e = edge(w, n)
        if e > best[0]:
            best = (e, r.id)
    return best

ACTION_MAP = {
    "intraday": {"bull": "BUY-READY-INTRADAY", "bear": "SHORT-READY-INTRADAY"},
    "swing": {"bull": "BUY-READY-SWING"},  # bear can only block a swing buy
}

def arbitrate(conn, segment: str, fired: list) -> dict:
    bull_e, bull_rule = best_side(conn, segment, fired, "bull")
    bear_e, bear_rule = best_side(conn, segment, fired, "bear")
    allow_short = SEGMENTS[segment]["allow_short"]
    base = {"bull_edge": round(bull_e, 4), "bear_edge": round(bear_e, 4)}

    if bull_e >= MIN_EDGE and bull_e - bear_e >= MARGIN:
        return {"action": ACTION_MAP[segment]["bull"], "side": "bull",
                "driving_rule": bull_rule, **base}
    if allow_short and bear_e >= MIN_EDGE and bear_e - bull_e >= MARGIN:
        return {"action": ACTION_MAP[segment]["bear"], "side": "bear",
                "driving_rule": bear_rule, **base}
    blocked = bear_rule if (not allow_short and bear_e >= MIN_EDGE) else None
    return {"action": "WAIT", "side": None, "driving_rule": None,
            "blocked_by": blocked, **base}
