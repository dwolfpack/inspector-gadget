import json
from datetime import datetime, timezone

from gadget import history


def _idea(hook, url):
    return {
        "hook": hook,
        "what_it_is": "what",
        "why_you": "why",
        "source_url": url,
        "prompt_to_try": "prompt",
        "category": "releases",
    }


def test_append_then_load_roundtrip(tmp_path):
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    history.append([_idea("A", "https://a.example")], history_dir=tmp_path, now=now)

    loaded = history.load_recent(days=30, history_dir=tmp_path, now=now)

    assert len(loaded) == 1
    assert loaded[0]["hook"] == "A"
    assert loaded[0]["sent_at"] == "2026-08-03T05:00:00+00:00"


def test_append_writes_one_line_per_idea(tmp_path):
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    history.append(
        [_idea("A", "https://a.example"), _idea("B", "https://b.example")],
        history_dir=tmp_path,
        now=now,
    )

    lines = (tmp_path / "2026-08.jsonl").read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[1])["hook"] == "B"


def test_load_recent_crosses_month_boundary(tmp_path):
    july = datetime(2026, 7, 30, 5, 0, tzinfo=timezone.utc)
    august = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    history.append([_idea("July", "https://july.example")], history_dir=tmp_path, now=july)
    history.append([_idea("Aug", "https://aug.example")], history_dir=tmp_path, now=august)

    loaded = history.load_recent(days=30, history_dir=tmp_path, now=august)

    assert {item["hook"] for item in loaded} == {"July", "Aug"}


def test_load_recent_excludes_entries_older_than_window(tmp_path):
    old = datetime(2026, 5, 1, 5, 0, tzinfo=timezone.utc)
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    history.append([_idea("Ancient", "https://old.example")], history_dir=tmp_path, now=old)

    loaded = history.load_recent(days=30, history_dir=tmp_path, now=now)

    assert loaded == []


def test_load_recent_on_missing_directory_returns_empty(tmp_path):
    loaded = history.load_recent(days=30, history_dir=tmp_path / "nope")

    assert loaded == []


def test_load_recent_skips_naive_timestamps_instead_of_raising(tmp_path):
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    history.append([_idea("Good", "https://good.example")], history_dir=tmp_path, now=now)
    naive_record = {**_idea("Naive", "https://naive.example"), "sent_at": "2026-08-01T05:00:00"}
    with (tmp_path / "2026-08.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(naive_record) + "\n")

    loaded = history.load_recent(days=30, history_dir=tmp_path, now=now)

    assert len(loaded) == 1
    assert loaded[0]["hook"] == "Good"


def test_load_recent_skips_corrupt_lines(tmp_path):
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    history.append([_idea("Good", "https://good.example")], history_dir=tmp_path, now=now)
    with (tmp_path / "2026-08.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    loaded = history.load_recent(days=30, history_dir=tmp_path, now=now)

    assert len(loaded) == 1
