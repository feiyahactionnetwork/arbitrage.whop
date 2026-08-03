"""Thin wrapper around python-binance for the bits the bot needs.

Isolates the exchange SDK so strategy/risk/state code never imports
python-binance directly, and so DRY_RUN can short-circuit order
placement in one place.
"""
import logging
from decimal import ROUND_DOWN, Decimal
from typing import Optional

import pandas as pd
from binance.client import Client

from config import Config

log = logging.getLogger("bot.exchange")


class ExchangeError(RuntimeError):
    pass


class BinanceClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = Client(cfg.api_key, cfg.api_secret, testnet=cfg.use_testnet)
        self._symbol_filters: Optional[dict] = None

    # ---------- market data ----------

    def get_klines_df(self, limit: int = 300) -> pd.DataFrame:
        raw = self.client.get_klines(
            symbol=self.cfg.symbol, interval=self.cfg.interval, limit=limit
        )
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

    def get_last_price(self) -> float:
        ticker = self.client.get_symbol_ticker(symbol=self.cfg.symbol)
        return float(ticker["price"])

    # ---------- account ----------

    def get_free_balance(self, asset: str) -> float:
        if self.cfg.dry_run:
            return self.cfg.paper_equity if asset == self.cfg.quote_asset else 0.0
        bal = self.client.get_asset_balance(asset=asset)
        if bal is None:
            return 0.0
        return float(bal["free"])

    # ---------- symbol precision ----------

    def _filters(self) -> dict:
        if self._symbol_filters is None:
            info = self.client.get_symbol_info(self.cfg.symbol)
            if info is None:
                raise ExchangeError(f"Unknown symbol {self.cfg.symbol}")
            self._symbol_filters = {f["filterType"]: f for f in info["filters"]}
        return self._symbol_filters

    def round_quantity(self, quantity: float) -> float:
        step = Decimal(self._filters()["LOT_SIZE"]["stepSize"])
        q = Decimal(str(quantity)).quantize(step, rounding=ROUND_DOWN)
        return float(q)

    def min_notional(self) -> float:
        filters = self._filters()
        for key in ("MIN_NOTIONAL", "NOTIONAL"):
            if key in filters:
                return float(filters[key].get("minNotional") or filters[key].get("minNotional", 0))
        return 0.0

    # ---------- orders ----------

    def market_buy(self, quantity: float) -> dict:
        quantity = self.round_quantity(quantity)
        if quantity <= 0:
            raise ExchangeError("Computed buy quantity rounds down to zero")
        if self.cfg.dry_run:
            price = self.get_last_price()
            log.info("[DRY_RUN] market BUY %s %s @ ~%s", quantity, self.cfg.symbol, price)
            return {"status": "DRY_RUN", "side": "BUY", "executedQty": str(quantity), "price": price}
        order = self.client.order_market_buy(symbol=self.cfg.symbol, quantity=quantity)
        log.info("LIVE market BUY order placed: %s", order)
        return order

    def market_sell(self, quantity: float) -> dict:
        quantity = self.round_quantity(quantity)
        if quantity <= 0:
            raise ExchangeError("Computed sell quantity rounds down to zero")
        if self.cfg.dry_run:
            price = self.get_last_price()
            log.info("[DRY_RUN] market SELL %s %s @ ~%s", quantity, self.cfg.symbol, price)
            return {"status": "DRY_RUN", "side": "SELL", "executedQty": str(quantity), "price": price}
        order = self.client.order_market_sell(symbol=self.cfg.symbol, quantity=quantity)
        log.info("LIVE market SELL order placed: %s", order)
        return order

    def open_orders_count(self) -> int:
        if self.cfg.dry_run:
            return 0
        return len(self.client.get_open_orders(symbol=self.cfg.symbol))
