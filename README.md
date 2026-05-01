# claude-hackernews

Browser-driven Hacker News drafting harness, run from
[Claude Code](https://claude.com/claude-code) via the
[browser-use](https://github.com/browser-use/browser-use) MCP server attached
to a real Windows Chrome over the Chrome DevTools Protocol. The harness
is unauthenticated — Claude reads HN, drafts proposed replies into
`drafts/<ts>.md`, and surfaces them as PRs. You post manually from
whichever HN account you choose.

You ask Claude to do something on HN ("draft a comment on this thread",
"summarize today's Show HN posts", "find an Ask HN where FailProof helps").
Claude reasons over the live page state and drives Chrome through
browser-use. You always approve drafts before they go up.

This is a sibling to [`claude-reddit`](https://github.com/exospherehost/claude-reddit) — same architecture,
different target, different Chrome profile and CDP port so both can run
concurrently.

## Strict comment workflow (mandatory, no exceptions)

Every comment, reply, or submission Claude proposes **must** go through
this exact workflow. This is non-negotiable. Claude never types into the
HN composer and never clicks submit — the PR is the only handoff path.

1. **Write the comment to `drafts/<utc-timestamp>.md`** where
   `<utc-timestamp>` is UTC `YYYY-MM-DDTHHMMSSZ` (filesystem-safe; no
   colons in the time portion, e.g. `drafts/2026-04-30T143022Z.md`).
   One file per intended post. The file must contain the thread URL
   and the full body to be posted. Drafts are account-agnostic — no
   operating-account handle, no identity detection. The user picks
   the posting account at post time. (`comments/` is a separate
   directory used as a log of replies that were actually posted on
   HN — Claude does not write there on its own.)
2. **Commit** that file on a fresh branch (never on `main`). The commit
   message must clearly identify the thread or topic.
3. **Push** the branch to the remote.
4. **Open a PR** on this repo for that branch. The PR is the user's
   review-and-approval gate; the user posts to HN manually after
   reviewing.

If any of the four steps fails (push rejected, PR creation errored,
commit hook blocked, etc.), stop and surface the failure to the user.
Do not skip a step, do not collapse them, and do not paste the comment
body into chat in lieu of the PR.

## How it fits together

```
Windows side                                    WSL2 side
─────────────────                               ──────────────────────────
Chrome with:                                    Claude Code (this repo)
  --remote-debugging-port=9334                       │
  --remote-debugging-address=0.0.0.0                 │ stdio
  --user-data-dir=…\hn-profile                       │
  (no login required; reads only)               ┌────▼────────────────────┐
        ▲                                       │ browser-use MCP server  │
        │                                       │ (uvx --from             │
        └─── CDP over HTTP/WS ──────────────────┤  browser-use[cli] --mcp)│
              (127.0.0.1:9334)                  └─────────────────────────┘
```

The browser is **never** launched by Claude. You launch it once on Windows
with a dedicated profile; browser-use attaches to that running instance
instead of spawning its own. The profile does not need to be logged in
— this harness only reads HN — though if you've previously logged in,
the cookies persist.

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
rooted at `%USERPROFILE%\hn-profile`. **Logging in is optional.** This
harness only reads HN, so a logged-out profile is fine. If you do log
in (handy for showdead, profile pages, etc.), cookies persist across
runs.

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

**Browse / read**:
```
Summarize the top 10 Show HN posts from the last 24 hours.

Read https://news.ycombinator.com/item?id=12345678 and give me the
TL;DR plus the strongest counterargument in the thread.

Read /user?id=<some-handle> and summarize that account's recent
submissions and comments.
```

**Discovery / triage**:
```
Sweep /ask, /show, and /newest for threads where someone is asking
about reliability testing or guardrails for LLM agents. Surface a
candidate list with one-line rationale per thread.
```

**Drafting** (Claude writes a `drafts/<ts>.md` and opens a PR; you
post manually after merging):
```
Find one thread on the HN front page where FailProof would help.
Draft a reply, commit it on a fresh branch, push, open a PR.

Draft a Show HN submission for failproofai. Title and body. PR it.
```

A few prompts to never use (Claude will refuse anyway):
- "Post X to HN directly" — Claude does not submit to HN; only PRs.
- "Upvote / favorite / vote on X" — write-side interactions are off.
- "Email u/Y from their profile" — outbound contact is off by default.

## Playbooks

Task-specific procedures live in [`INSTRUCTIONS.md`](INSTRUCTIONS.md).
Highlights:

- **How to drive HN (always through the browser)** — primitives cheat
  sheet, pre-flight checks, MCP launch-order trap.
- **Reads** — feed coverage (front, newest, ask, show, best, from?site=,
  threads?id=, hn.algolia.com search UI), search query patterns.
- **Writes (comments via PR)** — drafting flow, required draft-file
  sections, three-surface duplicate scan. The HN comment composer
  recipe (currently inert) is preserved for the day direct-posting is
  re-enabled.
- **Output artifact** — every proposed reply lands as
  `drafts/<utc-timestamp>.md` (committed and surfaced via PR for
  manual posting); the `comments/` directory is a separate log of
  replies that were actually posted on HN.
- **About FailProof AI** — product context for HN-bound replies.

To extend a playbook: edit the relevant section of `INSTRUCTIONS.md`
in place.

## Hard rules and limits

Defined in [`CLAUDE.md`](CLAUDE.md). Headlines:

- Unauthenticated by policy. Drafts are account-agnostic — the user
  picks the posting account at post time.
- Claude never types into the HN composer or clicks submit; the PR is
  the only handoff path.
- Browser-only access for reads (no Firebase / Algolia / RSS / curl
  against ycombinator.com hosts).
- HN guidelines and thread context read before any draft.
- Stop on captcha / login wall / rate-limit signals; back off, don't
  log in to dismiss.
- Daily caps as guidance for the posting account: ≤ 2 submissions,
  ≤ 10 comments, ≤ 30 upvotes.
- Human-pace cadence on reads: jittered 3-12s between page navigations,
  ≤ 20 page loads per 5-minute window.

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
│   ├── launch-hn-chrome-close.ps1     # Windows-side Chrome stopper (end-of-run)
│   ├── win-chrome.sh                  # WSL → powershell.exe launch wrapper
│   ├── win-chrome-close.sh            # WSL → powershell.exe close wrapper
│   ├── verify-cdp.sh                  # CDP smoke test from WSL
│   └── hourly_hackernews_cron.py      # hourly cron driver (Discord-logged)
├── drafts/                            # proposed replies awaiting manual post (tracked; surfaced via PR)
└── comments/                          # log of replies that were actually posted on HN
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
A read path hit a login-gated page. Most HN reads work logged out, so
this usually means the agent navigated somewhere that requires auth
(e.g., `showdead`, vote arrows). Don't log in to dismiss it; back off
and retry the workflow without the gated step. Logging in is optional
for this harness, not required.

**The agent saw "we have a daily limit" or "submitting too fast"**
That's a rate-limit signal from a read sweep that was too aggressive.
Stop. Wait at least 30 minutes before resuming. The harness does not
submit, so this should not surface from the write side.

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
  the temptation to reach for them is real. Resist. Reason: side-channel
  HTTP traffic to HN's APIs while a browser is on the same machine is a
  noisy fingerprint and a traffic pattern moderation watches for, even
  with no logged-in session.
- **Scheduled jobs** — `scripts/hourly_hackernews_cron.py` is the hourly
  trigger (mirror of claude-reddit's `hourly_reddit_cron.py`). Wire it
  into system cron and it'll bring Chrome up via `scripts/win-chrome.sh`,
  poll `scripts/verify-cdp.sh` until CDP is reachable, then shell out to
  `luv claude-hackernews "<prompt>" -nit` after a randomized pre-run
  sleep (no working-hours gate; runs every cron firing). The default prompt enforces
  the strict comment workflow above (drafts to `drafts/` + commit +
  push + PR; never submits to HN). Run from a dedicated `.cron/` clone
  the same way the Reddit harness does. End-of-run Chrome cleanup is
  the agent's responsibility via `scripts/win-chrome-close.sh` (see the
  "End-of-run cleanup" section in `INSTRUCTIONS.md`).
- **Logging destination** — lifecycle events (start / ok / noop / fail)
  go to a Discord webhook, **not** healthchecks.io or any other
  uptime-style ping service. Set `CRON_DISCORD_WEBHOOK_URL` in the
  crontab line; leave it empty to disable. Long bodies attach as
  `cron.log` via multipart so nothing is truncated. If you also run the
  sibling claude-reddit cron on the same machine, give each cron line
  its own webhook URL so HN and Reddit events land in separate channels.
- **Tests / CI** — none yet. The "tests" are the verification steps in
  this README plus the playbooks themselves.
