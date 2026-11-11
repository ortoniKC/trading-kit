"""Entry point. Run through ./run.sh. Examples:
   ./run.sh login
   ./run.sh screen movers | screen active
   ./run.sh analyze RELIANCE swing
   ./run.sh watch intraday | watch swing
   ./run.sh review
   ./run.sh test
"""
import sys, json, datetime as dt, subprocess
import envfile
envfile.load_env()
import store, review
from config import DB_PATH, SEGMENTS
from engine import analyze, watch, now_ist

LABELS = {"BUY-READY-INTRADAY": "BUY-READY (intraday long, exit by 15:15 IST)",
          "SHORT-READY-INTRADAY": "SHORT-READY (intraday short, cover by 15:15 IST)",
          "BUY-READY-SWING": "BUY-READY (swing, about 3 weeks)",
          "WAIT": "WAIT"}

def token_is_today() -> bool:
    import os
    return os.environ.get("KITE_TOKEN_DATE") == now_ist().date().isoformat() and bool(os.environ.get("KITE_ACCESS_TOKEN"))

def require_login():
    if not token_is_today():
        sys.exit("No valid Kite login for today. Run: ./run.sh login")

def print_report(symbol: str, segment: str, res: dict) -> None:
    print(f"\n{symbol} | {segment} | {LABELS[res['action']]}")
    if res.get("preview"):
        print("Preview only: outside this segment's decision window, nothing logged.")
    if res.get("driving_rule"):
        print(f"Driving rule: {res['driving_rule']}")
    if res.get("stop_level") and res["action"] != "WAIT":
        print(f"Stop level: {res['stop_level']} (ATR-based; a risk limit, not a forecast)")
    if res.get("reason"):
        print(f"Reason: {res['reason']}")
    for b in res.get("blocks", []):
        print(f"Blocked: {b}")
    if res.get("judge"):
        print("\nBull case:", json.dumps(res.get("bull"), indent=2))
        print("\nBear case:", json.dumps(res.get("bear"), indent=2))
        print("\nJudge:", json.dumps(res.get("judge"), indent=2))

def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "help"
    if cmd == "help" or cmd not in {"login", "test", "screen", "analyze", "watch", "review"}:
        print(__doc__)
        return
    if cmd == "login":
        import login_kite; login_kite.main(); return
    if cmd == "test":
        codes = [subprocess.call([sys.executable, t]) for t in ("tests/test_core.py", "tests/test_engine.py")]
        sys.exit(max(codes))

    require_login()
    from kite_adapter import KiteAdapter
    adapter = KiteAdapter()

    if cmd == "screen":
        import screener
        print(screener.run(argv[1] if len(argv) > 1 else "movers", adapter).to_string(index=False))
    elif cmd == "analyze":
        if len(argv) != 3 or argv[2] not in SEGMENTS:
            sys.exit("usage: ./run.sh analyze SYMBOL intraday|swing")
        symbol, segment = argv[1].upper(), argv[2]
        print_report(symbol, segment, analyze(symbol, segment, adapter))
    elif cmd == "watch":
        if len(argv) != 2 or argv[1] not in SEGMENTS:
            sys.exit("usage: ./run.sh watch intraday|swing")
        for r in watch(argv[1], adapter):
            print(f"{r['symbol']:<12} {LABELS[r['action']]:<55} {r.get('reason', '')}")
    elif cmd == "review":
        conn = store.connect(DB_PATH)
        review.evaluate(conn, adapter)
        review.health_check(conn)
        print("Review complete.")

if __name__ == "__main__":
    main(sys.argv[1:])
