"""Historical backtest for the EMA trend-following strategy.

Fetches public klines (no API key needed), replays the same
entry_signal/exit_signal used by bot.py candle-by-candle, and reports
the metrics the plan calls for: win rate, avg win/loss, max drawdown,
net profit, fees paid.

Simplifications, so read the numbers as a sanity check, not a promise:
- Stop-loss/take-profit are tested against each candle's high/low
  (pessimistic: stop assumed hit before target within the same candle).
- The reported equity curve is realized-PnL-only between trades; it
  does not mark the open position to market intra-trade.
- Only one open position at a time, matching state_store.py's model.

Usage:
    python backtest.py --days 180 --symbol BTCUSDT --interval 1h
"""
import argparse
import logging

from binance.client import Client

import risk_manager
import strategy
from config import load_config

log = logging.getLogger("backtest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ASSUMED_MIN_NOTIONAL = 10.0  # USDT; real Binance MIN_NOTIONAL varies by symbol


def fetch_history(symbol: str, interval: str, days: int):
    client = Client()  # public endpoint, no keys required
    raw = client.get_historical_klines(symbol, interval, f"{days} day ago UTC")
    import pandas as pd

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df


def simulate(df, cfg, fee_rate: float, slippage_rate: float, starting_equity: float) -> dict:
    df = strategy.compute_indicators(df, cfg)
    equity = starting_equity
    position = None
    trades = []
    equity_curve = [starting_equity]
    start_idx = max(cfg.ema_trend, cfg.rsi_period) + 1

    for i in range(start_idx, len(df)):
        window = df.iloc[: i + 1]
        row = df.iloc[i]

        if position is None:
            if strategy.entry_signal(window, cfg):
                entry_price = row["close"] * (1 + slippage_rate)
                stop = entry_price * (1 - cfg.stop_loss_pct)
                tp = entry_price * (1 + cfg.take_profit_pct)
                qty = risk_manager.position_size(equity, entry_price, stop, cfg.risk_per_trade_pct)
                notional = qty * entry_price
                if qty <= 0 or notional < ASSUMED_MIN_NOTIONAL:
                    continue
                entry_fee = notional * fee_rate
                equity -= notional + entry_fee
                position = {
                    "entry_price": entry_price, "qty": qty, "stop": stop, "tp": tp,
                    "entry_fee": entry_fee, "opened_at": row["close_time"],
                }
            continue

        exit_price, reason = None, None
        if row["low"] <= position["stop"]:
            exit_price, reason = position["stop"] * (1 - slippage_rate), "stop_loss"
        elif row["high"] >= position["tp"]:
            exit_price, reason = position["tp"] * (1 - slippage_rate), "take_profit"
        elif strategy.exit_signal(window, cfg):
            exit_price, reason = row["close"] * (1 - slippage_rate), "signal_exit"

        if exit_price is None:
            continue

        exit_notional = position["qty"] * exit_price
        exit_fee = exit_notional * fee_rate
        equity += exit_notional - exit_fee
        total_fees = position["entry_fee"] + exit_fee
        pnl = (exit_price - position["entry_price"]) * position["qty"] - total_fees
        trades.append({
            "opened_at": position["opened_at"], "closed_at": row["close_time"],
            "entry_price": position["entry_price"], "exit_price": exit_price,
            "qty": position["qty"], "pnl": pnl, "fees": total_fees, "reason": reason,
        })
        equity_curve.append(equity)
        position = None

    return summarize(trades, starting_equity, equity)


def summarize(trades: list, starting_equity: float, ending_equity: float) -> dict:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "net_profit": 0.0, "max_drawdown": 0.0, "fees_paid": 0.0,
            "starting_equity": starting_equity, "ending_equity": ending_equity,
        }
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    cumulative, running_max, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        cumulative += t["pnl"]
        running_max = max(running_max, cumulative)
        max_dd = max(max_dd, running_max - cumulative)
    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "net_profit": sum(t["pnl"] for t in trades),
        "max_drawdown": max_dd,
        "fees_paid": sum(t["fees"] for t in trades),
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--interval", type=str, default=None)
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Taker fee in basis points (10 = 0.10%%)")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points")
    parser.add_argument("--equity", type=float, default=None)
    args = parser.parse_args()

    cfg = load_config()
    symbol = (args.symbol or cfg.symbol).upper()
    interval = args.interval or cfg.interval
    equity = args.equity if args.equity is not None else cfg.paper_equity

    log.info("Fetching %s days of %s %s klines...", args.days, symbol, interval)
    df = fetch_history(symbol, interval, args.days)
    log.info("Fetched %d candles. Running simulation...", len(df))

    result = simulate(df, cfg, args.fee_bps / 10_000, args.slippage_bps / 10_000, equity)

    print("\n--- Backtest results: {} {} over {} days ---".format(symbol, interval, args.days))
    for key, value in result.items():
        if isinstance(value, float):
            print(f"{key:>16}: {value:,.4f}")
        else:
            print(f"{key:>16}: {value}")


if __name__ == "__main__":
    main()
