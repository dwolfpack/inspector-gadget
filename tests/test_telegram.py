from unittest.mock import MagicMock, patch

import pytest

from gadget import telegram


def _idea(hook="Hook", what="What it is", why="Why you", url="https://example.com"):
    return {
        "hook": hook,
        "what_it_is": what,
        "why_you": why,
        "source_url": url,
        "prompt_to_try": "Do the thing",
        "category": "releases",
    }


def test_format_includes_every_field():
    text = telegram.format_digest([_idea()])

    assert "Hook" in text
    assert "What it is" in text
    assert "Why you" in text
    assert "https://example.com" in text
    assert "Do the thing" in text


def test_format_escapes_html_special_characters():
    text = telegram.format_digest([_idea(hook="A & B <script>")])

    assert "&amp;" in text
    assert "&lt;script&gt;" in text
    assert "<script>" not in text


def test_format_three_items_has_two_separators():
    text = telegram.format_digest([_idea(), _idea(), _idea()])

    assert text.count(telegram.SEPARATOR) == 2


def test_format_stays_within_telegram_limit():
    long_body = "x" * 5000
    items = [_idea(what=long_body, why=long_body) for _ in range(3)]

    text = telegram.format_digest(items)

    assert len(text) <= telegram.MAX_LEN


def test_format_with_fewer_than_three_adds_quiet_note():
    text = telegram.format_digest([_idea()])

    assert "quiet" in text.lower()


def test_format_with_no_items_is_quiet_morning_note():
    text = telegram.format_digest([])

    assert "quiet" in text.lower()
    assert len(text) <= telegram.MAX_LEN


def test_send_posts_to_telegram_api():
    response = MagicMock(status_code=200)
    with patch("gadget.telegram.requests.post", return_value=response) as post:
        telegram.send("hello", token="TOK", chat_id="123")

    post.assert_called_once()
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    assert url == "https://api.telegram.org/botTOK/sendMessage"
    assert payload["chat_id"] == "123"
    assert payload["text"] == "hello"
    assert payload["parse_mode"] == "HTML"


def test_send_retries_once_then_raises():
    failure = MagicMock(status_code=500, text="boom")
    with patch("gadget.telegram.requests.post", return_value=failure) as post:
        with patch("gadget.telegram.time.sleep") as sleep:
            with pytest.raises(telegram.TelegramError):
                telegram.send("hello", token="TOK", chat_id="123")

    assert post.call_count == 2
    sleep.assert_called_once_with(5)


def test_send_succeeds_on_retry():
    failure = MagicMock(status_code=500, text="boom")
    success = MagicMock(status_code=200)
    with patch("gadget.telegram.requests.post", side_effect=[failure, success]) as post:
        with patch("gadget.telegram.time.sleep"):
            telegram.send("hello", token="TOK", chat_id="123")

    assert post.call_count == 2


def test_send_error_message_never_contains_the_token():
    failure = MagicMock(status_code=401, text="unauthorized")
    with patch("gadget.telegram.requests.post", return_value=failure):
        with patch("gadget.telegram.time.sleep"):
            with pytest.raises(telegram.TelegramError) as excinfo:
                telegram.send("hello", token="SECRET_TOKEN", chat_id="123")

    assert "SECRET_TOKEN" not in str(excinfo.value)
