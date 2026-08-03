"""Environment-driven configuration for the spot trading bot.

All tunables live here so bot.py, strategy.py, and risk_manager.py never
read os.environ directly. Defaults are conservative (testnet, tiny size).
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val not in (None, "") else default


def _int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val not in (None, "") else default


@dataclass(frozen=True)
class Config:
    # --- Exchange credentials ---
    api_key: str
    api_secret: str
    use_testnet: bool
    dry_run: bool

    # --- Market ---
    symbol: str
    quote_asset: str
    base_asset: str
    interval: str

    # --- Strategy ---
    ema_fast: int
    ema_slow: int
    ema_trend: int
    rsi_period: int
    rsi_entry_min: float

    # --- Risk ---
    risk_per_trade_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    max_trades_per_day: int
    cooldown_minutes: int

    # --- Operations ---
    poll_seconds: int
    state_db_path: str
    log_dir: str
    kill_switch_path: str
    webhook_url: str
    paper_equity: float


def load_config() -> Config:
    interval = os.getenv("INTERVAL", "1h")
    symbol = os.getenv("SYMBOL", "BTCUSDT").upper()
    quote_asset = os.getenv("QUOTE_ASSET", "USDT").upper()
    base_asset = symbol[: -len(quote_asset)] if symbol.endswith(quote_asset) else symbol

    return Config(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        use_testnet=_bool("USE_TESTNET", True),
        dry_run=_bool("DRY_RUN", True),
        symbol=symbol,
        quote_asset=quote_asset,
        base_asset=base_asset,
        interval=interval,
        ema_fast=_int("EMA_FAST", 20),
        ema_slow=_int("EMA_SLOW", 50),
        ema_trend=_int("EMA_TREND", 200),
        rsi_period=_int("RSI_PERIOD", 14),
        rsi_entry_min=_float("RSI_ENTRY_MIN", 50.0),
        risk_per_trade_pct=_float("RISK_PER_TRADE_PCT", 0.01),
        stop_loss_pct=_float("STOP_LOSS_PCT", 0.02),
        take_profit_pct=_float("TAKE_PROFIT_PCT", 0.04),
        max_daily_loss_pct=_float("MAX_DAILY_LOSS_PCT", 0.03),
        max_open_positions=_int("MAX_OPEN_POSITIONS", 1),
        max_trades_per_day=_int("MAX_TRADES_PER_DAY", 3),
        cooldown_minutes=_int("COOLDOWN_MINUTES", 60),
        poll_seconds=_int("POLL_SECONDS", 60),
        state_db_path=os.getenv("STATE_DB_PATH", "trading-bot/state.db"),
        log_dir=os.getenv("LOG_DIR", "trading-bot/logs"),
        kill_switch_path=os.getenv("KILL_SWITCH_PATH", "trading-bot/STOP"),
        webhook_url=os.getenv("WEBHOOK_URL", ""),
        paper_equity=_float("PAPER_EQUITY", 500.0),
    )
