#!/usr/bin/env bash
# One-time setup on macOS (also works on Linux). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "login" ]]; then
  exec ./run.sh login
fi

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "python3 not found. Install it with: brew install python"; exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required."; exit 1
fi

if [[ ! -d .venv ]]; then "$PY" -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
mkdir -p data logs

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
fi
if [[ ! -f data/mis_allowed.txt ]]; then
  cp data/mis_allowed.example.txt data/mis_allowed.txt
fi

python setup_env.py

echo ""
echo "Setup complete."
echo "  1. Edit watchlist.json with your stock names (NSE symbols, e.g. RELIANCE)."
echo "  2. Each trading day, log in to Kite:   ./setup.sh login"
echo "  3. Try it:                             ./run.sh analyze RELIANCE swing"
