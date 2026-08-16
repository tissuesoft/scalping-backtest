"""CLI: PORT5 runner — real Binance Futures charts + demo account orders.

Setup
-----
1) Open https://demo.binance.com → Futures → API Management → create key
2) Copy `.env.example` to `.env` and fill API key/secret
3) Market data uses real fapi (BINANCE_MARKET_BASE_URL=https://fapi.binance.com)
4) Dry-run:
     python -u -m live.run_demo
5) Demo orders (still demo account, real charts):
     python -u -m live.run_demo --live

Stop: create file `live/STOP` or Ctrl+C.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# allow `python -m live.run_demo` from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.config import load_live_config
from live.runner import DemoRunner, _log


def main() -> None:
    ap = argparse.ArgumentParser(description="PORT5 Binance Futures Demo runner")
    ap.add_argument(
        "--live",
        action="store_true",
        help="Place real demo orders (default is dry-run)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Force dry-run")
    ap.add_argument("--leverage", type=float, default=None, help="Override leverage (default 100)")
    ap.add_argument("--poll", type=float, default=None, help="Poll seconds (default 15)")
    ap.add_argument("--once", action="store_true", help="Single loop then exit")
    args = ap.parse_args()

    dry = True
    if args.live:
        dry = False
    if args.dry_run:
        dry = True

    cfg = load_live_config(dry_run=dry, leverage=args.leverage, poll_sec=args.poll)
    if not dry and (not cfg.api_key or not cfg.api_secret):
        _log("ERROR: --live requires BINANCE_DEMO_API_KEY/SECRET in .env")
        sys.exit(1)

    runner = DemoRunner(cfg)
    if args.once:
        runner.setup_exchange()
        runner.loop_once()
        return
    runner.run()


if __name__ == "__main__":
    main()
