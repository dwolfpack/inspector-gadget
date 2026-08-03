"""Rendering the digest and delivering it to Telegram."""

from __future__ import annotations

import html
import time

import requests

MAX_LEN = 4096
SEPARATOR = "\n\n————————\n\n"
HEADER = "<b>🕵️ Inspector Gadget</b>\n\n"
QUIET_NOTE = "\n\n<i>Quiet morning — that's everything worth flagging.</i>"
EMPTY_MESSAGE = (
    HEADER + "<i>Quiet morning — nothing new worth flagging today.</i>"
)

# Progressively tighter body caps, tried in order until the message fits.
_BODY_CAPS = (600, 400, 250, 150, 80)

OVERFLOW_MESSAGE = (
    HEADER + "<i>Today's ideas were too long to send. "
    "Check the workflow logs for the raw digest.</i>"
)


class TelegramError(Exception):
    """Delivery to Telegram failed."""


def _redact(text: str, token: str) -> str:
    """Never let the bot token reach an exception string — these land in CI logs."""
    return text.replace(token, "***") if token else text


def _esc(value: str) -> str:
    return html.escape(str(value), quote=False)


def _esc_attr(value: str) -> str:
    """Escape a value for use inside a double-quoted HTML attribute."""
    return html.escape(str(value), quote=True)


def _clip(value: str, cap: int) -> str:
    value = str(value).strip()
    if len(value) <= cap:
        return value
    return value[: cap - 1].rstrip() + "…"


def _render_item(item: dict, cap: int) -> str:
    return (
        f"<b>{_esc(_clip(item['hook'], 120))}</b>\n"
        f"{_esc(_clip(item['what_it_is'], cap))}\n"
        f"<i>{_esc(_clip(item['why_you'], cap))}</i>\n"
        f"<a href=\"{_esc_attr(_clip(item['source_url'], 300))}\">source</a>\n"
        f"<pre>{_esc(_clip(item['prompt_to_try'], cap * 2))}</pre>"
    )


def _render(items: list[dict], cap: int) -> str:
    body = SEPARATOR.join(_render_item(item, cap) for item in items)
    text = HEADER + body
    if len(items) < 3:
        text += QUIET_NOTE
    return text


def format_digest(items: list[dict]) -> str:
    """Render ideas as Telegram HTML, guaranteed to fit within MAX_LEN.

    Bodies are clipped progressively rather than the whole message being cut,
    so an over-long model response degrades into shorter summaries instead of a
    truncated final item. Every rendered field has its own cap, so even a
    maximally-clipped item can never emit a partial tag or entity — if nothing
    fits, a short static (and valid-HTML) overflow message is returned instead
    of slicing raw characters off the rendered text.
    """
    if not items:
        return EMPTY_MESSAGE

    for count in range(len(items), 0, -1):
        for cap in _BODY_CAPS:
            text = _render(items[:count], cap)
            if len(text) <= MAX_LEN:
                return text

    return OVERFLOW_MESSAGE


def send(text: str, *, token: str, chat_id: str) -> None:
    """POST the message to Telegram, retrying once before giving up.

    The token is never included in the raised error — this exception text can
    end up in CI logs.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    last_status = None
    last_body = ""
    for attempt in range(2):
        if attempt:
            time.sleep(5)
        try:
            response = requests.post(url, json=payload, timeout=30)
        except requests.RequestException as exc:
            last_status, last_body = "network", str(exc)
            continue
        if response.status_code == 200:
            return
        last_status, last_body = response.status_code, response.text

    safe_body = _redact(last_body, token)[:200]
    raise TelegramError(
        f"Telegram sendMessage failed after 2 attempts "
        f"(status={last_status}): {safe_body}"
    )
