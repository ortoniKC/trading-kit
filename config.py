import os, json, re
import envfile
envfile.load_env()

try:
    import anthropic
    _client = anthropic.Anthropic()
except Exception:
    _client = None  # tests and offline runs use stubs

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
DB_PATH = os.environ.get("TRADING_DB", "data/trading.db")
WATCHLIST_PATH = "watchlist.json"
MIS_PATH = "data/mis_allowed.txt"

SEGMENTS = {
    "intraday": {"product": "MIS", "window": ("09:30", "14:45"), "exit_by": "15:15",
                 "interval": "5minute", "lookback_days": 5, "allow_short": True,
                 "cost_pct": 0.10, "min_trials": 30, "stop_atr": 1.5, "horizon_days": 0},
    "swing": {"product": "CNC", "window_from": "15:35", "interval": "day",
              "lookback_days": 60, "allow_short": False, "cost_pct": 0.30,
              "min_trials": 40, "stop_atr": 2.0, "horizon_days": 21},
}  # cost_pct values are placeholders; calibrate before use

PRIOR_RATE, PRIOR_WEIGHT = 0.5, 20
MIN_EDGE, MARGIN = 0.03, 0.02
SUSPEND_GAP, SUSPEND_WINDOW = 0.15, 20

def ask(system: str, user: str, max_tokens: int = 700) -> str:
    if _client is None:
        raise RuntimeError("Anthropic client not configured. Run ./setup.sh to add ANTHROPIC_API_KEY.")
    r = _client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                                messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in r.content if b.type == "text")

def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))
