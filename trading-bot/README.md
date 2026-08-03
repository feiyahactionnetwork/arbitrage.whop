# Spot Trading Bot (BTCUSDT, Binance)

A simple, single-pair EMA trend-following spot bot, built around the
starter plan: trade one liquid pair, one strategy, strict risk limits,
and a staged rollout (backtest → paper → tiny live → scale).

**This trades real money if you turn DRY_RUN and USE_TESTNET off. Read
this whole file before doing that.**

## Strategy

- Pair: BTCUSDT, timeframe: 1h (both configurable)
- Entry: price above 200 EMA, 20 EMA crosses above 50 EMA, RSI(14) > 50
- Exit: 20 EMA crosses below 50 EMA, or stop-loss / take-profit hit
- Risk: 1% of equity per trade, max 1 open position, max 3 trades/day,
  cooldown after each trade, hard halt at 3% daily loss

## Setup

```bash
cd trading-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — at minimum review DRY_RUN/USE_TESTNET before going further
```

## Stage 1 — Backtest

No API key needed (uses Binance's public market-data endpoint):

```bash
python backtest.py --days 180 --symbol BTCUSDT --interval 1h
```

Reports total trades, win rate, avg win/loss, net profit, max drawdown,
and fees paid, with a taker fee and slippage assumption baked in
(`--fee-bps` / `--slippage-bps` to adjust). Read the caveats at the top
of `backtest.py` — stop/take-profit are checked against candle
high/low (pessimistic), and the equity curve is realized-PnL-only
between trades, not intra-trade mark-to-market.

## Stage 2 — Paper trading

Set `DRY_RUN=true` in `.env` (the default). The bot pulls **live**
market data and evaluates the real strategy, but every "order" is
simulated in-memory against `PAPER_EQUITY` — no Binance credentials or
network order calls are used.

```bash
python bot.py
```

Let it run for several days to a couple of weeks. Check
`logs/bot.log` and the trade metrics (see below).

## Stage 3 — Testnet

Set `DRY_RUN=false`, `USE_TESTNET=true`, and put **testnet** keys
(from https://testnet.binance.vision, not your real account) in
`BINANCE_API_KEY` / `BINANCE_API_SECRET`. This exercises the real
order-placement code path against Binance's sandbox with fake funds —
the closest rehearsal to live trading without risking money.

## Stage 4 — Live, small

Set `USE_TESTNET=false` and use real API keys with **trading**
permission only (do not enable withdrawals on the key). Start with a
small `PAPER_EQUITY`-equivalent — i.e. only fund the account with what
you're prepared to lose while you validate live behavior — and confirm
`RISK_PER_TRADE_PCT` / `MAX_DAILY_LOSS_PCT` match your intended risk
before the first live order. Scale up only once you've watched it run
cleanly for a while.

## Running continuously

For 24/7 uptime on a VPS, run it under a process supervisor rather than
a bare terminal, e.g. systemd:

```ini
# /etc/systemd/system/spot-bot.service
[Unit]
Description=Spot trading bot
After=network.target

[Service]
WorkingDirectory=/path/to/arbitrage.whop/trading-bot
ExecStart=/path/to/arbitrage.whop/trading-bot/.venv/bin/python bot.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

## Safety controls built in

- **Kill switch**: create a file at the path in `KILL_SWITCH_PATH`
  (default `trading-bot/STOP`) to pause the bot without killing the
  process — it polls, sees the file, and skips trading until you
  remove it.
- **Daily loss halt**: once realized losses for the UTC day hit
  `MAX_DAILY_LOSS_PCT`, no new entries until the day rolls over.
- **Cooldown**: `COOLDOWN_MINUTES` after any closed trade before a new
  entry is considered.
- **Max trades/day** and **max open positions** caps.
- **Duplicate-order prevention**: state is persisted in SQLite
  (`state.db`), so a restart doesn't forget an open position or a
  day's realized P&L.
- **Error handling**: exceptions in the trading loop are logged (and
  sent to `WEBHOOK_URL` if set) and the loop retries next interval
  rather than crashing.
- **Logging**: rotating file log at `logs/bot.log` plus console.

## Metrics

Every closed trade is recorded in `state.db` (`trades` table). Get a
summary programmatically:

```python
from state_store import StateStore
print(StateStore("state.db").compute_metrics())
# {'total_trades': ..., 'win_rate': ..., 'avg_win': ..., 'avg_loss': ...,
#  'net_profit': ..., 'max_drawdown': ..., 'fees_paid': ...}
```

## Tests

```bash
pip install -r requirements.txt  # includes pytest
pytest tests/ -v
```

Covers strategy signal logic, position sizing, daily-loss/cooldown/
max-trades gating, and trade persistence — no network or API keys
required.

## Files

| File | Purpose |
|---|---|
| `config.py` | Loads all tunables from `.env` |
| `binance_client.py` | Exchange wrapper (klines, balances, market orders, DRY_RUN short-circuit) |
| `strategy.py` | EMA/RSI entry & exit signal logic |
| `risk_manager.py` | Position sizing, daily loss halt, cooldown, trade caps |
| `state_store.py` | SQLite persistence: open position, trade log, daily stats |
| `bot.py` | Main loop tying it all together |
| `backtest.py` | Historical simulation against public market data |
| `notifier.py` | Optional webhook alerts |

## Biggest mistakes this is designed to avoid

Trading too many pairs, no stop loss, risking too much per trade,
starting live too big, ignoring fees, forgetting daily loss limits.
It intentionally does **one** pair, **one** strategy, and hard risk
caps rather than trying to be a general-purpose multi-strategy engine.
