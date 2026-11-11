"""Decision engine: builds observed fields, runs rules, arbitrates, runs the debate, logs."""
import json, datetime as dt
import pandas as pd
import store, review
from config import SEGMENTS, DB_PATH, WATCHLIST_PATH, MIS_PATH, ask, parse_json
from rules import seed_rules, fired_rules, arbitrate, stats
from indicators import sma, rsi, atr, vwap, vol_ratio, first_30_high, upper_wick_ratio
from risk import stop_for

BASE = ("You analyze a snapshot of NSE stock data timestamped {ts}. Use only values present in the "
        "snapshot; if a value is missing, say so and do not estimate. Make no price forecasts and no "
        "statements about what will happen. Cite every claim with its field and exact value. Reply with JSON only.")

BULL_ROLE = ("Role: argue the strongest case from the snapshot for the BULL side, addressing the fired "
             "bull rules and their measured win rates. Name the one measured fact that would weaken your case. "
             'Output {"claims":[{"text":"","field":"","value":0}],"weakener":""}')
BEAR_ROLE = ("Role: argue the strongest case from the snapshot for the BEAR side, addressing the fired "
             "bear rules and their measured win rates. Name the one measured fact that would weaken your case. "
             'Output {"claims":[{"text":"","field":"","value":0}],"weakener":""}')
JUDGE_ROLE = ("Role: you do not decide the direction; the arbiter already did. Read both cases and name any "
              "claim that conflicts with the snapshot. Set veto true only when an item in "
              "past_mistakes_to_avoid clearly matches the current state. Output "
              '{"decisive_claims_verified": true, "veto": false, "veto_reason": ""}')

def now_ist() -> dt.datetime:
    return dt.datetime.now(store.IST)

def within_window(segment: str, at: dt.datetime | None = None) -> bool:
    t = (at or now_ist()).time()
    cfg = SEGMENTS[segment]
    if segment == "intraday":
        start, end = (dt.time(*map(int, x.split(":"))) for x in cfg["window"])
        return start <= t <= end
    return t >= dt.time(*map(int, cfg["window_from"].split(":")))

def horizon_for(segment: str, at: dt.datetime | None = None) -> str:
    now = at or now_ist()
    if segment == "intraday":
        h, m = map(int, SEGMENTS["intraday"]["exit_by"].split(":"))
        return now.replace(hour=h, minute=m, second=0, microsecond=0).isoformat(timespec="seconds")
    return (now + dt.timedelta(days=SEGMENTS["swing"]["horizon_days"])).isoformat(timespec="seconds")

def intraday_fields(adapter, symbol: str, at: dt.datetime | None = None) -> dict | None:
    bars = adapter.get_historical(symbol, SEGMENTS["intraday"]["interval"], 5)
    today_date = (at or now_ist()).date()
    today = bars[bars.index.date == today_date] if len(bars) else bars
    if len(today) < 25:
        return None
    price = float(adapter.get_quote(symbol)["last_price"])
    return {"close": price, "entry_price": price,
            "vwap": float(vwap(today).iloc[-1]),
            "vol_ratio": vol_ratio(today),
            "first30_high": first_30_high(today),
            "wick_ratio": upper_wick_ratio(today.iloc[-1]),
            "atr_14": atr(today)}

def swing_fields(adapter, symbol: str) -> dict | None:
    d = adapter.get_historical(symbol, SEGMENTS["swing"]["interval"], 400)
    if len(d) < 200:
        return None
    close = d["close"]
    f = {"close": float(close.iloc[-1]), "sma_50": float(sma(close, 50).iloc[-1]),
         "sma_200": float(sma(close, 200).iloc[-1]), "rsi_14": float(rsi(close).iloc[-1]),
         "atr_14": atr(d), "entry_price": float(close.iloc[-1])}
    if any(pd.isna(v) for v in f.values()):
        return None
    return f

def verify_claims(claims: list, fields: dict) -> tuple[int, int]:
    """Checks each cited field and value against the snapshot. Returns (verified, total)."""
    ok = 0
    for c in claims:
        f, v = c.get("field"), c.get("value")
        if f in fields and isinstance(v, (int, float)):
            tol = max(1e-6, 0.01 * abs(fields[f]))
            ok += abs(fields[f] - v) <= tol
    return ok, len(claims)

def _log(conn, segment, symbol, fields, fired_ids, action, driving, judge, horizon):
    conn.execute("INSERT INTO decisions(segment,symbol,ts,price,fields,fired,action,driving_rule,"
                 "judge,horizon_end) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (segment, symbol, store.now(),
                  fields.get("entry_price") if fields else None,
                  json.dumps(fields or {}), json.dumps(fired_ids), action, driving,
                  json.dumps(judge) if judge else None, horizon))
    conn.commit()

