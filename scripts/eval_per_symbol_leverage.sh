#!/usr/bin/env bash
# PORT5 windows — leverage always capped per Binance demo (no flag).
# BTC100 ETH100 BNB75 SOL50 XRP75 when --leverage 100
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:-P_levcap}"
python -u eval_portfolio_windows.py \
  --capital 100 \
  --leverage 100 \
  --out-dir reports/iter/port5_agent \
  --tag "$TAG"
