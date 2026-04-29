# claude-hackernews

Browser-driven Hacker News automation for the operating account, run from
[Claude Code](https://claude.com/claude-code) via the
[browser-use](https://github.com/browser-use/browser-use) MCP server attached
to a real Windows Chrome over the Chrome DevTools Protocol.

You ask Claude to do something on HN ("draft a comment on this thread",
"summarize today's Show HN posts", "find an Ask HN where FailProof helps").
Claude reasons over the live page state and drives Chrome through
browser-use. You always approve drafts before they go up.

This is a sibling to [`claude-reddit`](https://github.com/exospherehost/claude-reddit) — same architecture,
different target, different Chrome profile and CDP port so both can run
concurrently.

## How it fits together

```
Windows side                                    WSL2 side
─────────────────                               ──────────────────────────
Chrome with:                                    Claude Code (this repo)
  --remote-debugging-port=9334                       │
  --remote-debugging-address=0.0.0.0                 │ stdio
  --user-data-dir=…\hn-profile                       │
  (logged in as the operating HN account)       ┌────▼────────────────────┐
        ▲                                       │ browser-use MCP server  │
        │                                       │ (uvx --from             │
        └─── CDP over HTTP/WS ──────────────────┤  browser-use[cli] --mcp)│
              (127.0.0.1:9334)                  └─────────────────────────┘
```

The browser is **never** launched by Claude. You launch it once on Windows
with a dedicated profile that's logged into the operating HN account;
browser-use attaches to that running instance instead of spawning its own.
Cookies persist in the profile.

## One-time setup

These steps run exactly once after cloning. Most of the tooling
(`uv` / `uvx`, `claude`, `gh`) is assumed already installed on this WSL.

```bash
cd ~/claude-hackernews
# No env vars are required for the browser-use MCP primitives this repo uses.
# The autonomous `retry_with_browser_use_agent` tool is disabled by policy
# (see CLAUDE.md), so its `ANTHROPIC_API_KEY` is intentionally not wired up.
```

Then on the Windows side, the first launch of the dedicated Chrome profile:

```bash
bash scripts/win-chrome.sh
```

A new Chrome window opens at news.ycombinator.com with a brand-new profile
rooted at `%USERPROFILE%\hn-profile`. **Log in as the operating account
manually** (or sign up — HN's signup form is short and there's no email
confirmation by default). Cookies persist in that profile, so you won't
need to re-log on later runs.

Verify the CDP endpoint is reachable from WSL:

```bash
bash scripts/verify-cdp.sh
```

Expected: a JSON blob ending in `OK -- Chrome CDP reachable at 127.0.0.1:9334`.
Common failure modes and fixes are listed inside the script's error output.

If your WSL→Windows networking isn't mirrored, edit `.mcp.json` and update the
`--cdp-url` arg to the appropriate host (e.g., the Windows host IP from
`ip route show default`).

## Daily flow

```bash
# 1. Make sure the HN Chrome is running on Windows
bash scripts/win-chrome.sh    # no-op if already running

# 2. Open Claude Code in this repo
cd ~/claude-hackernews
claude
```

Inside Claude Code:

- Run `/mcp` — `browser-use` should show ✓ Connected with ~16 tools.
- Ask Claude to do whatever HN work you want (see next section).
- When you're done, close the Claude Code session. Leave Chrome open if
  you expect to come back; otherwise close that window too.

## Using it from Claude Code

Examples of prompts that work well. Claude will read the relevant playbook
under `INSTRUCTIONS.md` and follow it.

**Browse / read** (no writes):
```
Open my HN profile and summarize my last 5 submissions and comments
with timestamps.

Summarize the top 10 Show HN posts from the last 24 hours.

Read https://news.ycombinator.com/item?id=12345678 and give me the
TL;DR plus the strongest counterargument in the thread.
```

**Discovery / triage**:
```
Sweep /ask, /show, and /newest for threads where someone is asking
about reliability testing or guardrails for LLM agents. Surface a
candidate list with one-line rationale per thread.
```

**Posting / commenting** (always two-step — draft → approve → submit):
```
Find one thread on the HN front page where FailProof would help.
Draft a comment in failproofai's voice, show me, post after I approve.

Draft a Show HN submission for failproofai. Title and body.
Show me before submitting.
```

**Light engagement** (be conservative — caps in `CLAUDE.md`):
```
Find any HN stories from this week that mention "agent guardrails" or
"hooks". Surface the candidate list. After I approve, upvote.
```

A few prompts to never use (Claude will refuse anyway):
- "Post X without showing me first" — drafts always require approval.
- "Email u/Y from their profile" — outbound contact is off by default.
- Anything that would exceed the daily caps in `CLAUDE.md`.

## Playbooks

Task-specific procedures live in [`INSTRUCTIONS.md`](INSTRUCTIONS.md).
Highlights:

- **How to drive HN (always through the browser)** — primitives cheat
  sheet, identity detection, pre-flight checks, MCP launch-order trap.
- **Reads** — feed coverage (front, newest, ask, show, best, from?site=,
  threads?id=, hn.algolia.com search UI), search query patterns.
- **Writes** — comment composer recipe (HN's plain `<textarea>`, vastly
  simpler than Reddit's Lexical), submission flow, vote/favorite.
- **Output artifact** — every successful post lands as
  `comments/<utc-timestamp>.md` with the same shape as the
  claude-reddit log.
- **About FailProof AI** — product context for HN-bound replies.

To extend a playbook: edit the relevant section of `INSTRUCTIONS.md`
in place.

## Hard rules and limits

Defined in [`CLAUDE.md`](CLAUDE.md). Headlines:

- Drafts always need explicit approval before submitting.
- HN guidelines and thread context read before any post.
- No edits/deletes on others' content; no replies on dead/flagged/closed
  threads.
- Stop on captcha / login wall / rate-limit / shadowban signals.
- Daily caps: ≤ 2 submissions, ≤ 10 comments, ≤ 30 upvotes.
- Randomized 5–30s delays between consecutive write actions.

## Repo layout

```
.
├── .mcp.json                          # browser-use MCP server registration
├── .env.example                       # env template
├── .gitignore
├── CLAUDE.md                          # rules Claude follows in this repo
├── INSTRUCTIONS.md                    # task recipes; grows as system matures
├── README.md                          # this file
├── .claude/settings.json              # failproofai policy hooks (32 policies)
├── .failproofai/policies-config.json  # which policies are enabled
├── scripts/
│   ├── launch-hn-chrome.ps1           # Windows-side Chrome launcher
│   ├── win-chrome.sh                  # WSL → powershell.exe wrapper
│   └── verify-cdp.sh                  # CDP smoke test from WSL
└── comments/                          # log of posted comments (one .md per post)
```

## Troubleshooting

**`browser_get_state` returns a connection error in Claude Code**
The Windows Chrome with CDP isn't running, or the IP changed.

```bash
bash scripts/verify-cdp.sh
```

If the host detected by the script differs from `127.0.0.1`, update the
`--cdp-url` line in `.mcp.json` and restart Claude Code (so the MCP server
re-spawns with the new arg).

**`browser-use` MCP shows as not connected in `/mcp`**
Most often: `uv` / `uvx` not on PATH for the MCP server's spawn environment.
Check:
- `which uvx` resolves
- `uvx --from browser-use[cli] browser-use --help` runs without errors

**HN asks to log in mid-session**
The dedicated profile's session expired. Re-launch Chrome with
`scripts/win-chrome.sh`, log in manually, leave the window open.

**The action ran but I see "we have a daily limit on new submissions"**
You hit an HN rate limit. Stop. Wait at least 30 minutes before any
further write action. If it persists, the account may have been
shadowbanned — check by opening the same thread in an incognito window
and confirming your recent comments are visible. (HN shadowbans are
silent; the account sees its own dead comments as alive.)

**WSL→Windows IP keeps changing on every restart**
Switch WSL2 to mirrored networking. Edit `C:\Users\<you>\.wslconfig`:

```
[wsl2]
networkingMode=mirrored
```

Then `wsl --shutdown` and restart. After that, `localhost:9334` works from
WSL — though `.mcp.json` here uses `127.0.0.1:9334` because `localhost`
on this WSL resolves to IPv6 only and Chrome's CDP listens on IPv4.

**Reddit and HN harnesses fight over Chrome**
They shouldn't — claude-reddit uses CDP port 9333 and profile
`reddit-profile`, claude-hackernews uses 9334 and `hn-profile`. Both can
run concurrently as separate `chrome.exe` processes against separate
profile dirs. If you see `browser-use` from one repo connecting to the
other's tabs, double-check `.mcp.json` in each repo is on its own port.

## What's intentionally not here

- **Firebase HN API / Algolia HN API / RSS** — this harness is browser-only
  by design (see `CLAUDE.md`). HN's APIs are public and unauthenticated, so
  the temptation to reach for them is real. Resist. Account-safety reason:
  side-channel reads from a non-browser fingerprint correlate with the
  browsing session and flag faster on HN than they do on Reddit.
- **Tests / CI** — none yet. The "tests" are the verification steps in
  this README plus the playbooks themselves.
- **Scheduled jobs** — planned for after the ad-hoc flow is reliable; will
  port `hourly_reddit_cron.py` from claude-reddit to a sibling
  `hourly_hackernews_cron.py` and run from a dedicated `.cron/` clone, the
  same way the Reddit harness does.
