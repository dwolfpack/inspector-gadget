import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from gadget import research


def _idea(headline="Headline"):
    return {
        "headline": headline,
        "summary": "What happened, in two sentences.",
        "why_it_matters": "Why a reader should care.",
        "outlet": "Reuters",
        "source_url": "https://example.com",
        "section": "Models & Releases",
    }


def _response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
    )


def _client(*responses):
    client = MagicMock()
    client.messages.create.side_effect = list(responses)
    return client


def test_find_ideas_parses_a_fenced_json_block():
    payload = json.dumps({"items": [_idea("A"), _idea("B"), _idea("C")]})
    client = _client(_response(f"Here you go:\n```json\n{payload}\n```"))

    ideas = research.find_items([], client=client)

    assert [item["headline"] for item in ideas] == ["A", "B", "C"]


def test_find_ideas_parses_bare_json():
    payload = json.dumps({"items": [_idea("A")]})
    client = _client(_response(payload))

    ideas = research.find_items([], client=client)

    assert len(ideas) == 1


def test_find_ideas_uses_the_configured_model_and_web_search():
    payload = json.dumps({"items": [_idea()]})
    client = _client(_response(payload))

    research.find_items([], client=client)

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["tools"] == [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": research.MAX_SEARCHES,
        }
    ]
    assert kwargs["output_config"]["effort"] == research.EFFORT


def test_the_search_budget_fits_inside_three_minutes():
    # The whole point of these two numbers is that a morning digest lands
    # quickly; if someone raises them, this is the reminder to re-time it.
    assert research.MAX_SEARCHES <= 5
    assert research.DEADLINE_SECONDS <= 180


def test_find_ideas_gives_up_when_the_deadline_passes(monkeypatch):
    payload = json.dumps({"items": [_idea()]})
    client = _client(_response("searching...", stop_reason="pause_turn"), _response(payload))

    # First check passes, second is past the budget.
    ticks = iter([0, 0, research.DEADLINE_SECONDS + 1])
    monkeypatch.setattr(research.time, "monotonic", lambda: next(ticks))

    with pytest.raises(research.ResearchError) as excinfo:
        research.find_items([], client=client)

    assert "budget" in str(excinfo.value)
    assert client.messages.create.call_count == 1


def test_find_ideas_sends_seen_urls_as_exclusions():
    payload = json.dumps({"items": [_idea()]})
    client = _client(_response(payload))
    seen = [{"headline": "Old thing", "source_url": "https://old.example"}]

    research.find_items(seen, client=client)

    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "https://old.example" in prompt
    assert "Old thing" in prompt


def test_find_ideas_resumes_on_pause_turn():
    payload = json.dumps({"items": [_idea()]})
    client = _client(_response("searching...", stop_reason="pause_turn"), _response(payload))

    ideas = research.find_items([], client=client)

    assert len(ideas) == 1
    assert client.messages.create.call_count == 2


def test_find_ideas_raises_on_unparseable_response():
    client = _client(_response("I could not find anything useful today."))

    with pytest.raises(research.ResearchError):
        research.find_items([], client=client)


def test_find_ideas_raises_when_an_idea_is_missing_a_key():
    broken = _idea()
    del broken["summary"]
    payload = json.dumps({"items": [broken]})
    client = _client(_response(payload))

    with pytest.raises(research.ResearchError):
        research.find_items([], client=client)


def test_find_ideas_returns_empty_list_when_model_finds_nothing():
    payload = json.dumps({"items": []})
    client = _client(_response(payload))

    assert research.find_items([], client=client) == []


def test_find_items_caps_at_max_items():
    payload = json.dumps({"items": [_idea(str(i)) for i in range(9)]})
    client = _client(_response(payload))

    assert len(research.find_items([], client=client)) == research.MAX_ITEMS


def test_find_ideas_raises_research_error_on_unexpected_response_shape():
    # Response has no usable `content` at all -- _text_of would raise
    # AttributeError if unguarded. find_ideas must still raise ResearchError.
    weird_response = SimpleNamespace(stop_reason="end_turn")
    client = _client(weird_response)

    with pytest.raises(research.ResearchError):
        research.find_items([], client=client)


