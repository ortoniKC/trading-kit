# Trading kit: project instructions for Claude

## What this project is
An advisory decision system for NSE cash equities, run by the owner for their own decisions.
It reads observed market data from Kite Connect, applies pre-defined rules with measured track
records, runs a bull/bear debate, and outputs BUY-READY, SHORT-READY, or WAIT with reasons.

## Hard rules (never change without the owner asking)
- Cash equity only. Never place or suggest F&O (futures, options, or any derivative).
- Intraday (MIS): long and short allowed, flat by 15:15 IST, symbols must be on data/mis_allowed.txt.
- Swing (CNC): long only. A bear signal can block a buy but never create a sell-short.
- Advisory only. `place_order` raises an error. Do not add order placement without an explicit request
  and a human confirmation step, plus static IP and Algo-ID handling.
- No price forecasts. Outputs describe measured state and measured rule history. Never write
  "will go up", targets, or probabilities of future price moves.
- WAIT is the default. Any unverified claim or failed judge check blocks a trade (fail closed).
- Never read, print, log, or commit secrets in .env, access tokens, or API keys.
- Never automate the Zerodha login. The owner logs in through the browser with their own 2FA.

## How to work in this repo
- Run `./run.sh test` before and after every change. All tests must pass.
- Do not hard-code symbols. They come from watchlist.json.
- Do not edit `data/trading.db` by hand. Backtest counts go in the rules table via the backtest step.
- Keep every decision logged. The learning loop depends on the decisions and outcomes tables.
- Lessons from losing trades change prompts only. They never change rule logic without out-of-sample
  support (see review.promote_guard).

## File map
- cli.py: entry point for every command
- engine.py: builds observed fields, runs rules, arbitrates, runs the debate, logs decisions
- rules.py: rule library, edge calculation, bull/bear arbiter
- risk.py: ATR stops and bar-by-bar trade path outcomes
- review.py: scores decisions after their horizon, writes post-mortems, suspends weak rules
- indicators.py: SMA, RSI, ATR, VWAP, volume ratio, first-30-minute high, wick ratio
- kite_adapter.py: read-only Kite Connect wrapper
- screener.py: today's movers and most-traded equities
- login_kite.py, setup_env.py, envfile.py: credentials and daily login
- tests/: unit tests with synthetic data, no network

## Commands
- `./run.sh analyze SYMBOL intraday|swing`
- `./run.sh watch intraday|swing`
- `./run.sh screen movers|active`
- `./run.sh review`
- `./run.sh test`

## Known gaps (do not treat as done)
- The backtest that fills rule statistics is not built yet. Until it exists, every rule has zero history
  and the system returns WAIT.
- Costs in config.py are placeholders.
- No position sizing, daily loss limit, or kill switch yet.
- Holiday calendar is not built in.