def analyze(symbol: str, segment: str, adapter, conn=None, llm=None, at=None) -> dict:
    """Returns BUY-READY-*, SHORT-READY-INTRADAY, or WAIT, with reasons. Logs unless previewing."""
    llm = llm or ask
    conn = conn or store.connect(DB_PATH)
    seed_rules(conn)
    preview = not within_window(segment, at)
    horizon = horizon_for(segment, at)

    if segment == "intraday" and (at or now_ist()).time() >= dt.time(15, 15):
        return {"action": "WAIT", "reason": "past the 15:15 intraday exit; no new intraday entries"}
    if not preview and store.has_open(conn, symbol, segment):
        return {"action": "WAIT", "reason": "an earlier decision for this symbol is still open"}

    fields = intraday_fields(adapter, symbol, at) if segment == "intraday" else swing_fields(adapter, symbol)
    if not fields:
        if not preview:
            _log(conn, segment, symbol, None, [], "WAIT", None, None, horizon)
        return {"action": "WAIT", "reason": "insufficient data for this segment", "preview": preview}

    fired = fired_rules(segment, fields)
    fired_ids = [r.id for r in fired]
    arb = arbitrate(conn, segment, fired)
    if arb["action"] == "WAIT":
        if not preview:
            _log(conn, segment, symbol, fields, fired_ids, "WAIT", None, None, horizon)
        reason = ("a bear rule blocks the buy" if arb.get("blocked_by")
                  else "no rule meets the minimum measured edge")
        return {"action": "WAIT", "reason": reason, "fired": fired_ids, "arbiter": arb,
                "preview": preview}

    rule_stats = []
    for r in fired:
        w, n, _ = stats(conn, r.id)
        rule_stats.append({"id": r.id, "side": r.side, "name": r.name,
                           "win_rate": round(w / n, 3) if n else None, "trials": n})
    context = {"symbol": symbol, "fields": fields, "fired_rules": rule_stats,
               "past_mistakes_to_avoid": review.lessons_for(conn, segment, fired_ids)}
    ts = store.now()
    try:
        bull = parse_json(llm(BASE.format(ts=ts) + "\n" + BULL_ROLE, json.dumps(context)))
        bear = parse_json(llm(BASE.format(ts=ts) + "\n" + BEAR_ROLE, json.dumps(context)))
        judge = parse_json(llm(BASE.format(ts=ts) + "\n" + JUDGE_ROLE,
                               json.dumps({"context": context, "arbiter": arb,
                                           "bull": bull, "bear": bear})))
    except Exception as e:
        if not preview:
            _log(conn, segment, symbol, fields, fired_ids, "WAIT", None, {"error": str(e)}, horizon)
        return {"action": "WAIT", "reason": f"debate failed: {e}", "preview": preview}

    # Fail closed: any claim that does not match the snapshot, or any failed verification, blocks the trade.
    blocks = []
    ok, total = verify_claims(bull.get("claims", []) + bear.get("claims", []), fields)
    if ok < total:
        blocks.append(f"{total - ok} of {total} cited claims do not match the snapshot")
    if not judge.get("decisive_claims_verified", False):
        blocks.append("judge did not verify the decisive claims")
    if judge.get("veto"):
        blocks.append(f"veto: {judge.get('veto_reason', 'matched a past mistake')}")

    action = arb["action"] if not blocks else "WAIT"
    stop = stop_for(arb["side"], fields["entry_price"], fields["atr_14"],
                    SEGMENTS[segment]["stop_atr"])
    result = {"action": action, "driving_rule": arb["driving_rule"], "fired": fired_ids,
              "arbiter": arb, "bull": bull, "bear": bear, "judge": judge,
              "blocks": blocks, "stop_level": round(stop, 2),
              "entry": fields["entry_price"], "preview": preview}
    if not preview:
        _log(conn, segment, symbol, fields, fired_ids, action, arb["driving_rule"], judge, horizon)
    return result

def load_watchlist(path: str = WATCHLIST_PATH) -> dict:
    with open(path) as f:
        data = json.load(f)
    return {seg: [s.strip().upper() for s in data.get(seg, []) if s.strip()]
            for seg in SEGMENTS}

def load_mis(path: str = MIS_PATH) -> set[str]:
    try:
        with open(path) as f:
            return {s.strip().upper() for s in f if s.strip() and not s.startswith("#")}
    except FileNotFoundError:
        return set()

def watch(segment: str, adapter, llm=None) -> list[dict]:
    symbols = load_watchlist()[segment]
    equity = adapter.equity_symbols()
    unknown = [s for s in symbols if s not in equity]
    if unknown:
        print(f"Skipping non-equity or unknown symbols: {', '.join(unknown)}")
    symbols = [s for s in symbols if s in equity]
    if segment == "intraday":
        mis = load_mis()
        not_mis = [s for s in symbols if s not in mis]
        if not_mis:
            print(f"Not on data/mis_allowed.txt, skipped for intraday: {', '.join(not_mis)}")
        symbols = [s for s in symbols if s in mis]
    conn = store.connect(DB_PATH)
    out = []
    for s in symbols:
        try:
            res = analyze(s, segment, adapter, conn=conn, llm=llm)
        except Exception as e:
            res = {"action": "WAIT", "reason": f"error: {e}"}
        out.append({"symbol": s, **res})
    return out
