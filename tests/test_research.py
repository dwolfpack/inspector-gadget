import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from gadget import research


def _idea(hook="Hook"):
    return {
        "hook": hook,
        "what_it_is": "what",
        "why_you": "why",
        "source_url": "https://example.com",
        "prompt_to_try": "prompt",
        "category": "releases",
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
    payload = json.dumps({"ideas": [_idea("A"), _idea("B"), _idea("C")]})
    client = _client(_response(f"Here you go:\n```json\n{payload}\n```"))

    ideas = research.find_ideas("profile", [], client=client)

    assert [item["hook"] for item in ideas] == ["A", "B", "C"]


def test_find_ideas_parses_bare_json():
    payload = json.dumps({"ideas": [_idea("A")]})
    client = _client(_response(payload))

    ideas = research.find_ideas("profile", [], client=client)

    assert len(ideas) == 1


def test_find_ideas_uses_the_configured_model_and_web_search():
    payload = json.dumps({"ideas": [_idea()]})
    client = _client(_response(payload))

    research.find_ideas("profile", [], client=client)

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["tools"] == [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}
    ]


def test_find_ideas_sends_seen_urls_as_exclusions():
    payload = json.dumps({"ideas": [_idea()]})
    client = _client(_response(payload))
    seen = [{"hook": "Old thing", "source_url": "https://old.example"}]

    research.find_ideas("profile", seen, client=client)

    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "https://old.example" in prompt
    assert "Old thing" in prompt


def test_find_ideas_resumes_on_pause_turn():
    payload = json.dumps({"ideas": [_idea()]})
    client = _client(_response("searching...", stop_reason="pause_turn"), _response(payload))

    ideas = research.find_ideas("profile", [], client=client)

    assert len(ideas) == 1
    assert client.messages.create.call_count == 2


def test_find_ideas_raises_on_unparseable_response():
    client = _client(_response("I could not find anything useful today."))

    with pytest.raises(research.ResearchError):
        research.find_ideas("profile", [], client=client)


def test_find_ideas_raises_when_an_idea_is_missing_a_key():
    broken = _idea()
    del broken["prompt_to_try"]
    payload = json.dumps({"ideas": [broken]})
    client = _client(_response(payload))

    with pytest.raises(research.ResearchError):
        research.find_ideas("profile", [], client=client)


def test_find_ideas_returns_empty_list_when_model_finds_nothing():
    payload = json.dumps({"ideas": []})
    client = _client(_response(payload))

    assert research.find_ideas("profile", [], client=client) == []


def test_find_ideas_caps_at_three_items():
    payload = json.dumps({"ideas": [_idea(str(i)) for i in range(6)]})
    client = _client(_response(payload))

    assert len(research.find_ideas("profile", [], client=client)) == 3
