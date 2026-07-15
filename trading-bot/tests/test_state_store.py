from state_store import StateStore


def test_open_and_close_position_records_trade_and_pnl(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    state.open_position("BTCUSDT", entry_price=100.0, quantity=2.0, stop_price=98.0, take_profit_price=110.0)

    assert state.get_open_position() is not None

    trade = state.close_position(exit_price=110.0, exit_reason="take_profit", fee_quote=0.5)

    assert state.get_open_position() is None
    assert trade["pnl_quote"] == (110.0 - 100.0) * 2.0 - 0.5

    metrics = state.compute_metrics()
    assert metrics["total_trades"] == 1
    assert metrics["win_rate"] == 1.0
    assert metrics["fees_paid"] == 0.5


def test_metrics_track_wins_losses_and_drawdown(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))

    state.open_position("BTCUSDT", 100.0, 1.0, 98.0, 110.0)
    state.close_position(exit_price=110.0, exit_reason="take_profit")  # +10

    state.open_position("BTCUSDT", 110.0, 1.0, 108.0, 120.0)
    state.close_position(exit_price=108.0, exit_reason="stop_loss")  # -2

    metrics = state.compute_metrics()
    assert metrics["total_trades"] == 2
    assert metrics["win_rate"] == 0.5
    assert metrics["net_profit"] == 8.0
    assert metrics["max_drawdown"] == 2.0


def test_close_position_without_open_position_raises(tmp_path):
    state = StateStore(str(tmp_path / "state.db"))
    try:
        state.close_position(exit_price=100.0, exit_reason="signal_exit")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
