import json
import pandas as pd
import store
from config import SEGMENTS, SUSPEND_GAP, SUSPEND_WINDOW, ask, parse_json
from rules import RULE_SIDE
from risk import stop_for, path_outcome

EXECUTED = {"BUY-READY-INTRADAY", "SHORT-READY-INTRADAY", "BUY-READY-SWING"}

POSTMORTEM_SYSTEM = """You review one trading decision that lost money after costs.
Use only the snapshot, rules, judge output and realized result provided. Do not speculate about
market events that are not in the data. Reply with JSON only:
{"failure_type": "unverified_claim|rule_misfired|regime_change|costs_ignored|stop_hit|data_issue|other",
 "lesson": "one sentence: the observable condition and what to do differently",
 "guard_candidate": "rule id worth testing for suspension, or null"}"""

def evaluate(conn, adapter):
    """Score decisions whose horizon has passed, using bars up to the horizon, not the live quote."""
    due = conn.execute("SELECT * FROM decisions WHERE evaluated=0 AND horizon_end<=?",
                       (store.now(),)).fetchall()
    for d in due:
        if d["price"] is None or not d["fields"]:
            conn.execute("UPDATE decisions SET evaluated=1 WHERE id=?", (d["id"],))
            continue
        seg = SEGMENTS[d["segment"]]
        fields = json.loads(d["fields"])
        bars = adapter.get_historical(d["symbol"], interval=seg["interval"],
                                      days=seg["lookback_days"])
        entry_ts = pd.Timestamp(d["ts"])
        horizon_ts = pd.Timestamp(d["horizon_end"])
        if entry_ts >= horizon_ts:  # logged after its window closed: nothing to score
            conn.execute("UPDATE decisions SET evaluated=1 WHERE id=?", (d["id"],))
            continue
        entry = float(d["price"])
        cost = seg["cost_pct"]

        # Rule scoring uses the horizon close, so it measures the signal, not the stop.
        long_path = path_outcome(bars, "bull", entry_ts, float("-inf"), horizon_ts)
        if long_path is None:
            continue  # no bars yet; retry on a later run
        raw = (long_path["horizon_close"] / entry - 1) * 100
        bull_net, bear_net = raw - cost, -raw - cost
        for rid in json.loads(d["fired"]):
            correct = (bull_net if RULE_SIDE[rid] == "bull" else bear_net) > 0
            conn.execute("INSERT INTO rule_outcomes VALUES (?,?,?,?)",
                         (d["id"], rid, int(correct), store.now()))

        # Trade scoring uses the stop-aware exit for the side that was actually traded.
        if d["action"] in EXECUTED:
            side = "bear" if d["action"] == "SHORT-READY-INTRADAY" else "bull"
            stop = stop_for(side, entry, fields["atr_14"], seg["stop_atr"])
            path = path_outcome(bars, side, entry_ts, stop, horizon_ts)
            exit_raw = (path["exit"] / entry - 1) * 100
            trade_raw = exit_raw if side == "bull" else -exit_raw
            net = trade_raw - cost
            correct = net > 0
            conn.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?)",
                         (d["id"], path["reason"], trade_raw, net, int(correct), store.now()))
            if not correct:
                postmortem(conn, d, trade_raw, net, path["reason"])

        conn.execute("UPDATE decisions SET evaluated=1 WHERE id=?", (d["id"],))
    conn.commit()

def postmortem(conn, d, raw, net, exit_reason):
    user = json.dumps({
        "action": d["action"],
        "fields": json.loads(d["fields"]),
        "fired": json.loads(d["fired"]),
        "judge": json.loads(d["judge"]) if d["judge"] else None,
        "exit_reason": exit_reason,
        "raw_return_pct": round(raw, 3),
        "net_return_pct": round(net, 3),
    })
    try:
        out = parse_json(ask(POSTMORTEM_SYSTEM, user, max_tokens=400))
    except Exception:
        return  # a failed review writes no lesson; never block the loop
    conn.execute("INSERT INTO lessons(decision_id,segment,failure_type,signature,lesson,"
                 "guard_rule_id,status,ts) VALUES (?,?,?,?,?,?,'candidate',?)",
                 (d["id"], d["segment"], out.get("failure_type", "other"),
                  json.dumps(sorted(json.loads(d["fired"]))), out["lesson"],
                  out.get("guard_candidate"), store.now()))
    conn.commit()

def lessons_for(conn, segment: str, fired_ids: list) -> list:
    """Past lessons whose triggering rules overlap today's rules. Shown to the agents."""
    rows = conn.execute("SELECT lesson, signature FROM lessons "
                        "WHERE segment=? AND status!='retired'", (segment,)).fetchall()
    current = set(fired_ids)
    return [r["lesson"] for r in rows if set(json.loads(r["signature"])) & current]

def health_check(conn):
    """Suspend rules whose recent live accuracy has fallen well below their backtest rate."""
    for r in conn.execute("SELECT id, bt_wins, bt_trials FROM rules "
                          "WHERE status='active'").fetchall():
        if r["bt_trials"] == 0:
            continue
        bt_rate = r["bt_wins"] / r["bt_trials"]
        recent = conn.execute("SELECT side_correct FROM rule_outcomes WHERE rule_id=? "
                              "ORDER BY rowid DESC LIMIT ?", (r["id"], SUSPEND_WINDOW)).fetchall()
        if len(recent) < SUSPEND_WINDOW:
            continue
        live_rate = sum(x["side_correct"] for x in recent) / len(recent)
        if live_rate < bt_rate - SUSPEND_GAP:
            conn.execute("UPDATE rules SET status='suspended' WHERE id=?", (r["id"],))
            print(f"SUSPENDED {r['id']}: live {live_rate:.2f} vs backtest {bt_rate:.2f}")
    conn.commit()

def promote_guard(conn, lesson_id: int, oos_wins: int, oos_trials: int, min_trials: int = 40):
    """Act on a lesson only if out-of-sample data supports the rule it names."""
    lesson = conn.execute("SELECT guard_rule_id FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    if not lesson or not lesson["guard_rule_id"] or oos_trials < min_trials:
        return False
    if oos_wins / oos_trials < 0.5:
        conn.execute("UPDATE rules SET status='suspended' WHERE id=?", (lesson["guard_rule_id"],))
        conn.execute("UPDATE lessons SET status='active' WHERE id=?", (lesson_id,))
        conn.commit()
        return True
    conn.execute("UPDATE lessons SET status='retired' WHERE id=?", (lesson_id,))
    conn.commit()
    return False
