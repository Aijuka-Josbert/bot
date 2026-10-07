"""Pluggable notifiers. Telegram by default, no-op if disabled."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


# --- base ---

class Notifier:
    """Base class. Implementations must override send()."""

    def send(self, text: str, level: str = "info") -> None:
        raise NotImplementedError


class NullNotifier(Notifier):
    """Does nothing. Used when notifications are disabled."""

    def send(self, text: str, level: str = "info") -> None:
        pass


# --- telegram ---

_EMOJI = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}


class TelegramNotifier(Notifier):
    """
    Posts messages to a Telegram chat via the Bot API.

    - min_interval_seconds throttles bursts (default 5s).
    - fail-open: network errors are logged, never raised.
    """

    API = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        min_interval_seconds: float = 5.0,
    ) -> None:
        if not bot_token:
            raise ValueError("telegram bot_token is required")
        if not chat_id:
            raise ValueError("telegram chat_id is required")
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.min_interval = float(min_interval_seconds)
        self._last_sent: float = 0.0
        self._dropped = 0

    def _throttled(self) -> bool:
        if self.min_interval <= 0:
            return False
        return (time.monotonic() - self._last_sent) < self.min_interval

    def send(self, text: str, level: str = "info") -> None:
        if self._throttled():
            self._dropped += 1
            return

        emoji = _EMOJI.get(level, "")
        payload = {
            "chat_id": self.chat_id,
            "text": f"{emoji} {text}".strip(),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        url = self.API.format(token=self.bot_token)

        try:
            import requests
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code >= 400:
                logger.error("telegram send failed: %s %s", r.status_code, r.text[:200])
            else:
                self._last_sent = time.monotonic()
        except Exception as e:
            logger.error("telegram send raised: %s", e)

    def stats(self) -> dict:
        return {"dropped": self._dropped}


# --- composite ---

class NotifierList(Notifier):
    """Fan out to multiple notifiers. Used if you add email/Slack later."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    def send(self, text: str, level: str = "info") -> None:
        for n in self.notifiers:
            try:
                n.send(text, level)
            except Exception as e:
                logger.error("notifier %s failed: %s", type(n).__name__, e)


# --- factory ---

def make_notifier(cfg) -> Notifier:
    """
    Build a notifier from the loaded Config.

    Reads cfg.notifications (added in this stage). Returns NullNotifier if
    notifications are disabled or misconfigured.
    """
    n = getattr(cfg, "notifications", None)
    if n is None or not n.enabled:
        return NullNotifier()

    tg = getattr(n, "telegram", None)
    if tg is None or not tg.bot_token or not tg.chat_id:
        logger.warning("notifications enabled but telegram not configured; disabling")
        return NullNotifier()

    logger.info("telegram notifications enabled (chat %s)", tg.chat_id)
    return TelegramNotifier(
        bot_token=tg.bot_token,
        chat_id=tg.chat_id,
        min_interval_seconds=n.min_interval_seconds,
    )