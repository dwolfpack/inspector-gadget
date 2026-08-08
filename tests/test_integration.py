"""End-to-end wiring, with only the network boundary faked.

Every other test module mocks sibling modules, so nothing exercises the real
seams between them: parsed research output feeding the real renderer, the
rendered payload reaching the HTTP layer, the archive coming back as tomorrow's
exclusion list, and the static site being generated from that same archive.
This module runs the real code for all of it and stubs only two things — the
Anthropic client and `requests.post`.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gadget import history, run, site

MODEL_ITEMS = [
    {
        "headline": "Anthropic ships subagents in Claude Code",
        "summary": "Work can now fan out to fresh contexts. Reviews happen between them.",
        "why_it_matters": "Cuts the cost of long refactors.",
        "outlet": "Anthropic",
        "source_url": "https://example.com/subagents",
        "section": "Models & Releases",
    },
    {
        "headline": "A prompting pattern for <agent> loops",
        "summary": "Someone published a rubric-graded eval loop.",
        "why_it_matters": "Makes agent output measurable rather than vibes.",
        "outlet": "Simon Willison's blog",
        "source_url": "https://example.com/eval-loop",
        "section": "Prompt Engineering & Technique",
    },
]


def _api_response(items):
    payload = json.dumps({"items": items})
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=f"```json\n{payload}\n```")],
        stop_reason="end_turn",
    )


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Point history and the generated site at scratch directories."""
    monkeypatch.setattr(history, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(site, "DOCS", tmp_path / "docs")
    return tmp_path / "history"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")


def _run_one_morning(items, posts):
    client = MagicMock()
    client.messages.create.return_value = _api_response(items)

    def capture(url, **kwargs):
        posts.append(kwargs["json"])
        return MagicMock(status_code=200)

    with patch("gadget.research.anthropic.Anthropic", return_value=client), \
         patch("gadget.telegram.requests.post", side_effect=capture):
        return run.main([])


def test_one_morning_end_to_end(archive, tmp_path):
    posts = []

    code = _run_one_morning(MODEL_ITEMS, posts)

    assert code == 0
    assert len(posts) == 1
    payload = posts[0]

    # The real renderer produced the real Telegram payload.
    assert payload["parse_mode"] == "HTML"
    assert payload["chat_id"] == "123"
    assert len(payload["text"]) <= 4096
    assert "Anthropic ships subagents" in payload["text"]
    assert "inspector-gadget" in payload["text"]  # link to the board

    # Angle brackets in model output survived as entities, not raw markup.
    assert "&lt;agent&gt;" in payload["text"]
    assert "<agent>" not in payload["text"]

    # Both items were archived with the timestamp history adds.
    archived = history.load_recent(days=30, history_dir=archive)
    assert {i["headline"] for i in archived} == {
        "Anthropic ships subagents in Claude Code",
        "A prompting pattern for <agent> loops",
    }
    assert all(i["sent_at"] for i in archived)

    # And the static site was generated from that same archive.
    index = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert "Anthropic ships subagents" in index
    assert "Models &amp; Releases" in index
    assert "Prompt Engineering &amp; Technique" in index
    assert "&lt;agent&gt;" in index and "<agent>" not in index
    assert 'href="https://example.com/subagents"' in index
    # Sections are numbered, and the header carries honest counts.
    assert "01" in index and "02" in index
    assert "searches run" in index

    archive_index = (tmp_path / "docs" / "archive" / "index.html").read_text(encoding="utf-8")
    assert "1 day on record" in archive_index


def test_second_morning_does_not_repeat_the_first(archive):
    posts = []
    assert _run_one_morning(MODEL_ITEMS, posts) == 0

    # The model returns yesterday's first story again — trailing slash and
    # different host casing — plus something genuinely new.
    repeat = dict(MODEL_ITEMS[0], source_url="https://EXAMPLE.com/subagents/")
    fresh = {
        "headline": "Something new today",
        "summary": "A fresh find.",
        "why_it_matters": "It changes the calculus.",
        "outlet": "Reuters",
        "source_url": "https://example.com/new",
        "section": "Companies & Money",
    }
    assert _run_one_morning([repeat, fresh], posts) == 0

    second = posts[1]["text"]
    assert "Something new today" in second
    assert "Anthropic ships subagents" not in second


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

    assert code == 1
    assert len(posts) == 1
    assert "stumbled" in posts[0]["text"].lower()
    assert "<b>useful</b>" not in posts[0]["text"]
    assert history.load_recent(days=30, history_dir=archive) == []
