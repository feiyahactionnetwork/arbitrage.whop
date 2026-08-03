"""Spot trend-following bot entrypoint.

Loop: fetch candles -> compute indicators -> manage open position (stop
loss / take profit / signal exit) -> else look for a new entry -> log
everything -> sleep -> repeat. See README.md for setup and the safety
controls (kill switch, daily loss halt, cooldown) this relies on.
"""
import logging
import logging.handlers
import os
import signal
import sys
import time

import risk_manager
import strategy
from binance_client import BinanceClient, ExchangeError
from config import Config, load_config
from notifier import notify
from state_store import StateStore

log = logging.getLogger("bot")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %s, shutting down after this iteration.", signum)
    _shutdown = True


def setup_logging(cfg: Config) -> None:
    os.makedirs(cfg.log_dir, exist_ok=True)
    root = logging.getLogger("bot")
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(cfg.log_dir, "bot.log"), maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def kill_switch_active(cfg: Config) -> bool:
    return os.path.exists(cfg.kill_switch_path)


def manage_open_position(client: BinanceClient, state: StateStore, cfg: Config,
                          closed_df) -> None:
    position = state.get_open_position()
    if position is None:
        return

    current_price = client.get_last_price()
    exit_reason = None
    if current_price <= position.stop_price:
        exit_reason = "stop_loss"
    elif current_price >= position.take_profit_price:
        exit_reason = "take_profit"
    elif strategy.exit_signal(closed_df, cfg):
        exit_reason = "signal_exit"

    if exit_reason is None:
        return

    try:
        order = client.market_sell(position.quantity)
    except ExchangeError as exc:
        log.error("Failed to close position (%s): %s", exit_reason, exc)
        return

    fill_price = float(order.get("price", current_price))
    trade = state.close_position(exit_price=fill_price, exit_reason=exit_reason)
    risk_manager.start_cooldown(state, cfg)
    notify(
        cfg.webhook_url,
        f"SELL {cfg.symbol} qty={trade['quantity']:.6f} @ {fill_price:.2f} "
        f"reason={exit_reason} pnl={trade['pnl_quote']:.2f} ({trade['pnl_pct']*100:.2f}%)",
    )


def look_for_entry(client: BinanceClient, state: StateStore, cfg: Config, closed_df) -> None:
    last_candle_time = closed_df.iloc[-1]["close_time"].isoformat()
    if state.get_meta("last_processed_candle") == last_candle_time:
        return
    state.set_meta("last_processed_candle", last_candle_time)

    equity = client.get_free_balance(cfg.quote_asset)
    blocked_reason = risk_manager.can_open_new_trade(state, cfg, equity)
    if blocked_reason is not None:
        log.debug("Skipping entry check: %s", blocked_reason)
        return

    if not strategy.entry_signal(closed_df, cfg):
        return

    current_price = client.get_last_price()
    stop_price = current_price * (1 - cfg.stop_loss_pct)
    take_profit_price = current_price * (1 + cfg.take_profit_pct)
    quantity = risk_manager.position_size(equity, current_price, stop_price, cfg.risk_per_trade_pct)

    if quantity * current_price < client.min_notional() or quantity <= 0:
        log.info("Entry signal fired but sized quantity is below exchange minimum notional; skipping.")
        return

    try:
        order = client.market_buy(quantity)
    except ExchangeError as exc:
        log.error("Failed to open position: %s", exc)
        return

    filled_qty = float(order.get("executedQty", quantity))
    fill_price = float(order.get("price", current_price))
    state.open_position(
        symbol=cfg.symbol, entry_price=fill_price, quantity=filled_qty,
        stop_price=stop_price, take_profit_price=take_profit_price,
        order_id=str(order.get("orderId", "")),
    )
    notify(
        cfg.webhook_url,
        f"BUY {cfg.symbol} qty={filled_qty:.6f} @ {fill_price:.2f} "
        f"stop={stop_price:.2f} tp={take_profit_price:.2f}",
    )


def run_iteration(client: BinanceClient, state: StateStore, cfg: Config) -> None:
    df = client.get_klines_df(limit=max(cfg.ema_trend + 50, 300))
    closed_df = df.iloc[:-1]  # drop the still-forming candle
    closed_df = strategy.compute_indicators(closed_df, cfg)

    manage_open_position(client, state, cfg, closed_df)
    if state.get_open_position() is None:
        look_for_entry(client, state, cfg, closed_df)


def main() -> None:
    cfg = load_config()
    setup_logging(cfg)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    mode = "DRY_RUN (paper)" if cfg.dry_run else ("TESTNET" if cfg.use_testnet else "LIVE")
    log.info(
        "Starting bot: symbol=%s interval=%s mode=%s risk_per_trade=%.2f%% max_daily_loss=%.2f%%",
        cfg.symbol, cfg.interval, mode, cfg.risk_per_trade_pct * 100, cfg.max_daily_loss_pct * 100,
    )
    if not cfg.dry_run and not cfg.api_key:
        log.error("DRY_RUN is off but BINANCE_API_KEY is not set. Refusing to start live without credentials.")
        sys.exit(1)

    os.makedirs(os.path.dirname(cfg.state_db_path) or ".", exist_ok=True)
    state = StateStore(cfg.state_db_path)
    client = BinanceClient(cfg)

    while not _shutdown:
        if kill_switch_active(cfg):
            log.warning("Kill switch file present at %s; halting until it is removed.", cfg.kill_switch_path)
            time.sleep(cfg.poll_seconds)
            continue
        try:
            run_iteration(client, state, cfg)
        except Exception as exc:
            log.exception("Unhandled error in trading loop iteration; will retry after poll interval.")
            notify(cfg.webhook_url, f"ERROR in trading loop for {cfg.symbol}: {exc}")
        time.sleep(cfg.poll_seconds)

    log.info("Bot stopped cleanly.")


if __name__ == "__main__":
    main()
