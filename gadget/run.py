"""Entry point: sweep, format, deliver, record."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from gadget import history, research, telegram

PROFILE_PATH = Path(__file__).resolve().parent.parent / "profile.md"
HISTORY_WINDOW_DAYS = 30


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

    profile = PROFILE_PATH.read_text(encoding="utf-8")
    seen = history.load_recent(days=HISTORY_WINDOW_DAYS)

    try:
        ideas = research.find_ideas(profile, seen)
    except research.ResearchError as exc:
        notify(f"🕵️ <b>Inspector Gadget stumbled</b>\n\n{telegram.escape_html(str(exc))}")
        return 1

    if not notify(telegram.format_digest(ideas)):
        return 1

    if ideas and not args.dry_run:
        try:
            history.append(ideas)
        except OSError as exc:
            # The digest already went out. A lost history entry costs at most
            # one repeated idea, so this is not worth failing the run over.
            print(f"Could not write history: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
