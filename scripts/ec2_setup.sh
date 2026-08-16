#!/usr/bin/env bash
# Minimal EC2 bootstrap for PORT5 Binance demo runner.
# Usage on EC2 (Ubuntu):
#   git clone <repo> && cd scalping-backtest
#   bash scripts/ec2_setup.sh
# Then create .env (never commit) and:
#   python3 -u -m live.run_demo --live
set -euo pipefail
cd "$(dirname "$0")/.."

sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
# stdlib-only live runner; install pandas/numpy for signals
pip install pandas numpy

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Edit .env with BINANCE_DEMO_API_KEY/SECRET before --live"
fi

echo "OK. Activate: source .venv/bin/activate"
echo "Dry-run: python -u -m live.run_demo --once"
echo "Live:    python -u -m live.run_demo --live"
echo "Stop:    touch live/STOP"
