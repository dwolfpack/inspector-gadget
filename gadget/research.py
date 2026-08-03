"""The daily sweep: one Claude call with web search, parsed into ideas."""

from __future__ import annotations

import json
import re

import anthropic

MODEL = "claude-sonnet-5"
MAX_TOKENS = 8000
MAX_SEARCHES = 8
MAX_IDEAS = 3
MAX_RESUMES = 5

REQUIRED_KEYS = (
    "hook",
    "what_it_is",
    "why_you",
    "source_url",
    "prompt_to_try",
    "category",
)

WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": MAX_SEARCHES,
}

SYSTEM = """You are Inspector Gadget, a daily scout for one person named Dror.

Every morning you sweep the web and return the three most useful new things he
could do with Claude today. You are writing for someone who will act on this
over coffee, not read it as news.

Sweep across four areas, and prefer a mix rather than three items from one:
1. New Claude features and releases — Anthropic's changelog and news, Claude
   Code releases, new models, new skills, plugins, and MCP servers.
2. Community projects and workflows — what people are actually building and
   sharing on Reddit, Hacker News, X, GitHub, and YouTube.
3. Ideas connected to Dror's own projects, as described in his profile.
4. Prompting and technique tips — prompting patterns, subagent tricks, context
   management, cost-saving techniques.

Rules:
- Favour things from the last 48 hours. Older material only if it is genuinely
  excellent and he plausibly has not seen it.
- Every item needs a real source URL you actually visited. Never invent one.
- `why_you` must connect the item to Dror specifically, not to developers in
  general. If you cannot make that connection honestly, pick a different item.
- `prompt_to_try` is a prompt he can paste into Claude verbatim to try the idea
  right now. Make it concrete and specific to him.
- Quality beats quantity. Returning two strong items is better than three with
  one filler. Returning zero is acceptable on a genuinely dead news day.

Respond with a single fenced JSON block and nothing after it:

```json
{"ideas": [{"hook": "...", "what_it_is": "...", "why_you": "...",
            "source_url": "...", "prompt_to_try": "...",
            "category": "releases|community|projects|technique"}]}
```

`hook` is one line, under 80 characters. `what_it_is` and `why_you` are each
one to three sentences."""

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ResearchError(Exception):
    """The research call failed or returned something unusable."""


def _build_prompt(profile: str, seen: list[dict]) -> str:
    lines = [
        "Here is who you are scouting for:",
        "",
        profile.strip(),
        "",
        "Find today's three ideas.",
    ]

    if seen:
        lines += ["", "Already sent — do not repeat any of these:"]
        for item in seen:
            hook = str(item.get("hook", "")).strip()
            url = str(item.get("source_url", "")).strip()
            lines.append(f"- {hook} ({url})")

    return "\n".join(lines)


def _text_of(response) -> str:
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )


def _extract_json(text: str) -> dict:
    match = _FENCE.search(text)
    candidate = match.group(1) if match else None

    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ResearchError(f"No JSON object in response: {text[:300]!r}")
        candidate = text[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ResearchError(f"Response JSON did not parse: {exc}") from exc


def _field(idea: dict, key: str) -> str:
    value = idea.get(key)
    if value is None or isinstance(value, (list, dict, bool)):
        return ""
    return str(value).strip()


def _validate(payload: dict) -> list[dict]:
    ideas = payload.get("ideas")
    if not isinstance(ideas, list):
        raise ResearchError("Response JSON has no 'ideas' list")

    validated = []
    for index, idea in enumerate(ideas[:MAX_IDEAS]):
        if not isinstance(idea, dict):
            raise ResearchError(f"Idea {index} is not an object")
        fields = {key: _field(idea, key) for key in REQUIRED_KEYS}
        missing = [key for key, value in fields.items() if not value]
        if missing:
            raise ResearchError(f"Idea {index} is missing: {', '.join(missing)}")
        validated.append(fields)

    return validated


def find_ideas(profile: str, seen: list[dict], *, client=None) -> list[dict]:
    """Run the daily sweep and return up to three validated ideas.

    Raises ResearchError on any API or parsing failure — run.py turns that into
    a Telegram stumble message.
    """
    client = client or anthropic.Anthropic()
    messages = [{"role": "user", "content": _build_prompt(profile, seen)}]

    try:
        for _ in range(MAX_RESUMES):
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                tools=[WEB_SEARCH_TOOL],
                output_config={"effort": "medium"},
                messages=messages,
            )
            if response.stop_reason != "pause_turn":
                return _validate(_extract_json(_text_of(response)))
            # The server-side search loop hit its iteration cap; echo the turn
            # back and the server resumes where it left off.
            messages.append({"role": "assistant", "content": response.content})
    except ResearchError:
        raise
    except anthropic.APIError as exc:
        raise ResearchError(f"Claude API error: {exc}") from exc
    except Exception as exc:  # never let an unexpected type escape — run.py only catches ResearchError
        raise ResearchError(f"Unexpected failure during research: {exc!r}") from exc

    raise ResearchError(f"Search did not converge after {MAX_RESUMES} resumes")
