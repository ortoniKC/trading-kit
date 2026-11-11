import sqlite3, datetime as dt

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SCHEMA = """
CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY, segment TEXT, side TEXT, name TEXT,
  bt_wins INTEGER DEFAULT 0, bt_trials INTEGER DEFAULT 0, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, segment TEXT,
  symbol TEXT, ts TEXT, price REAL, fields TEXT, fired TEXT, action TEXT, driving_rule TEXT,
  judge TEXT, horizon_end TEXT, evaluated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS rule_outcomes(decision_id INTEGER, rule_id TEXT,
  side_correct INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS outcomes(decision_id INTEGER PRIMARY KEY, reason TEXT,
  raw_pct REAL, net_pct REAL, correct INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id INTEGER,
  segment TEXT, failure_type TEXT, signature TEXT, lesson TEXT, guard_rule_id TEXT,
  status TEXT DEFAULT 'candidate', ts TEXT);
"""

def connect(path: str = "trading.db"):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c

def now() -> str:
    return dt.datetime.now(IST).isoformat(timespec="seconds")

def has_open(conn, symbol: str, segment: str) -> bool:
    """True if a non-WAIT decision for this symbol and segment is still unevaluated."""
    return conn.execute("SELECT 1 FROM decisions WHERE symbol=? AND segment=? "
                        "AND evaluated=0 AND action!='WAIT' LIMIT 1",
                        (symbol, segment)).fetchone() is not None
