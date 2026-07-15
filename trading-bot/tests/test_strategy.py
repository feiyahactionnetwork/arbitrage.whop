import pandas as pd

import strategy


def _df(closes):
    return pd.DataFrame({
        "open": closes,
        "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes],
        "close": closes,
        "volume": [10.0] * len(closes),
    })


def test_entry_signal_fires_on_bullish_reversal(cfg_factory):
    cfg = cfg_factory()
    # Downtrend long enough to seed EMAs bearish, then a sharp reversal up.
    closes = [100, 98, 96, 94, 92, 90, 88, 86, 84, 82, 80, 78, 76, 74, 72,
              80, 90, 100, 110, 120, 130, 140]
    indicators = strategy.compute_indicators(_df(closes), cfg)
    fired = [i for i in range(len(indicators)) if strategy.entry_signal(indicators.iloc[: i + 1], cfg)]
    assert fired, "expected the reversal to trigger at least one entry signal"


def test_no_entry_signal_in_persistent_downtrend(cfg_factory):
    cfg = cfg_factory()
    closes = [100 - i for i in range(30)]
    indicators = strategy.compute_indicators(_df(closes), cfg)
    assert not any(
        strategy.entry_signal(indicators.iloc[: i + 1], cfg) for i in range(len(indicators))
    )


def test_no_entry_signal_when_rsi_filter_fails(cfg_factory):
    # rsi_entry_min set above 100 makes the RSI condition impossible, so an
    # otherwise-valid EMA crossover + uptrend must never fire.
    cfg = cfg_factory(rsi_entry_min=200.0)
    closes = [100, 98, 96, 94, 92, 90, 88, 86, 84, 82, 80, 78, 76, 74, 72,
              80, 90, 100, 110, 120, 130, 140]
    indicators = strategy.compute_indicators(_df(closes), cfg)
    assert not any(
        strategy.entry_signal(indicators.iloc[: i + 1], cfg) for i in range(len(indicators))
    )


def test_exit_signal_fires_on_bearish_reversal(cfg_factory):
    cfg = cfg_factory()
    closes = [80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100, 90, 80, 70, 60]
    indicators = strategy.compute_indicators(_df(closes), cfg)
    fired = [i for i in range(len(indicators)) if strategy.exit_signal(indicators.iloc[: i + 1], cfg)]
    assert fired, "expected the downturn to trigger at least one exit signal"


def test_signals_are_false_without_enough_history(cfg_factory):
    cfg = cfg_factory(ema_trend=200)  # requires far more rows than provided
    closes = [100, 101, 102, 103, 104]
    indicators = strategy.compute_indicators(_df(closes), cfg)
    assert strategy.entry_signal(indicators, cfg) is False
    assert strategy.exit_signal(indicators, cfg) is False
