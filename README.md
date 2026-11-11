# Trading kit

Advisory stock analysis for NSE equities, using Kite Connect for data and Claude for the debate.
Cash equity only. No F&O. Makes no price forecasts. Outputs BUY-READY, SHORT-READY (intraday only), or WAIT.

## Setup on a MacBook

1. Install Python 3.10+ and git if you don't have them:
   ```bash
   brew install python git
   ```
2. Clone the kit:
   ```bash
   git clone <your-repo-url> trading-kit
   cd trading-kit
   ```
3. Put your stock names in `watchlist.json`, using NSE symbols (for example RELIANCE, INFY).
4. Run setup. It creates a virtual environment, installs packages, and asks for your API keys with hidden input:
   ```bash
   ./setup.sh
   ```
5. Edit `data/mis_allowed.txt` with the MIS-eligible symbols from your broker. Intraday symbols not on this list are skipped.
6. Each trading day, log in to Kite. You do the login yourself in the browser:
   ```bash
   ./setup.sh login
   ```
7. Try it:
   ```bash
   ./run.sh analyze RELIANCE swing
   ./run.sh watch swing
   ./run.sh test
   ```

## Using it with Claude Code

Open the folder in Claude Code. The project's `CLAUDE.md` gives Claude the rules, and the slash commands
`/analyze`, `/watch`, `/review`, and `/screen` run the matching `./run.sh` command.

## Important

- Keep `.env` private. It is in `.gitignore`. Never paste your keys into chat or commit them.
- Kite access tokens expire daily, so run `./setup.sh login` before each session.
- Costs and thresholds are placeholders. The backtest that fills rule statistics is not built yet, so
  until it is, every result is WAIT.
- Advisory output only. This is general information, not financial or legal advice. If you share outputs
  with others, SEBI Research Analyst rules may apply.
