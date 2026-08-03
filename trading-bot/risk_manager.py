"""Position sizing and the "stay alive" rules from the plan:
risk <=1% per trade, max 3% daily loss, cooldown after a trade,
max trades per day, and a hard halt once the daily loss cap is hit.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import Config
from state_store import StateStore

log = logging.getLogger("bot.risk")


def position_size(equity: float, entry_price: float, stop_price: float, risk_pct: float) -> float:
    """Size so that a stop-out loses exactly risk_pct of equity (spot, no leverage)."""
    per_unit_risk = abs(entry_price - stop_price)
    if per_unit_risk <= 0:
        return 0.0
    risk_amount = equity * risk_pct
    quantity = risk_amount / per_unit_risk
    max_affordable = equity / entry_price
    return max(0.0, min(quantity, max_affordable))


def daily_loss_limit_hit(state: StateStore, cfg: Config, starting_equity: float) -> bool:
    stats = state.get_today_stats(starting_equity)
    if stats["halted"]:
        return True
    loss_limit = -abs(cfg.max_daily_loss_pct) * stats["starting_equity"]
    if stats["realized_pnl"] <= loss_limit:
        log.warning(
            "Daily loss limit hit: realized_pnl=%.4f <= limit=%.4f. Halting new entries until UTC day rolls over.",
            stats["realized_pnl"], loss_limit,
        )
        state.set_halted_today()
        return True
    return False


def in_cooldown(state: StateStore) -> bool:
    raw = state.get_meta("cooldown_until")
    if not raw:
        return False
    return datetime.now(timezone.utc) < datetime.fromisoformat(raw)


def start_cooldown(state: StateStore, cfg: Config) -> None:
    until = datetime.now(timezone.utc) + timedelta(minutes=cfg.cooldown_minutes)
    state.set_meta("cooldown_until", until.isoformat())


def max_trades_reached(state: StateStore, cfg: Config, starting_equity: float) -> bool:
    stats = state.get_today_stats(starting_equity)
    return stats["trades_count"] >= cfg.max_trades_per_day


def can_open_new_trade(state: StateStore, cfg: Config, starting_equity: float) -> Optional[str]:
    """Returns None if a new trade is allowed, else a string reason it's blocked."""
    if state.get_open_position() is not None:
        return "position already open"
    if daily_loss_limit_hit(state, cfg, starting_equity):
        return "daily loss limit reached"
    if max_trades_reached(state, cfg, starting_equity):
        return "max trades per day reached"
    if in_cooldown(state):
        return "in post-trade cooldown"
    return None
