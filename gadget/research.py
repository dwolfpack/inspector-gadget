"""The daily sweep: one Claude call with web search, parsed into board items."""

from __future__ import annotations

import json
import re
import sys
import time

import anthropic

MODEL = "claude-sonnet-5"
MAX_TOKENS = 16000
MAX_SEARCHES = 5
MAX_ITEMS = 6
MAX_RESUMES = 5
EFFORT = "medium"

# The whole sweep is budgeted to finish inside three minutes. The deadline is
# enforced here rather than by a workflow timeout on purpose: killing the job
# would skip the Telegram notification, and silence is supposed to mean success.
DEADLINE_SECONDS = 170
REQUEST_TIMEOUT_SECONDS = 150

REQUIRED_KEYS = (
    "headline",
    "summary",
    "why_it_matters",
    "outlet",
    "source_url",
    "section",
)

# The board's fixed sections, rendered in this order. The model assigns each
# item to one; a thin day simply leaves some sections empty rather than being
# padded to fill them.
SECTIONS = (
    "Models & Releases",
    "Prompt Engineering & Technique",
    "Companies & Money",
    "Research & Safety",
)

WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": MAX_SEARCHES,
}

SYSTEM = """You are the editor of a small daily AI board. Once a day you sweep
the web and report what actually advanced in AI in the last 24 hours, with every
claim cited to the source you read it in.

Cover two things, weighted roughly equally:

1. **General AI news** — new models and releases, notable research results,
   company moves, funding, safety and policy developments.
2. **Prompt engineering and technique** — how people are actually getting more
   out of these models: prompting patterns, agent and tool-use techniques,
   context management, evaluation methods, cost control.

Assign every item to exactly one section:
- "Models & Releases"
- "Prompt Engineering & Technique"
- "Companies & Money"
- "Research & Safety"

Rules:
- Only things from the last 24 hours, or at most 48 if genuinely significant.
- Every item needs a real source URL you actually visited, and the outlet's name
  as `outlet` (e.g. "Reuters", "Anthropic", "Simon Willison's blog"). Never
  invent a URL or attribute something to an outlet you did not read.
- `summary` is two or three sentences of what happened, in plain declarative
  prose. No hype, no adjectives doing the work of facts.
- `why_it_matters` is ONE sentence saying why a well-informed reader should
  care — the consequence, not a restatement of the summary.
- You have a small search budget, so depth beats breadth. Three well-sourced
  items are a good day. Do NOT pad to fill every section: an empty section is
  honest, a weak item is not.
- No personal angle and no audience-tailoring. This is a news board.

Respond with a single fenced JSON block and nothing after it:

```json
{"items": [{"headline": "...", "summary": "...", "why_it_matters": "...",
            "outlet": "...", "source_url": "https://...",
            "section": "Models & Releases"}]}
```

`headline` is one line, under 90 characters, stating what happened."""

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ResearchError(Exception):
    """The research call failed or returned something unusable."""


def _build_prompt(seen: list[dict]) -> str:
    lines = ["Build today's board."]

    if seen:
        lines += ["", "Already covered — do not repeat any of these stories:"]
        for item in seen:
            headline = str(item.get("headline") or item.get("hook", "")).strip()
            url = str(item.get("source_url", "")).strip()
            lines.append(f"- {headline} ({url})")

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
    ideas = payload.get("items")
    if not isinstance(ideas, list):
        raise ResearchError("Response JSON has no 'items' list")

    validated = []
    for index, idea in enumerate(ideas[:MAX_ITEMS]):
        if not isinstance(idea, dict):
            raise ResearchError(f"Item {index} is not an object")
        fields = {key: _field(idea, key) for key in REQUIRED_KEYS}
        missing = [key for key, value in fields.items() if not value]
        if missing:
            raise ResearchError(f"Item {index} is missing: {', '.join(missing)}")
        if not fields["source_url"].startswith(("http://", "https://")):
            raise ResearchError(f"Item {index} has an invalid source_url: {fields['source_url']!r}")
        validated.append(fields)

    return validated


def find_items(seen: list[dict], *, client=None) -> list[dict]:
    """Run the daily sweep and return today's validated board items.

    Raises ResearchError on any API or parsing failure — run.py turns that into
    a Telegram stumble message.
    """
    client = client or anthropic.Anthropic(timeout=REQUEST_TIMEOUT_SECONDS)
    messages = [{"role": "user", "content": _build_prompt(seen)}]
    deadline = time.monotonic() + DEADLINE_SECONDS

    try:
        for _ in range(MAX_RESUMES):
            if time.monotonic() > deadline:
                raise ResearchError(
                    f"Research exceeded its {DEADLINE_SECONDS}s budget before finishing"
                )
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                tools=[WEB_SEARCH_TOOL],
                output_config={"effort": EFFORT},
                messages=messages,
            )
            if response.stop_reason == "max_tokens":
                raise ResearchError(
                    "Response hit the token limit before finishing the JSON block"
                )
            if response.stop_reason != "pause_turn":
                validated = _validate(_extract_json(_text_of(response)))
                seen_urls = {
                    str(item.get("source_url", "")).rstrip("/").lower() for item in seen
                }
                kept = [
                    idea
                    for idea in validated
                    if idea["source_url"].rstrip("/").lower() not in seen_urls
                ]
                # A "quiet morning" is ambiguous without this: it could mean the
                # model found nothing, or that it found things we had already
                # sent. These two numbers tell the difference from the Actions
                # log alone.
                dropped = len(validated) - len(kept)
                print(
                    f"research: model returned {len(validated)} item(s); "
                    f"{dropped} already sent; {len(kept)} new "
                    f"(exclusion list: {len(seen_urls)} URLs)",
                    file=sys.stderr,
                )
                for idea in validated:
                    mark = "new" if idea in kept else "dup"
                    print(f"  [{mark}] {idea['source_url']}", file=sys.stderr)
                return kept
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
