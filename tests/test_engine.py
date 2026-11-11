import os, sys, json, tempfile, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
import store, envfile
from config import parse_json
from engine import (analyze, intraday_fields, swing_fields, verify_claims,
                    load_watchlist, within_window)
from rules import seed_rules, stats
from indicators import rsi, atr, vwap, upper_wick_ratio, first_30_high

IST = store.IST
passed = failed = 0
def check(name, cond):
    global passed, failed
    if cond: passed += 1; print("PASS", name)
    else: failed += 1; print("FAIL", name)

DAY = dt.date(2026, 11, 11)
AT_10 = dt.datetime(2026, 11, 11, 10, 0, tzinfo=IST)
AT_1520 = dt.datetime(2026, 11, 11, 15, 20, tzinfo=IST)
AT_1600 = dt.datetime(2026, 11, 11, 16, 0, tzinfo=IST)
AT_1100 = dt.datetime(2026, 11, 11, 11, 0, tzinfo=IST)

class FakeAdapter:
    def __init__(self, bars, price):
        self.bars, self.price = bars, price
    def get_historical(self, symbol, interval, days):
        return self.bars
    def get_quote(self, symbol):
        return {"last_price": self.price}
    def equity_symbols(self):
        return {"RELIANCE", "INFY"}

def intraday_bars():
    idx = pd.date_range(f"{DAY} 09:15", periods=30, freq="5min", tz=IST)
    close = np.linspace(100, 101, 30)
    open_ = np.concatenate([[100.0], close[:-1]])
    vol = np.full(30, 1000.0); vol[-1] = 3000.0
    return pd.DataFrame({"open": open_, "high": close + 0.2, "low": close - 0.2,
                         "close": close, "volume": vol}, index=idx)

def swing_bars(n=260):
    idx = pd.date_range("2025-06-01", periods=n, freq="B", tz=IST)
    close = np.linspace(50, 150, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1e6}, index=idx)

def fake_llm(system, user, max_tokens=700):
    ctx = json.loads(user) if user.startswith("{") else {}
    if "for the BULL side" in system:
        return json.dumps({"claims": [{"text": "above vwap", "field": "close",
                                       "value": ctx["fields"]["close"]}], "weakener": "x"})
    if "for the BEAR side" in system:
        field = "wick_ratio" if "wick_ratio" in ctx["fields"] else "rsi_14"
        return json.dumps({"claims": [{"text": "bear point", "field": field,
                                       "value": ctx["fields"][field]}], "weakener": "x"})
    return json.dumps({"decisive_claims_verified": True, "veto": False, "veto_reason": ""})

def conn_with(stats_map):
    c = store.connect(":memory:"); seed_rules(c)
    for rid, (w, n) in stats_map.items():
        c.execute("UPDATE rules SET bt_wins=?, bt_trials=? WHERE id=?", (w, n, rid))
    c.commit(); return c

# Indicators
check("sma of rising series", abs(rsi(pd.Series(np.arange(30.0))).iloc[-1] - 100) < 1e-6)
b = intraday_bars()
check("atr is positive and finite", atr(b) > 0 and np.isfinite(atr(b)))
check("vwap lies within the bar range", b["low"].min() <= vwap(b).iloc[-1] <= b["high"].max())
check("upper wick ratio finite for normal bar", np.isfinite(upper_wick_ratio(b.iloc[-1])))
check("first_30_high uses only the first 30 minutes",
      first_30_high(b) < b["high"].max())

# Claim verification
f = {"close": 101.0, "wick_ratio": 6.0}
check("matching claims verify", verify_claims([{"field": "close", "value": 101.0}], f) == (1, 1))
check("claim within 1% tolerance verifies", verify_claims([{"field": "close", "value": 101.5}], f) == (1, 1))
check("claim outside tolerance fails", verify_claims([{"field": "close", "value": 50}], f) == (0, 1))
check("claim on unknown field fails", verify_claims([{"field": "pe", "value": 20}], f) == (0, 1))

# Time windows
check("intraday window open at 10:00", within_window("intraday", AT_10))
check("intraday window closed at 15:20", not within_window("intraday", AT_1520))
check("swing window closed at 11:00", not within_window("swing", AT_1100))
check("swing window open at 16:00", within_window("swing", AT_1600))

