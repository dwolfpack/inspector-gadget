"""Render the archive into a static site: today's board plus every past day.

No build tooling, no framework, no JavaScript. Everything is generated from the
`history/*.jsonl` files the digest already writes, so the archive is a
by-product of data we keep anyway rather than a second source of truth.
"""

from __future__ import annotations

import html
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from gadget.research import SECTIONS

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"

TITLE = "Inspector Gadget"
TAGLINE = "What moved in AI yesterday, and how people are actually prompting these models. Read once a day, every claim cited."

STYLE = """
:root {
  --paper: #faf7f2;
  --ink: #1c1a17;
  --muted: #6b6459;
  --rule: #ddd6c9;
  --accent: #9c3d10;
  --card: #fffdf9;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #14130f;
    --ink: #ece7dd;
    --muted: #9a9284;
    --rule: #2e2b25;
    --accent: #e2833f;
    --card: #1a1814;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 17px/1.65 Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.25rem 5rem; }
.meta {
  font: 600 0.72rem/1.4 ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}
header { border-bottom: 3px double var(--rule); padding-bottom: 1.5rem; margin-bottom: 2.5rem; }
h1 {
  font-size: clamp(2.1rem, 7vw, 3.1rem);
  line-height: 1.05;
  margin: 0.6rem 0 0.5rem;
  letter-spacing: -0.02em;
}
h1 a { color: inherit; text-decoration: none; }
.tagline { color: var(--muted); font-size: 1.02rem; margin: 0 0 1.25rem; max-width: 34rem; }
.stats { display: flex; flex-wrap: wrap; gap: 1.4rem; }
.stat b { display: block; font: 700 1.35rem/1 Georgia, serif; color: var(--accent); }
.stat span { font: 600 0.66rem/1.4 ui-monospace, monospace; letter-spacing: 0.09em; text-transform: uppercase; color: var(--muted); }
section { margin: 3rem 0 0; }
.sec-head { display: flex; align-items: baseline; gap: 0.7rem; border-bottom: 1px solid var(--rule); padding-bottom: 0.4rem; }
.sec-num { font: 700 0.8rem/1 ui-monospace, monospace; color: var(--accent); }
.sec-head h2 { font-size: 1.06rem; margin: 0; letter-spacing: 0.01em; }
article {
  background: var(--card);
  border: 1px solid var(--rule);
  border-radius: 3px;
  padding: 1.2rem 1.3rem;
  margin: 1.1rem 0;
}
article h3 { font-size: 1.22rem; line-height: 1.25; margin: 0 0 0.6rem; letter-spacing: -0.01em; }
article p { margin: 0 0 0.75rem; }
.why {
  border-left: 3px solid var(--accent);
  padding: 0.15rem 0 0.15rem 0.8rem;
  color: var(--muted);
  font-style: italic;
}
.src { font: 600 0.72rem/1.4 ui-monospace, monospace; letter-spacing: 0.06em; text-transform: uppercase; }
.src a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
.src a:hover { border-bottom-color: var(--accent); }
.quiet { color: var(--muted); font-style: italic; }
nav.days { margin-top: 3.5rem; border-top: 1px solid var(--rule); padding-top: 1.2rem; }
nav.days ul { list-style: none; padding: 0; margin: 0.8rem 0 0; }
nav.days li { padding: 0.3rem 0; border-bottom: 1px dotted var(--rule); }
nav.days a { color: inherit; text-decoration: none; }
nav.days a:hover { color: var(--accent); }
nav.days .n { font: 600 0.72rem ui-monospace, monospace; color: var(--muted); float: right; }
footer { margin-top: 4rem; border-top: 1px solid var(--rule); padding-top: 1.2rem; }
footer p { color: var(--muted); font-size: 0.86rem; }
footer a { color: var(--accent); }
"""


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def _pretty_date(day: str) -> str:
    """2026-08-05 -> Wednesday, 5 August 2026. Falls back to the raw string."""
    try:
        return datetime.strptime(day, "%Y-%m-%d").strftime("%A, %-d %B %Y")
    except ValueError:
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d")
            return f"{parsed.strftime('%A')}, {parsed.day} {parsed.strftime('%B %Y')}"
        except ValueError:
            return day


def group_by_day(entries: list[dict]) -> "OrderedDict[str, list[dict]]":
    """Bucket archive entries by the date they were sent, newest day first."""
    days: dict[str, list[dict]] = {}
    for entry in entries:
        stamp = str(entry.get("sent_at", ""))[:10]
        if len(stamp) != 10:
            continue
        # Entries from before this was a news board carry a different shape
        # (a personal "hook" rather than a headline). They would render as
        # empty cards, so they are simply not part of the site.
        if not str(entry.get("headline", "")).strip():
            continue
        days.setdefault(stamp, []).append(entry)
    return OrderedDict(sorted(days.items(), key=lambda kv: kv[0], reverse=True))


