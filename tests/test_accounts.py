"""Regression tests for the per-session account refactor."""

import importlib


def _fresh_modules():
    """Reload database + accounts so they pick up the test's chdir."""
    import database
    import accounts
    importlib.reload(database)
    importlib.reload(accounts)
    return database, accounts


def test_new_account_uses_default_balance():
    _, accounts = _fresh_modules()
    acc = accounts.Account.get("Warren", "sess-1")
    assert acc.balance == accounts.DEFAULT_INITIAL_BALANCE
    assert acc.holdings == {}
    assert acc.transactions == []


def test_initial_balance_override_persists():
    _, accounts = _fresh_modules()
    acc = accounts.Account.get("Warren", "sess-1", initial_balance=50_000)
    assert acc.balance == 50_000
    # Second fetch should return the same balance — proves write_account stored it.
    again = accounts.Account.get("Warren", "sess-1")
    assert again.balance == 50_000


def test_reset_takes_strategy_and_balance():
    _, accounts = _fresh_modules()
    acc = accounts.Account.get("Warren", "sess-1")
    acc.balance = 99
    acc.holdings = {"AAPL": 5}
    acc.save()

    acc.reset("be patient", initial_balance=12_345)
    assert acc.balance == 12_345
    assert acc.holdings == {}
    assert acc.transactions == []
    assert acc.strategy == "be patient"


def test_two_sessions_are_isolated():
    _, accounts = _fresh_modules()
    a = accounts.Account.get("Warren", "alpha", initial_balance=10_000)
    b = accounts.Account.get("Warren", "beta", initial_balance=99_999)
    assert a.balance == 10_000
    assert b.balance == 99_999
    a.change_strategy("alpha-strategy")
    assert accounts.Account.get("Warren", "beta").strategy == ""


def test_cleanup_session_wipes_only_target():
    database, accounts = _fresh_modules()
    accounts.Account.get("Warren", "alpha", initial_balance=10_000).change_strategy("a")
    accounts.Account.get("Warren", "beta", initial_balance=20_000).change_strategy("b")

    database.cleanup_session("alpha")

    post_a = accounts.Account.get("Warren", "alpha")
    post_b = accounts.Account.get("Warren", "beta")
    assert post_a.strategy == ""           # cleanup → fresh default
    assert post_a.balance == accounts.DEFAULT_INITIAL_BALANCE
    assert post_b.strategy == "b"
    assert post_b.balance == 20_000


def test_db_key_format_is_session_then_name():
    database, accounts = _fresh_modules()
    acc = accounts.Account.get("Warren", "sess-X")
    assert acc.key == "sess-x:warren"
    assert database.make_key("Warren", "sess-X") == "sess-x:warren"


def test_buy_then_sell_round_trip(monkeypatch):
    database, accounts = _fresh_modules()
    # Pin share price so the test is deterministic (real call hits Polygon / random).
    import market
    monkeypatch.setattr(market, "get_share_price", lambda symbol: 100.0)
    # accounts module already imported market.get_share_price; patch its binding too.
    monkeypatch.setattr(accounts, "get_share_price", lambda symbol: 100.0)

    acc = accounts.Account.get("Warren", "sess-1", initial_balance=10_000)
    acc.buy_shares("AAPL", 10, "value play")
    acc = accounts.Account.get("Warren", "sess-1")
    assert acc.holdings == {"AAPL": 10}
    # 10 * 100 * (1 + 0.002 spread) = 1002
    assert abs(acc.balance - (10_000 - 1002)) < 0.01

    acc.sell_shares("AAPL", 4, "trim")
    acc = accounts.Account.get("Warren", "sess-1")
    assert acc.holdings == {"AAPL": 6}
    # Recovered 4 * 100 * (1 - 0.002 spread) = 399.2
    assert abs(acc.balance - (10_000 - 1002 + 399.2)) < 0.01

    assert len(acc.transactions) == 2
    assert acc.transactions[0].quantity == 10
    assert acc.transactions[1].quantity == -4


def test_log_rows_keyed_by_session(monkeypatch):
    database, accounts = _fresh_modules()
    monkeypatch.setattr(accounts, "get_share_price", lambda symbol: 50.0)

    accounts.Account.get("Warren", "alpha").buy_shares("AAPL", 1, "x")
    accounts.Account.get("Warren", "beta").buy_shares("MSFT", 1, "y")

    log_a = list(database.read_log(database.make_key("warren", "alpha"), last_n=10))
    log_b = list(database.read_log(database.make_key("warren", "beta"), last_n=10))
    assert any("AAPL" in str(r) for r in log_a)
    assert all("MSFT" not in str(r) for r in log_a)
    assert any("MSFT" in str(r) for r in log_b)
    assert all("AAPL" not in str(r) for r in log_b)