def test_find_ideas_raises_when_source_url_is_null():
    broken = _idea()
    broken["source_url"] = None
    payload = json.dumps({"items": [broken]})
    client = _client(_response(payload))

    with pytest.raises(research.ResearchError, match="source_url"):
        research.find_items([], client=client)


def test_find_ideas_raises_when_hook_is_a_list():
    broken = _idea()
    broken["headline"] = []
    payload = json.dumps({"items": [broken]})
    client = _client(_response(payload))

    with pytest.raises(research.ResearchError, match="headline"):
        research.find_items([], client=client)


def test_find_ideas_raises_after_exhausting_resumes():
    responses = [_response("searching...", stop_reason="pause_turn") for _ in range(research.MAX_RESUMES)]
    client = _client(*responses)

    with pytest.raises(research.ResearchError):
        research.find_items([], client=client)

    assert client.messages.create.call_count == research.MAX_RESUMES


def test_find_ideas_raises_a_clear_error_on_max_tokens_stop():
    client = _client(_response("partial output, no closing fence", stop_reason="max_tokens"))

    with pytest.raises(research.ResearchError, match="token limit"):
        research.find_items([], client=client)


def test_find_ideas_drops_ideas_that_duplicate_a_seen_source_url():
    seen = [{"headline": "Old thing", "source_url": "https://example.com/a"}]
    dup = _idea("Duplicate")
    dup["source_url"] = "https://EXAMPLE.COM/A/"
    fresh = _idea("Fresh")
    fresh["source_url"] = "https://example.com/b"
    payload = json.dumps({"items": [dup, fresh]})
    client = _client(_response(payload))

    ideas = research.find_items(seen, client=client)

    assert [item["headline"] for item in ideas] == ["Fresh"]


def test_find_ideas_raises_when_source_url_is_not_http():
    broken = _idea()
    broken["source_url"] = "javascript:alert(1)"
    payload = json.dumps({"items": [broken]})
    client = _client(_response(payload))

    with pytest.raises(research.ResearchError, match="source_url"):
        research.find_items([], client=client)


def test_find_ideas_preserves_conversation_across_resume():
    payload = json.dumps({"items": [_idea()]})
    responses = [_response("searching...", stop_reason="pause_turn"), _response(payload)]

    # `messages` is mutated in place and appended to on each resume, so
    # MagicMock's call_args_list would hold references to the *same* list
    # object for every call. Snapshot the length/shape at call time instead.
    seen_message_lists = []

    def _create(**kwargs):
        messages = kwargs["messages"]
        seen_message_lists.append((len(messages), messages[-1]["role"]))
        return responses.pop(0)

    client = MagicMock()
    client.messages.create.side_effect = _create

    research.find_items([], client=client)

    first_len, _ = seen_message_lists[0]
    second_len, second_last_role = seen_message_lists[1]

    assert second_len > first_len
    assert second_last_role == "assistant"


def test_find_ideas_logs_the_dedupe_counts(capsys):
    payload = json.dumps({"items": [_idea("A"), _idea("B")]})
    # Both share the same _idea() source_url, and it is already in `seen`,
    # so both should be reported as duplicates and nothing returned.
    client = _client(_response(payload))
    seen = [{"hook": "old", "source_url": "https://example.com"}]

    kept = research.find_items(seen, client=client)

    err = capsys.readouterr().err
    assert kept == []
    assert "model returned 2 item(s)" in err
    assert "2 already sent" in err
    assert "0 new" in err
    assert "[dup] https://example.com" in err


def test_find_ideas_logs_new_ideas_as_new(capsys):
    payload = json.dumps({"items": [_idea("A")]})
    client = _client(_response(payload))

    research.find_items([], client=client)

    err = capsys.readouterr().err
    assert "1 new" in err
    assert "[new] https://example.com" in err


def test_effort_is_medium():
    # Dropped to "low" for a 3-minute budget, which produced two consecutive
    # empty digests. Pin the setting so a change is deliberate.
    assert research.EFFORT == "medium"
