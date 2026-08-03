"""The archive of ideas already sent, used to avoid repeating them."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HISTORY_DIR = Path(__file__).resolve().parent.parent / "history"


def _resolve(history_dir: Path | None) -> Path:
    return HISTORY_DIR if history_dir is None else Path(history_dir)


def _utcnow(now: datetime | None) -> datetime:
    return datetime.now(timezone.utc) if now is None else now


def append(
    items: list[dict],
    *,
    history_dir: Path | None = None,
    now: datetime | None = None,
) -> None:
    """Append one JSON line per idea to the archive file for the current month."""
    if not items:
        return

    moment = _utcnow(now)
    directory = _resolve(history_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{moment:%Y-%m}.jsonl"

    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            record = dict(item)
            record["sent_at"] = moment.isoformat()
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent(
    days: int = 30,
    *,
    history_dir: Path | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Return every archived idea sent within the last `days` days.

    Reads every month file and filters by timestamp, so a window that spans a
    month boundary needs no special handling. Corrupt lines are skipped rather
    than raising: a damaged archive should cost us dedupe accuracy, not the
    morning's digest.
    """
    directory = _resolve(history_dir)
    if not directory.is_dir():
        return []

    cutoff = _utcnow(now) - timedelta(days=days)
    recent: list[dict] = []

    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                sent_at = datetime.fromisoformat(record["sent_at"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if sent_at >= cutoff:
                recent.append(record)

    return recent
