import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, datetime as dt
import numpy as np, pandas as pd
import store, review, rules, risk
from config import parse_json
from rules import edge
from rules import RULES, fired_rules, arbitrate, seed_rules, stats

IST = store.IST
passed = failed = 0
def check(name, cond):
    global passed, failed
    if cond: passed += 1; print("PASS", name)
    else: failed += 1; print("FAIL", name)

def fresh():
    c = store.connect(":memory:"); seed_rules(c); return c

def set_stats(c, rid, wins, trials):
    c.execute("UPDATE rules SET bt_wins=?, bt_trials=? WHERE id=?", (wins, trials, rid)); c.commit()

# 1. Edge: no data is zero, large sample with high win rate is positive, small sample is shrunk
check("edge zero with no trials", abs(edge(0, 0)) < 1e-9)
check("edge positive for 40/50", edge(40, 50) > 0.2)
check("small sample shrunk: 5/5 weaker than 50/50", edge(5, 5) < edge(50, 50))

# 2. Untrained rules -> WAIT (safe default)
c = fresh()
fields = {"close": 110, "vwap": 100, "vol_ratio": 2.0, "sma_50": 105, "sma_200": 100, "rsi_14": 55}
arb = arbitrate(c, "intraday", fired_rules("intraday", fields))
check("untrained rules produce WAIT", arb["action"] == "WAIT")

# 3. Bull overtakes bear -> BUY-READY-INTRADAY
c = fresh(); set_stats(c, "I1", 40, 50); set_stats(c, "I2", 22, 50)
arb = arbitrate(c, "intraday", fired_rules("intraday", fields))
check("strong bull beats weaker bear", arb["action"] == "BUY-READY-INTRADAY" and arb["driving_rule"] == "I1")

# 4. Bear overtakes bull -> SHORT-READY-INTRADAY
c = fresh(); set_stats(c, "I1", 25, 50); set_stats(c, "I2", 40, 50)
bear_fields = {"close": 90, "vwap": 100, "vol_ratio": 2.0, "first30_high": 120, "wick_ratio": 0.5}
arb = arbitrate(c, "intraday", fired_rules("intraday", bear_fields))
check("strong bear produces short in intraday", arb["action"] == "SHORT-READY-INTRADAY")

# 5. Both sides similar -> WAIT (margin protects against coin-flip flips)
c = fresh(); set_stats(c, "I1", 30, 50); set_stats(c, "I4", 29, 50)
both = dict(fields, first30_high=120, wick_ratio=3.0)  # I1 bull and I4 bear fire together
arb = arbitrate(c, "intraday", fired_rules("intraday", both))
check("near-tie between co-firing bull and bear gives WAIT", arb["action"] == "WAIT")

# 5b. Bear rule with stronger edge overtakes a co-firing bull on the same bar
c = fresh(); set_stats(c, "I1", 25, 50); set_stats(c, "I4", 42, 50)
arb = arbitrate(c, "intraday", fired_rules("intraday", both))
check("co-firing bear overtakes bull -> SHORT-READY", arb["action"] == "SHORT-READY-INTRADAY" and arb["driving_rule"] == "I4")

# 5c. Bull overtakes co-firing bear on the same bar
c = fresh(); set_stats(c, "I1", 42, 50); set_stats(c, "I4", 25, 50)
arb = arbitrate(c, "intraday", fired_rules("intraday", both))
check("co-firing bull overtakes bear -> BUY-READY", arb["action"] == "BUY-READY-INTRADAY" and arb["driving_rule"] == "I1")

# 6. Swing never shorts: strong bear blocks but never creates a SELL
sf = {"close": 90, "sma_50": 95, "sma_200": 100, "rsi_14": 75}
c = fresh(); set_stats(c, "S2", 40, 50)
arb = arbitrate(c, "swing", fired_rules("swing", sf))
check("swing bear never creates a short", arb["action"] == "WAIT" and arb["blocked_by"] == "S2")

# 7. Swing bull with no bear -> BUY-READY-SWING
uf = {"close": 110, "sma_50": 105, "sma_200": 100, "rsi_14": 55}
c = fresh(); set_stats(c, "S1", 40, 50)
arb = arbitrate(c, "swing", fired_rules("swing", uf))
check("swing bull gives BUY-READY-SWING", arb["action"] == "BUY-READY-SWING")

# 8. Stop logic and path outcome
idx = pd.date_range("2026-11-11 09:15", periods=6, freq="5min", tz=IST)
bars = pd.DataFrame({"open": 100, "high": [101,101,103,101,101,101],
                     "low": [99,99,99,94,99,99], "close": 100.0}, index=idx)
entry_ts = idx[0] - pd.Timedelta("1min")
out = risk.path_outcome(bars, "bull", entry_ts, 95.0, idx[-1])
check("long stop hit intrabar exits at stop", out["reason"] == "stop" and out["exit"] == 95.0)
out = risk.path_outcome(bars, "bear", entry_ts, 102.5, idx[-1])
check("short stop hit when high reaches stop", out["reason"] == "stop" and out["exit"] == 102.5)
out = risk.path_outcome(bars, "bull", entry_ts, 80.0, idx[-1])
check("no stop: exits at horizon close", out["reason"] == "horizon")
check("stop_for bull is below entry", risk.stop_for("bull", 100, 2, 1.5) == 97.0)
check("stop_for bear is above entry", risk.stop_for("bear", 100, 2, 1.5) == 103.0)

