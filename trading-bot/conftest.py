"""Root conftest: being at the trading-bot/ top level puts this
directory on sys.path, so tests can `import strategy`, `import
risk_manager`, etc. without packaging trading-bot as an installable
package. Also provides a Config factory fixture for tests.
"""
import pytest

from config import Config


def _make_cfg(**overrides) -> Config:
    base = dict(
        api_key="", api_secret="", use_testnet=True, dry_run=True,
        symbol="BTCUSDT", quote_asset="USDT", base_asset="BTC", interval="1h",
        ema_fast=3, ema_slow=5, ema_trend=8, rsi_period=5, rsi_entry_min=50.0,
        risk_per_trade_pct=0.01, stop_loss_pct=0.02, take_profit_pct=0.04,
        max_daily_loss_pct=0.03, max_open_positions=1, max_trades_per_day=3,
        cooldown_minutes=60, poll_seconds=60, state_db_path=":memory:",
        log_dir="logs", kill_switch_path="STOP", webhook_url="",
        paper_equity=500.0,
    )
    base.update(overrides)
    return Config(**base)


@pytest.fixture
def cfg_factory():
    return _make_cfg
