"""EMA trend-following signal, per the plan:

Entry: price > 200 EMA, 20 EMA crosses above 50 EMA, RSI(14) > 50.
Exit:  20 EMA crosses below 50 EMA (stop-loss / take-profit are handled
       separately by risk_manager against the live price, not here).

Expects a DataFrame of *closed* candles only (the caller must drop the
still-forming last candle from the exchange response).
"""
import pandas as pd
import ta

from config import Config


def compute_indicators(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=cfg.ema_slow, adjust=False).mean()
    out["ema_trend"] = out["close"].ewm(span=cfg.ema_trend, adjust=False).mean()
    out["rsi"] = ta.momentum.RSIIndicator(out["close"], window=cfg.rsi_period).rsi()
    return out


def _ready(df: pd.DataFrame, cfg: Config) -> bool:
    required = max(cfg.ema_trend, cfg.rsi_period) + 1
    return len(df) >= required and not df[["ema_fast", "ema_slow", "ema_trend", "rsi"]].iloc[-2:].isna().any().any()


def entry_signal(df: pd.DataFrame, cfg: Config) -> bool:
    if not _ready(df, cfg):
        return False
    prev, last = df.iloc[-2], df.iloc[-1]
    cross_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    trend_ok = last["close"] > last["ema_trend"]
    rsi_ok = last["rsi"] > cfg.rsi_entry_min
    return bool(cross_up and trend_ok and rsi_ok)


def exit_signal(df: pd.DataFrame, cfg: Config) -> bool:
    if not _ready(df, cfg):
        return False
    prev, last = df.iloc[-2], df.iloc[-1]
    cross_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]
    return bool(cross_down)
