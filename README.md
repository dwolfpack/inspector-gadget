# Inspector Gadget

A daily scout. Every morning at 08:00 Israel time it sweeps the web for new
things worth doing with Claude and sends three of them to Telegram.

Design doc: `claude_projects/docs/superpowers/specs/2026-08-03-inspector-gadget-design.md`

## How it works

A GitHub Actions cron job runs `python -m gadget.run`, which:

1. Loads `profile.md` and the last 30 days of `history/*.jsonl`.
2. Asks `claude-sonnet-5` — with the web search tool enabled — for three new
   ideas, excluding anything already sent.
3. Renders them as Telegram HTML and sends them.
4. Appends what it sent to `history/` and commits it back to this repo.

If anything fails, it sends a "stumbled" message instead. Silence means it
worked.

## One-time setup

### 1. Create the bot

Message [@BotFather](https://t.me/BotFather) on Telegram:

```
/newbot
```

Name it `Inspector Gadget`, pick a username, and save the token it gives you.
Optionally set an avatar with `/setuserpic`.

### 2. Get your chat ID

Send any message to your new bot (say `hi`), then run:

```bash
curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | grep -o '"id":[0-9-]*' | head -1
```

The number is your `TELEGRAM_CHAT_ID`.

### 3. Add the repository secrets

In GitHub → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | From step 2 |

### 4. Test it

GitHub → Actions → "daily digest" → Run workflow. Manual runs bypass the
time-of-day guard, so it fires immediately.

## Local development

```bash
pip install -r requirements.txt pytest
python -m pytest -v
```

Preview a digest without sending anything (needs only `ANTHROPIC_API_KEY`):

```bash
python -m gadget.run --dry-run
```

## Tuning it

- **What it looks for** — the `SYSTEM` prompt in `gadget/research.py`.
- **Who it's for** — `profile.md`. Keep this current; it is what makes the
  `why_you` line land.
- **When it runs** — the cron pair in `.github/workflows/daily.yml`. Both entries
  exist so the Israel-hour guard can pick the right one across DST; change both
  together.

## Cost

Roughly $3–8/month, mostly web searches ($10 per 1,000; up to 8 per run).
