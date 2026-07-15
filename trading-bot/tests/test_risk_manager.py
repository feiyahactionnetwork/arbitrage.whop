import risk_manager
from state_store import StateStore


def test_position_size_matches_risk_amount_over_stop_distance():
    qty = risk_manager.position_size(equity=1000, entry_price=100, stop_price=98, risk_pct=0.01)
    # risk_amount = 10, per-unit risk = 2 -> qty = 5
    assert abs(qty - 5.0) < 1e-9


def test_position_size_capped_by_available_equity():
    # risk math alone would ask for more than the account can afford; spot has no leverage.
    qty = risk_manager.position_size(equity=100, entry_price=100, stop_price=50, risk_pct=0.5)
    assert qty * 100 <= 100 + 1e-9


def test_position_size_zero_when_stop_equals_entry():
    assert risk_manager.position_size(1000, 100, 100, 0.01) == 0.0


def test_daily_loss_limit_halts_and_blocks_new_trades(tmp_path, cfg_factory):
    cfg = cfg_factory(max_daily_loss_pct=0.03)
    state = StateStore(str(tmp_path / "state.db"))
    state.get_today_stats(starting_equity=1000)
    state.record_trade_pnl(-31)  # worse than -3% of 1000

    assert risk_manager.daily_loss_limit_hit(state, cfg, starting_equity=1000)
    assert state.is_halted_today()
    assert risk_manager.can_open_new_trade(state, cfg, starting_equity=1000) == "daily loss limit reached"


def test_daily_loss_within_limit_does_not_halt(tmp_path, cfg_factory):
    cfg = cfg_factory(max_daily_loss_pct=0.03)
    state = StateStore(str(tmp_path / "state.db"))
    state.get_today_stats(starting_equity=1000)
    state.record_trade_pnl(-10)  # within -3% of 1000

    assert not risk_manager.daily_loss_limit_hit(state, cfg, starting_equity=1000)


def test_cooldown_blocks_new_trade_until_it_expires(tmp_path, cfg_factory):
    cfg = cfg_factory(cooldown_minutes=30)
    state = StateStore(str(tmp_path / "state.db"))
    risk_manager.start_cooldown(state, cfg)
    assert risk_manager.in_cooldown(state)
    assert risk_manager.can_open_new_trade(state, cfg, starting_equity=1000) == "in post-trade cooldown"


def test_can_open_new_trade_blocked_when_position_already_open(tmp_path, cfg_factory):
    cfg = cfg_factory()
    state = StateStore(str(tmp_path / "state.db"))
    state.open_position("BTCUSDT", entry_price=100.0, quantity=1.0, stop_price=98.0, take_profit_price=104.0)
    assert risk_manager.can_open_new_trade(state, cfg, starting_equity=1000) == "position already open"


def test_can_open_new_trade_blocked_when_max_trades_per_day_reached(tmp_path, cfg_factory):
    cfg = cfg_factory(max_trades_per_day=2)
    state = StateStore(str(tmp_path / "state.db"))
    state.get_today_stats(starting_equity=1000)
    state.record_trade_pnl(5)
    state.record_trade_pnl(5)
    assert risk_manager.can_open_new_trade(state, cfg, starting_equity=1000) == "max trades per day reached"


def test_can_open_new_trade_allowed_when_nothing_blocks_it(tmp_path, cfg_factory):
    cfg = cfg_factory()
    state = StateStore(str(tmp_path / "state.db"))
    assert risk_manager.can_open_new_trade(state, cfg, starting_equity=1000) is None
