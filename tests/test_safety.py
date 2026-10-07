"""Kill switch and preflight behaviour."""


from bot.safety import KillSwitch


def test_kill_switch_absent(tmp_path):
    ks = KillSwitch(tmp_path / "KILL")
    assert ks.is_triggered() is False


def test_kill_switch_trigger_and_clear(tmp_path):
    ks = KillSwitch(tmp_path / "KILL")
    ks.trigger()
    assert ks.is_triggered() is True
    ks.clear()
    assert ks.is_triggered() is False


def test_kill_switch_clear_when_absent_is_noop(tmp_path):
    ks = KillSwitch(tmp_path / "KILL")
    ks.clear()  # should not raise
    assert ks.is_triggered() is False


def test_preflight_fails_without_api_key():
    from bot.safety import preflight_live

    class FakeClient:
        apiKey = ""
        def load_markets(self): pass
        def fetch_balance(self): return {"free": {"USDT": 100.0}}

    class FakeExchange:
        client = FakeClient()

    ok, msg = preflight_live(FakeExchange(), "BTC/USDT")
    assert ok is False
    assert "API key" in msg


def test_preflight_fails_on_low_balance():
    from bot.safety import preflight_live

    class FakeClient:
        apiKey = "abc"
        def load_markets(self): pass
        def fetch_balance(self): return {"free": {"USDT": 1.0}}

    class FakeExchange:
        client = FakeClient()

    ok, msg = preflight_live(FakeExchange(), "BTC/USDT", min_balance=10.0)
    assert ok is False
    assert "insufficient" in msg.lower()


def test_preflight_passes_with_balance():
    from bot.safety import preflight_live

    class FakeClient:
        apiKey = "abc"
        def load_markets(self): pass
        def fetch_balance(self): return {"free": {"USDT": 100.0}}

    class FakeExchange:
        client = FakeClient()

    ok, msg = preflight_live(FakeExchange(), "BTC/USDT", min_balance=10.0)
    assert ok is True
    assert "ok" in msg