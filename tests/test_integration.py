"""End-to-end wiring, with only the network boundary faked.

Every other test module mocks sibling modules, so nothing exercises the real
seams between them: research's parsed output feeding telegram's renderer,
telegram's payload actually reaching the HTTP layer, and history's archive
coming back as the next morning's exclusion list. This module runs the real
code for all of that and stubs only two things — the Anthropic client and
`requests.post`.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gadget import history, run

MODEL_IDEAS = [
    {
        "hook": "Claude Code now ships subagents",
        "what_it_is": "You can fan work out to fresh contexts & review between them.",
        "why_you": "Your <kids' games> repos are exactly this shape.",
        "source_url": "https://example.com/subagents",
        "prompt_to_try": "Split this refactor across subagents.",
        "category": "releases",
    },
    {
        "hook": "A QA harness for agent output",
        "what_it_is": "Someone published a rubric-graded eval loop.",
        "why_you": "Directly feeds your QA-for-AI thesis.",
        "source_url": "https://example.com/qa-harness",
        "prompt_to_try": "Draft a rubric for my agent's output.",
        "category": "community",
    },
]


def _api_response(ideas):
    """Shape a fake Anthropic response the way the real SDK returns one."""
    payload = json.dumps({"ideas": ideas})
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=f"```json\n{payload}\n```")],
        stop_reason="end_turn",
    )


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Point the history module at a scratch directory for the whole run."""
    monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")


def _run_one_morning(ideas, posts):
    """Run main() end-to-end against a faked model response. Returns exit code."""
    client = MagicMock()
    client.messages.create.return_value = _api_response(ideas)

    def capture(url, **kwargs):
        posts.append(kwargs["json"])
        return MagicMock(status_code=200)

    with patch("gadget.research.anthropic.Anthropic", return_value=client), \
         patch("gadget.telegram.requests.post", side_effect=capture):
        return run.main([])


def test_one_morning_end_to_end(archive):
    posts = []

    code = _run_one_morning(MODEL_IDEAS, posts)

    assert code == 0
    assert len(posts) == 1
    payload = posts[0]

    # The real renderer produced the real payload.
    assert payload["parse_mode"] == "HTML"
    assert payload["chat_id"] == "123"
    assert len(payload["text"]) <= 4096
    assert "Claude Code now ships subagents" in payload["text"]
    assert "https://example.com/qa-harness" in payload["text"]

    # Model output containing angle brackets survived as escaped entities,
    # not as raw markup Telegram would reject.
    assert "&lt;kids' games&gt;" in payload["text"]
    assert "<kids' games>" not in payload["text"]

    # Both ideas were archived, with the timestamp history adds.
    archived = history.load_recent(days=30, history_dir=archive)
    assert {item["hook"] for item in archived} == {
        "Claude Code now ships subagents",
        "A QA harness for agent output",
    }
    assert all(item["sent_at"] for item in archived)


def test_second_morning_does_not_repeat_the_first(archive):
    posts = []
    assert _run_one_morning(MODEL_IDEAS, posts) == 0

    # The model returns yesterday's first item again (trailing slash, different
    # host casing) plus something genuinely new.
    repeat = dict(MODEL_IDEAS[0], source_url="https://EXAMPLE.com/subagents/")
    fresh = {
        "hook": "Something new today",
        "what_it_is": "A fresh find.",
        "why_you": "Relevant to you.",
        "source_url": "https://example.com/new",
        "prompt_to_try": "Try this.",
        "category": "technique",
    }
    assert _run_one_morning([repeat, fresh], posts) == 0

    second = posts[1]["text"]
    assert "Something new today" in second
    assert "Claude Code now ships subagents" not in second


def test_a_broken_model_response_still_reaches_the_owner(archive):
    posts = []
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I found nothing <b>useful</b>.")],
        stop_reason="end_turn",
    )

    def capture(url, **kwargs):
        posts.append(kwargs["json"])
        return MagicMock(status_code=200)

    with patch("gadget.research.anthropic.Anthropic", return_value=client), \
         patch("gadget.telegram.requests.post", side_effect=capture):
        code = run.main([])

    # Failure is reported to the owner, loudly, and nothing is recorded as sent.
    assert code == 1
    assert len(posts) == 1
    assert "stumbled" in posts[0]["text"].lower()
    assert "<b>useful</b>" not in posts[0]["text"]
    assert history.load_recent(days=30, history_dir=archive) == []
