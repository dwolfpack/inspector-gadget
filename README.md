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
curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | grep -o '"chat":{"id":[0-9-]*' | grep -o '[0-9-]*$' | head -1
```

The number is your `TELEGRAM_CHAT_ID`.

### 3. Add the secrets

These three live in the **`Gadget` environment** (GitHub → Settings →
Environments → Gadget → Environment secrets):

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | From step 2 |

The `digest` job in `daily.yml` declares `environment: Gadget` so it can read
them. Environment secrets are invisible to any job that does not name the
environment — if you ever move these to repository-level secrets instead, drop
that line, and if you rename the environment, change it in both places.

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
- **When it runs** — the four cron slots in `.github/workflows/daily.yml`,
  spanning roughly 08:00–11:30 Israel time across both DST states.

  There are four rather than one because GitHub does not guarantee cron
  punctuality; delays of 30–120 minutes are routine. Idempotency comes from
  `history/.last-sent`, which records the Israel date of the last successful
  send: the first slot that runs at or after 08:00 local sends the digest, and
  every later slot that day sees the marker and becomes a no-op. A delayed run
  therefore arrives late instead of not at all.

  If you ever need to force a resend on a day that already went out, delete
  `history/.last-sent` — or just use Run workflow, which bypasses the check.

## Cost

Roughly $2–5/month, mostly web searches ($10 per 1,000; up to 5 per run).

The sweep is budgeted to finish inside three minutes — `MAX_SEARCHES`,
`EFFORT`, and `DEADLINE_SECONDS` in `gadget/research.py` are the knobs.
The deadline is enforced in Python rather than by a workflow timeout so a
slow morning still sends you a message explaining itself.