# Intraday end-to-end: bull rule with strong history -> BUY-READY-INTRADAY, no blocks
conn = conn_with({"I1": (40, 50)})
res = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=fake_llm, at=AT_10)
check("intraday bull yields BUY-READY-INTRADAY", res["action"] == "BUY-READY-INTRADAY")
check("no blocks when claims verify", res.get("blocks") == [])
check("decision logged", conn.execute("SELECT COUNT(*) n FROM decisions").fetchone()["n"] == 1)
check("stop is below entry for a long", res["stop_level"] < res["entry"])

# Fail closed: a bull claim with a wrong value blocks the trade
def lying_llm(system, user, max_tokens=700):
    if "for the BULL side" in system:
        return json.dumps({"claims": [{"text": "x", "field": "close", "value": 50}], "weakener": ""})
    return fake_llm(system, user)
conn = conn_with({"I1": (40, 50)})
res = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=lying_llm, at=AT_10)
check("mismatched claim blocks the trade", res["action"] == "WAIT" and res["blocks"])

# Judge veto blocks the trade
def veto_llm(system, user, max_tokens=700):
    if "you do not decide" in system:
        return json.dumps({"decisive_claims_verified": True, "veto": True,
                           "veto_reason": "matches past mistake"})
    return fake_llm(system, user)
conn = conn_with({"I1": (40, 50)})
res = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=veto_llm, at=AT_10)
check("judge veto blocks the trade", res["action"] == "WAIT" and any("veto" in x for x in res["blocks"]))

# Judge that omits the verification flag blocks the trade (default False)
def silent_judge(system, user, max_tokens=700):
    if "you do not decide" in system:
        return json.dumps({"veto": False})
    return fake_llm(system, user)
conn = conn_with({"I1": (40, 50)})
res = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=silent_judge, at=AT_10)
check("missing verification flag blocks", res["action"] == "WAIT")

# Untrained rules: WAIT without calling the debate at all
calls = []
def counting_llm(system, user, max_tokens=700):
    calls.append(1); return fake_llm(system, user)
conn = conn_with({})
res = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=counting_llm, at=AT_10)
check("untrained rules return WAIT with no LLM calls", res["action"] == "WAIT" and calls == [])

# Open-position guard
conn = conn_with({"I1": (40, 50)})
analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=fake_llm, at=AT_10)
res2 = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=fake_llm, at=AT_10)
check("second signal blocked while first is open", res2["action"] == "WAIT" and "open" in res2["reason"])

# Intraday after 15:15: no new entries
res = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn_with({"I1": (40, 50)}),
              llm=fake_llm, at=AT_1520)
check("no intraday entry after 15:15", res["action"] == "WAIT" and "15:15" in res["reason"])

# Preview outside the window is not logged
conn = conn_with({"I1": (40, 50)})
res = analyze("RELIANCE", "intraday", FakeAdapter(b, 101.0), conn=conn, llm=fake_llm, at=dt.datetime(2026,11,11,9,20,tzinfo=IST))
check("preview is flagged and not logged",
      res.get("preview") is True and conn.execute("SELECT COUNT(*) n FROM decisions").fetchone()["n"] == 0)

# Swing: rising history -> trend bull buys, RSI overheated bear only blocks
sw = swing_bars()
check("swing fields computed from 260 bars", swing_fields(FakeAdapter(sw, 150), "RELIANCE") is not None)
conn = conn_with({"S1": (40, 50)})
res = analyze("RELIANCE", "swing", FakeAdapter(sw, 150), conn=conn, llm=fake_llm, at=AT_1600)
check("swing bull yields BUY-READY-SWING", res["action"] == "BUY-READY-SWING")
check("swing never returns a short", "SHORT" not in res["action"])

# Watchlist loader ignores _note and normalizes case
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "wl.json")
    json.dump({"_note": "x", "intraday": [" reliance "], "swing": ["tcs"]}, open(p, "w"))
    wl = load_watchlist(p)
    check("watchlist normalizes symbols and ignores _keys",
          wl == {"intraday": ["RELIANCE"], "swing": ["TCS"]})

# .env writer updates in place and sets 600 permissions
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, ".env")
    open(p, "w").write("KITE_ACCESS_TOKEN=old\nOTHER=1\n")
    envfile.set_key("KITE_ACCESS_TOKEN", "new", p)
    text = open(p).read()
    check(".env key updated in place", "KITE_ACCESS_TOKEN=new" in text and "OTHER=1" in text and "old" not in text)
    check(".env is owner-only", oct(os.stat(p).st_mode)[-3:] == "600")

check("parse_json tolerates surrounding text", parse_json('Sure {"a": 1} ok')["a"] == 1)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
