from unittest.mock import MagicMock, patch

import pytest
import requests

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


def test_send_network_error_never_contains_the_token():
    # requests' exception strings routinely embed the full request URL,
    # including the bot token (e.g. "Max retries exceeded with url:
    # /botSECRET_TOKEN/sendMessage"). That must never reach the raised error.
    error = requests.ConnectionError(
        "Max retries exceeded with url: /botSECRET_TOKEN/sendMessage"
    )
    with patch("gadget.telegram.requests.post", side_effect=error):
        with patch("gadget.telegram.time.sleep"):
            with pytest.raises(telegram.TelegramError) as excinfo:
                telegram.send("hello", token="SECRET_TOKEN", chat_id="123")

    assert "SECRET_TOKEN" not in str(excinfo.value)


def test_format_handles_very_long_hook_without_exceeding_max_len():
    text = telegram.format_digest([_idea(hook="x" * 5000)])

    assert len(text) <= telegram.MAX_LEN


def test_format_handles_very_long_prompt_without_exceeding_max_len():
    idea = _idea()
    idea["prompt_to_try"] = "x" * 5000

    text = telegram.format_digest([idea])

    assert len(text) <= telegram.MAX_LEN


def test_format_never_ends_mid_tag():
    # An uncapped source_url pushes the rendered item past MAX_LEN even at the
    # tightest body cap; the old raw [:MAX_LEN] slice would land inside the
    # <a href="..."> tag and cut it in half.
    idea = _idea(url="https://example.com/" + "x" * 5000)

    text = telegram.format_digest([idea])

    assert text.count("<") == text.count(">")


def test_format_escapes_quotes_in_source_url():
    text = telegram.format_digest([_idea(url='https://example.com/"onmouseover=alert(1)')])

    assert 'href="https://example.com/&quot;onmouseover=alert(1)"' in text
    # No raw quote may appear inside the href attribute value (which would
    # terminate the attribute early and break out into the surrounding HTML).
    href_start = text.index('href="') + len('href="')
    href_end = text.index('"', href_start)
    assert '"' not in text[href_start:href_end]


def test_format_shows_trimmed_note_when_items_dropped_for_size():
    # Create ideas with long content that forces size-based dropping.
    # When not all items fit, the message should say so explicitly,
    # not misleadingly claim it's a "quiet morning with everything worth flagging".
    long_body = "x" * 5000
    # Many items with long content should trigger dropping due to size limits
    items = [_idea(what=long_body, why=long_body) for _ in range(50)]

    text = telegram.format_digest(items)

    # Count rendered items by counting <a href occurrences
    num_rendered = text.count("<a href")

    # With 50 items of this much content, not all will fit
    assert num_rendered < 50, f"Expected fewer than 50 items; got {num_rendered}"

    # Message should contain trimmed note, not quiet-morning claim
    assert "trimmed" in text.lower()
    assert "everything worth flagging" not in text


def test_format_board_renders_headlines_and_a_link():
    items = [
        {"headline": "A thing happened", "outlet": "Reuters"},
        {"headline": "R&D <spending> up", "outlet": "The Information"},
    ]
    text = telegram.format_board("2026-08-07", items)

    assert "A thing happened" in text
    assert "R&amp;D &lt;spending&gt; up" in text
    assert "<spending>" not in text
    assert telegram.SITE_URL in text
    assert "Read all 2 items" in text
    assert len(text) <= telegram.MAX_LEN


def test_format_board_with_no_items_says_so_and_still_links():
    text = telegram.format_board("2026-08-07", [])

    assert "nothing cleared the bar" in text.lower()
    assert telegram.SITE_URL in text


def test_format_board_sheds_items_rather_than_slicing_html():
    items = [{"headline": "x" * 300, "outlet": "y" * 80}] * 60
    text = telegram.format_board("2026-08-07", items)

    assert len(text) <= telegram.MAX_LEN
    assert text.count("<") == text.count(">")
    # The count still reflects what the board actually holds, not what fit.
    assert "Read all 60 items" in text
