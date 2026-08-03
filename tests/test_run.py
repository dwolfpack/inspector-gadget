from unittest.mock import patch

import pytest

from gadget import research, run, telegram


def _idea(hook="Hook"):
    return {
        "hook": hook,
        "what_it_is": "what",
        "why_you": "why",
        "source_url": "https://example.com",
        "prompt_to_try": "prompt",
        "category": "releases",
    }


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")


def test_happy_path_sends_and_records():
    with patch("gadget.run.history.load_recent", return_value=[]), \
         patch("gadget.run.research.find_ideas", return_value=[_idea()]), \
         patch("gadget.run.telegram.send") as send, \
         patch("gadget.run.history.append") as append:
        code = run.main([])

    assert code == 0
    send.assert_called_once()
    append.assert_called_once()


def test_dry_run_neither_sends_nor_records(capsys):
    with patch("gadget.run.history.load_recent", return_value=[]), \
         patch("gadget.run.research.find_ideas", return_value=[_idea("Dry")]), \
         patch("gadget.run.telegram.send") as send, \
         patch("gadget.run.history.append") as append:
        code = run.main(["--dry-run"])

    assert code == 0
    send.assert_not_called()
    append.assert_not_called()
    assert "Dry" in capsys.readouterr().out


def test_research_failure_sends_a_stumble_message_and_exits_nonzero():
    with patch("gadget.run.history.load_recent", return_value=[]), \
         patch("gadget.run.research.find_ideas", side_effect=research.ResearchError("boom")), \
         patch("gadget.run.telegram.send") as send, \
         patch("gadget.run.history.append") as append:
        code = run.main([])

    assert code == 1
    assert "stumbled" in send.call_args.args[0].lower()
    assert "boom" in send.call_args.args[0]
    append.assert_not_called()


def test_no_ideas_sends_quiet_note_and_exits_zero():
    with patch("gadget.run.history.load_recent", return_value=[]), \
         patch("gadget.run.research.find_ideas", return_value=[]), \
         patch("gadget.run.telegram.send") as send, \
         patch("gadget.run.history.append") as append:
        code = run.main([])

    assert code == 0
    assert "quiet" in send.call_args.args[0].lower()
    append.assert_not_called()


def test_telegram_failure_exits_nonzero():
    with patch("gadget.run.history.load_recent", return_value=[]), \
         patch("gadget.run.research.find_ideas", return_value=[_idea()]), \
         patch("gadget.run.telegram.send", side_effect=telegram.TelegramError("down")), \
         patch("gadget.run.history.append") as append:
        code = run.main([])

    assert code == 1
    append.assert_not_called()


def test_history_append_failure_still_exits_zero():
    with patch("gadget.run.history.load_recent", return_value=[]), \
         patch("gadget.run.research.find_ideas", return_value=[_idea()]), \
         patch("gadget.run.telegram.send"), \
         patch("gadget.run.history.append", side_effect=OSError("read-only fs")):
        code = run.main([])

    assert code == 0


def test_missing_env_var_exits_nonzero_without_calling_the_api(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    with patch("gadget.run.research.find_ideas") as find:
        code = run.main([])

    assert code == 1
    find.assert_not_called()


def test_dry_run_does_not_require_the_telegram_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    with patch("gadget.run.history.load_recent", return_value=[]), \
         patch("gadget.run.research.find_ideas", return_value=[_idea()]), \
         patch("gadget.run.telegram.send") as send:
        code = run.main(["--dry-run"])

    assert code == 0
    send.assert_not_called()
