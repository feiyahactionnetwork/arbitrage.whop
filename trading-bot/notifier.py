"""Best-effort webhook alerts (Slack/Discord-style incoming webhook).
Never let a notification failure interrupt trading logic.
"""
import logging

import requests

log = logging.getLogger("bot.notify")


def notify(webhook_url: str, message: str) -> None:
    log.info("ALERT: %s", message)
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"text": message}, timeout=5)
    except requests.RequestException as exc:
        log.warning("Webhook notification failed: %s", exc)