def _render_item(item: dict) -> str:
    return f"""      <article>
        <h3>{_esc(item.get('headline', ''))}</h3>
        <p>{_esc(item.get('summary', ''))}</p>
        <p class="why">{_esc(item.get('why_it_matters', ''))}</p>
        <p class="src"><a href="{_esc(item.get('source_url', '#'))}" rel="noopener nofollow">{_esc(item.get('outlet', 'source'))} &rsaquo;</a></p>
      </article>"""


def _render_sections(items: list[dict]) -> str:
    if not items:
        return (
            '      <p class="quiet">Nothing cleared the bar today. An empty board '
            "is more honest than a padded one.</p>"
        )

    out = []
    number = 0
    for section in SECTIONS:
        in_section = [i for i in items if i.get("section") == section]
        if not in_section:
            continue
        number += 1
        body = "\n".join(_render_item(i) for i in in_section)
        out.append(
            f"""    <section>
      <div class="sec-head"><span class="sec-num">{number:02d}</span><h2>{_esc(section)}</h2></div>
{body}
    </section>"""
        )

    # Anything the model filed under an unrecognised section still gets shown,
    # rather than silently vanishing from the board.
    known = set(SECTIONS)
    orphans = [i for i in items if i.get("section") not in known]
    if orphans:
        number += 1
        body = "\n".join(_render_item(i) for i in orphans)
        out.append(
            f"""    <section>
      <div class="sec-head"><span class="sec-num">{number:02d}</span><h2>Also today</h2></div>
{body}
    </section>"""
        )
    return "\n".join(out)


def _page(*, title: str, body: str, home: bool) -> str:
    home_link = "" if home else '<p class="meta"><a href="../index.html">&lsaquo; Latest board</a></p>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(TAGLINE)}">
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
{home_link}
{body}
<footer>
  <p>Assembled once a day by <a href="https://github.com/dwolfpack/inspector-gadget">Inspector Gadget</a>,
  a small agent that runs one web sweep and writes up what it found. Every item links to the
  source it was read in. Summaries are the agent's words, not the outlet's.</p>
</footer>
</div>
</body>
</html>
"""


def render_board(day: str, items: list[dict], *, searches: int, home: bool = True) -> str:
    """One day's board as a complete HTML page."""
    sources = len({str(i.get("source_url", "")) for i in items if i.get("source_url")})
    header = f"""<header>
  <p class="meta">{_esc(_pretty_date(day))}</p>
  <h1>{'<a href="index.html">' if not home else ''}{_esc(TITLE)}{'</a>' if not home else ''}</h1>
  <p class="tagline">{_esc(TAGLINE)}</p>
  <div class="stats">
    <div class="stat"><b>{searches}</b><span>searches run</span></div>
    <div class="stat"><b>{len(items)}</b><span>items</span></div>
    <div class="stat"><b>{sources}</b><span>sources cited</span></div>
  </div>
</header>"""
    return _page(title=f"{TITLE} — {day}", body=header + "\n" + _render_sections(items), home=home)


def render_archive(days: "OrderedDict[str, list[dict]]") -> str:
    rows = "\n".join(
        f'      <li><a href="{_esc(day)}.html">{_esc(_pretty_date(day))}</a>'
        f'<span class="n">{len(items)} item{"s" if len(items) != 1 else ""}</span></li>'
        for day, items in days.items()
    )
    body = f"""<header>
  <p class="meta">Archive</p>
  <h1>{_esc(TITLE)}</h1>
  <p class="tagline">Every board, oldest kept forever.</p>
</header>
    <nav class="days">
      <p class="meta">{len(days)} day{'s' if len(days) != 1 else ''} on record</p>
      <ul>
{rows}
      </ul>
    </nav>"""
    return _page(title=f"{TITLE} — archive", body=body, home=False)


def build(entries: list[dict], *, searches: int, root: Path | None = None) -> list[Path]:
    """Write the whole site. Returns the paths written, newest board first."""
    docs = DOCS if root is None else Path(root)
    archive = docs / "archive"
    archive.mkdir(parents=True, exist_ok=True)

    days = group_by_day(entries)
    written: list[Path] = []

    today = next(iter(days), None)
    index = docs / "index.html"
    index.write_text(
        render_board(today or "", days.get(today, []) if today else [], searches=searches),
        encoding="utf-8",
    )
    written.append(index)

    for day, items in days.items():
        path = archive / f"{day}.html"
        path.write_text(render_board(day, items, searches=searches, home=False), encoding="utf-8")
        written.append(path)

    archive_index = archive / "index.html"
    archive_index.write_text(render_archive(days), encoding="utf-8")
    written.append(archive_index)

    # Stops GitHub Pages running the output through Jekyll, which would mangle
    # any path beginning with an underscore.
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    return written