# 9. Evaluate end-to-end with a fake adapter
class FakeAdapter:
    def __init__(self, bars): self.bars = bars
    def get_historical(self, symbol, interval, days, exchange="NSE"): return self.bars

c = fresh()
ts = "2026-11-11T10:00:00+05:30"; horizon = "2026-11-11T15:15:00+05:30"
fields = {"close": 100, "entry_price": 100, "atr_14": 1.0, "vwap": 99, "vol_ratio": 2}
c.execute("INSERT INTO decisions(segment,symbol,ts,price,fields,fired,action,driving_rule,judge,horizon_end)"
          " VALUES ('intraday','TEST',?,100,?,?,'BUY-READY-INTRADAY','I1',NULL,?)",
          (ts, json.dumps(fields), json.dumps(["I1"]), horizon))
c.commit()
bidx = pd.date_range("2026-11-11 10:05", periods=40, freq="5min", tz=IST)
rising = pd.DataFrame({"open":100,"high":104,"low":99.5,"close":np.linspace(100,103,40)}, index=bidx)
review.evaluate(c, FakeAdapter(rising))
o = c.execute("SELECT * FROM outcomes").fetchone()
check("evaluate records a winning long outcome", o is not None and o["correct"] == 1)
check("rule outcome recorded for fired rule", c.execute("SELECT COUNT(*) n FROM rule_outcomes").fetchone()["n"] == 1)
check("decision marked evaluated", c.execute("SELECT evaluated FROM decisions").fetchone()["evaluated"] == 1)

# 10. Losing long gets a post-mortem lesson (LLM stubbed)
c = fresh()
c.execute("INSERT INTO decisions(segment,symbol,ts,price,fields,fired,action,driving_rule,judge,horizon_end)"
          " VALUES ('intraday','TEST',?,100,?,?,'BUY-READY-INTRADAY','I1',NULL,?)",
          (ts, json.dumps(fields), json.dumps(["I1"]), horizon)); c.commit()
falling = pd.DataFrame({"open":100,"high":100.5,"low":90,"close":np.linspace(100,92,40)}, index=bidx)
review.ask = lambda s, u, max_tokens=400: '{"failure_type":"stop_hit","lesson":"Stop-out on VWAP long with low volume follow-through","guard_candidate":"I1"}'
review.evaluate(c, FakeAdapter(falling))
check("losing trade triggers lesson", c.execute("SELECT COUNT(*) n FROM lessons").fetchone()["n"] == 1)
check("lesson is retrieved for matching rules", len(review.lessons_for(c, "intraday", ["I1"])) == 1)
check("lesson not retrieved for unrelated rules", review.lessons_for(c, "intraday", ["I2"]) == [])

# 11. Stop hit is recorded as the exit reason
c = fresh()
c.execute("INSERT INTO decisions(segment,symbol,ts,price,fields,fired,action,driving_rule,judge,horizon_end)"
          " VALUES ('intraday','TEST',?,100,?,?,'BUY-READY-INTRADAY','I1',NULL,?)",
          (ts, json.dumps(fields), json.dumps(["I1"]), horizon)); c.commit()
review.ask = lambda *a, **k: '{"failure_type":"stop_hit","lesson":"x","guard_candidate":null}'
review.evaluate(c, FakeAdapter(falling))
check("stop exit reason stored", c.execute("SELECT reason FROM outcomes").fetchone()["reason"] == "stop")

# 12. Health check suspends a rule whose live accuracy collapses
c = fresh(); set_stats(c, "I1", 45, 50)
for _ in range(20):
    c.execute("INSERT INTO rule_outcomes VALUES (1,'I1',0,?)", (store.now(),))
c.commit(); review.health_check(c)
check("collapsed rule is suspended", stats(c, "I1")[2] == "suspended")

# 13. Open-position guard
c = fresh()
c.execute("INSERT INTO decisions(segment,symbol,ts,price,fields,fired,action,driving_rule,judge,horizon_end)"
          " VALUES ('intraday','TEST',?,100,'{}','[]','BUY-READY-INTRADAY',NULL,NULL,?)", (ts, horizon)); c.commit()
check("open position detected", store.has_open(c, "TEST", "intraday"))
check("no open position for other symbol", not store.has_open(c, "OTHER", "intraday"))

# 13b. Decision logged after its window closed is marked evaluated, not retried forever
c = fresh()
late_ts = "2026-11-11T15:20:00+05:30"
c.execute("INSERT INTO decisions(segment,symbol,ts,price,fields,fired,action,driving_rule,judge,horizon_end)"
          " VALUES ('intraday','TEST',?,100,?,?,'BUY-READY-INTRADAY','I1',NULL,?)",
          (late_ts, json.dumps(fields), json.dumps(["I1"]), horizon)); c.commit()
review.evaluate(c, FakeAdapter(rising))
check("late decision is closed, not retried", c.execute("SELECT evaluated FROM decisions").fetchone()["evaluated"] == 1)

# 14. LLM output parsing
check("parse_json tolerates surrounding text", parse_json('Sure: {"a": 1} done')["a"] == 1)
try:
    parse_json("no json here"); check("parse_json rejects non-JSON", False)
except ValueError:
    check("parse_json rejects non-JSON", True)

print(f"\n{passed} passed, {failed} failed")
