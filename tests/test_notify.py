"""Notifier tests. Telegram network calls are not exercised."""
import pytest

from bot.notify import (
    NotifierList,
    NullNotifier,
    TelegramNotifier,
    make_notifier,
)


def test_null_notifier_does_nothing():
    n = NullNotifier()
    n.send("hello")  # should not raise


def test_telegram_requires_token():
    with pytest.raises(ValueError):
        TelegramNotifier(bot_token="", chat_id="123")


def test_telegram_requires_chat_id():
    with pytest.raises(ValueError):
        TelegramNotifier(bot_token="abc", chat_id="")


def test_telegram_throttle_drops_second_message(monkeypatch):
    n = TelegramNotifier(bot_token="x", chat_id="1", min_interval_seconds=10)

    sent = []
    def fake_send(text, level="info"):
        sent.append(text)
    # patch the actual network send by short-circuiting _throttled tracking
    monkeypatch.setattr(n, "_last_sent", 0.0)

    # first call goes through (monkeypatch requests.post to avoid network)
    class FakeResp:
        status_code = 200
        text = ""
    import sys
    import types
    fake_requests = types.SimpleNamespace(post=lambda *a, **k: FakeResp())
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    n.send("first")
    n.send("second")  # should be throttled
    assert n.stats()["dropped"] == 1


def test_notifier_list_fans_out():
    calls = []

    class Recorder(NullNotifier):
        def send(self, text, level="info"):
            calls.append((text, level))

    n = NotifierList([Recorder(), Recorder()])
    n.send("x", level="warning")
    assert len(calls) == 2
    assert calls[0] == ("x", "warning")


def test_make_notifier_returns_null_when_disabled():
    class Cfg:
        notifications = None
    assert isinstance(make_notifier(Cfg()), NullNotifier)


def test_make_notifier_returns_null_when_telegram_missing():
    from bot.config import NotificationConfig, TelegramConfig
    class Cfg:
        notifications = NotificationConfig(enabled=True, telegram=TelegramConfig())
    assert isinstance(make_notifier(Cfg()), NullNotifier)


def test_make_notifier_returns_telegram_when_configured():
    from bot.config import NotificationConfig, TelegramConfig
    class Cfg:
        notifications = NotificationConfig(
            enabled=True,
            telegram=TelegramConfig(bot_token="t", chat_id="1"),
        )
    assert isinstance(make_notifier(Cfg()), TelegramNotifier)