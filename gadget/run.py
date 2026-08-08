"""Entry point: sweep, format, deliver, record."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from gadget import history, research, site, telegram

HISTORY_WINDOW_DAYS = 30
# The site keeps everything; the exclusion list only looks back a month.
SITE_WINDOW_DAYS = 3650


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="inspector-gadget")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the digest instead of sending it, and do not touch history",
    )
    return parser.parse_args(argv)


def _require_env(names: list[str]) -> dict[str, str] | None:
    values = {}
    missing = []
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            values[name] = value
        else:
            missing.append(name)
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return None
    return values


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    required = ["ANTHROPIC_API_KEY"]
    if not args.dry_run:
        required += ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    env = _require_env(required)
    if env is None:
        return 1

    def notify(text: str) -> bool:
        """Deliver text; return False if delivery itself failed."""
        if args.dry_run:
            print(text)
            return True
        try:
            telegram.send(
                text,
                token=env["TELEGRAM_BOT_TOKEN"],
                chat_id=env["TELEGRAM_CHAT_ID"],
            )
            return True
        except telegram.TelegramError as exc:
            print(f"Telegram delivery failed: {exc}", file=sys.stderr)
            return False

    seen = history.load_recent(days=HISTORY_WINDOW_DAYS)

    try:
        items = research.find_items(seen)
    except research.ResearchError as exc:
        notify(f"🕵️ <b>Inspector Gadget stumbled</b>\n\n{telegram.escape_html(str(exc))}")
        return 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if items and not args.dry_run:
        try:
            history.append(items)
        except OSError as exc:
            # Recorded before the site is built so the board includes today.
            # A lost entry costs at most one repeated story tomorrow.
            print(f"Could not write history: {exc}", file=sys.stderr)

    if not args.dry_run:
        try:
            written = site.build(
                history.load_recent(days=SITE_WINDOW_DAYS),
                searches=research.MAX_SEARCHES,
            )
            print(f"site: wrote {len(written)} page(s)", file=sys.stderr)
        except OSError as exc:
            # The board still goes out on Telegram; only the site is stale.
            print(f"Could not build the site: {exc}", file=sys.stderr)

    if not notify(telegram.format_board(today, items)):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
