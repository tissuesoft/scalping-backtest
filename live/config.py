"""Live demo config (Binance USD-M Futures Demo orders + real market data)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from portfolio_engine import PortfolioConfig
from strategies.registry import PORTFOLIO_SYMBOLS

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


@dataclass
class LiveConfig:
    api_key: str
    api_secret: str
    # Orders / account (demo)
    trade_url: str = "https://demo-fapi.binance.com"
    # Charts / klines / mark (real Binance Futures)
    market_url: str = "https://fapi.binance.com"
    symbols: tuple[str, ...] = PORTFOLIO_SYMBOLS
    dry_run: bool = True
    poll_sec: float = 15.0
    kline_limit: int = 1200
    leverage: float = 100.0
    state_path: Path = ROOT / "live" / "state.json"
    log_dir: Path = ROOT / "live" / "logs"
    stop_file: Path = ROOT / "live" / "STOP"
    portfolio: PortfolioConfig | None = None

    @property
    def base_url(self) -> str:
        """Trade host (demo). Kept for older call sites."""
        return self.trade_url

    def __post_init__(self) -> None:
        if self.portfolio is None:
            self.portfolio = PortfolioConfig(
                leverage=float(self.leverage),
            )
        else:
            self.portfolio.leverage = float(self.leverage)


def load_live_config(
    dry_run: bool | None = None,
    leverage: float | None = None,
    poll_sec: float | None = None,
) -> LiveConfig:
    _load_dotenv(ROOT / ".env")
    key = os.environ.get("BINANCE_DEMO_API_KEY", "").strip()
    secret = os.environ.get("BINANCE_DEMO_API_SECRET", "").strip()
    trade = os.environ.get("BINANCE_DEMO_BASE_URL", "https://demo-fapi.binance.com").strip()
    market = os.environ.get("BINANCE_MARKET_BASE_URL", "https://fapi.binance.com").strip()
    env_dry = os.environ.get("BINANCE_DEMO_DRY_RUN", "1").strip().lower() in ("1", "true", "yes")
    return LiveConfig(
        api_key=key,
        api_secret=secret,
        trade_url=trade.rstrip("/"),
        market_url=market.rstrip("/"),
        dry_run=env_dry if dry_run is None else dry_run,
        leverage=float(leverage if leverage is not None else os.environ.get("BINANCE_DEMO_LEVERAGE", 100)),
        poll_sec=float(poll_sec if poll_sec is not None else os.environ.get("BINANCE_DEMO_POLL_SEC", 15)),
    )
