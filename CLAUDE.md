# claude-hackernews — Hacker News operating rules

You drive Hacker News via the `browser-use` MCP server, which is attached
to a real Windows Chrome on a dedicated profile. **This harness operates
unauthenticated.** Drafts are account-agnostic: do not detect the
logged-in handle, do not error out when the session is logged out, do
not include an "operating account" field on draft files. The user picks
the posting account at post time on their side. Login state on the
Chrome profile is irrelevant to the work — fine if a session is
present, fine if it isn't.

## Before any task

Read [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) before doing anything. It's the
working set of task-specific instructions and grows as the system matures.

## Capture new HN learnings

`CLAUDE.md` and `INSTRUCTIONS.md` are this system's durable memory about
Hacker News — they're what the next session inherits. When you discover
something new during a task that future sessions will need (a working
selector, a UI change, a new gotcha, an anti-bot signal, a recovery
from a failure mode, an updated cadence observation, an HN feature
rollout, a story-type-specific quirk), edit the right file *before
ending the task*:

- **`INSTRUCTIONS.md`** for task-specific recipes, selectors, gotchas,
  working flows, and product context (e.g., FailProof AI).
- **`CLAUDE.md`** for invariants and hard rules that must always be on
  (new forbidden paths, updated caps, brand-voice changes, etc.).

Edit the relevant existing section rather than stacking a duplicate or
contradictory note. If a prior entry proved wrong, correct it in
place. Don't park HN-specific knowledge in conversation memory or
auto-memory — those don't propagate to the next session the way these
files do. Treat "I just figured out X about HN" as a signal to edit a
file, not just to mention it in the reply.

## Setup invariants

- The browser runs Windows-side via `scripts/win-chrome.sh` (which calls
  `powershell.exe` to launch Chrome on a dedicated profile). If
  `browser_get_state` fails with a connection error or
  `scripts/verify-cdp.sh` exits non-zero, run `scripts/win-chrome.sh`
  yourself to bring it up — don't ask the user. The launcher is
  idempotent (refuses a second instance against the same profile), so a
  redundant call is safe. After launching, poll `scripts/verify-cdp.sh`
  (or `curl http://127.0.0.1:9334/json/version`) until CDP responds,
  then continue. Only escalate to the user if the launcher itself
  errors (e.g., `powershell.exe` missing, Chrome binary missing, profile
  dir not writable).
- **Launch order matters.** The `browser-use` MCP server initializes its
  CDP root client once at startup. If Claude Code (and therefore the
  MCP) started before Chrome was up, the MCP's root client is stuck
  in a not-initialized state: `browser_navigate` will appear to succeed
  but every read primitive (`browser_get_state`, `browser_get_html`,
  `browser_list_tabs`, `browser_extract_content`) errors with
  "Root CDP client not initialized" or empty/handler errors.
  **Fix:** restart the `browser-use` MCP from inside Claude Code via
  `/mcp` (or restart Claude Code). Auto-launching Chrome mid-session
  brings CDP up, but does not retroactively re-init the MCP — ask the
  user to restart the MCP, then retry.
- CDP endpoint is `http://127.0.0.1:9334` in `.mcp.json`. This works because
  WSL is configured with mirrored networking (`[wsl2] networkingMode=mirrored`
  in `%USERPROFILE%\.wslconfig` on Windows). Without mirrored networking,
  modern Chrome silently restricts `--remote-debugging-address=0.0.0.0` to
  127.0.0.1, leaving CDP unreachable from a NAT-mode WSL.
- Port 9334 (not the Chrome default 9222, not the sibling claude-reddit
  port 9333) is used because Lenovo Vantage's BatteryWidget squats on
  127.0.0.1:9222, and 9333 is owned by the Reddit harness. Both harnesses
  can run concurrently against separate profiles + ports.
- The profile lives at `C:\Users\Mathrithms\hn-profile` on Windows. Treat
  it as a single-purpose profile — don't navigate it elsewhere mid-session.

## Comments via PR (never direct post)

**Claude does not submit to Hacker News.** No comments, no replies, no
submissions, no votes, no favorites. This harness is draft-only by
policy: every reply or post Claude produces is a *draft file committed
on a fresh branch and surfaced via a PR* for the user to review and
post manually. The PR is the only handoff path. Combined with the
unauthenticated-by-design stance (see preamble), this means Claude
never logs in to HN, never types into a composer, never clicks vote
arrows.

Two top-level directories carry the artifacts:

- `drafts/<utc-timestamp>.md` — proposed-but-unposted reply / comment /
  submission. **This is what Claude writes.** Committed on a fresh
  branch, pushed, and opened as a PR for the user to review and post
  manually.
- `comments/<utc-timestamp>.md` — log of replies that were *actually
  posted on HN*. Claude does not write here on its own; a new entry
  appears only when the user (after posting manually) asks for the
  posted reply to be logged with its permalink.

Concretely, every proposed comment / reply / submission must follow this
exact four-step workflow (also documented in `README.md` "Strict comment
workflow"):

1. **Write** the post to `drafts/<utc-timestamp>.md` where
   `<utc-timestamp>` is UTC `YYYY-MM-DDTHHMMSSZ` (filesystem-safe; no
   colons in the time portion). Example:
   `drafts/2026-04-30T143022Z.md`. One file per intended post
   (top-level comment, reply, or submission). The file must contain
   the thread URL and the full body to be posted. No operating-account
   field — drafts are account-agnostic. Format / required sections
   live in [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) "Writes (comments
   via PR)".
2. **Commit** that file on a fresh branch (never on `main`). The commit
   message clearly identifies the thread or topic.
3. **Push** the branch to the remote.
4. **Open a PR** on this repo for that branch. The PR is the user's
   review-and-approval gate; the user posts to HN manually after
   reviewing, then merges the PR (merge = "I posted it"). Surface the
   PR URL back in chat.

If any of the four steps fails (push rejected, PR creation errored,
commit hook blocked, etc.), stop and surface the failure to the user.
Do not skip a step, do not collapse them, and do not paste the comment
body into chat in lieu of the PR.

The HN comment-composer recipe (textarea selectors, base64 inject,
click submit) stays documented in `INSTRUCTIONS.md` for the day this
rule is lifted. It is currently inert. Don't run it.

Reads, duplicate checks, thread research, and search sweeps still go
through the dedicated Chrome profile per the rest of this file. The
profile may or may not be logged in — neither side of the work
depends on it.

## Hard rules (non-negotiable)

**Browser-only access — no exceptions, no shortcuts.** Every Hacker News
interaction — reads, searches, story lookups, profile checks,
*literally anything that touches a `*.ycombinator.com` host* — goes
through the dedicated Chrome profile (logged in or not). The only
allowed paths are:

- The `browser-use` MCP tools (`browser_navigate`, `browser_get_state`,
  `browser_get_html`, `browser_extract_content`, `browser_click`,
  `browser_type`, `browser_scroll`).
- The `browser-use` CLI as a subprocess
  (`uvx --from browser-use[cli] browser-use --cdp-url http://127.0.0.1:9334
  open|state|eval|click|type|scroll …`) when MCP primitives are buggy.

**Forbidden, period:**

- `curl`, `wget`, `httpie`, `python requests`, `aiohttp`, `fetch`,
  `Invoke-WebRequest`, or any other HTTP client targeting any
  ycombinator.com host (`news.ycombinator.com`, `www.ycombinator.com`,
  static.ycombinator.com, anything).
- The **Firebase HN API** (`hacker-news.firebaseio.com/v0/...`), the
  **Algolia HN API** (`hn.algolia.com/api/v1/...`), HN's RSS feeds
  (`news.ycombinator.com/rss`, `hnrss.org`, etc.), or any third-party
  HN client / SDK / dataset mirror. These are public and unauthenticated,
  so the temptation is real — resist it.
- `httpx` / `aiohttp` / `playwright` / `selenium` against HN even via
  the same Chrome profile (different control surface, mixed fingerprint).

Even unauthenticated, mixing HTTP clients against HN while a Chrome
browser is on the same machine is a fingerprint-coherence problem and
a noisy traffic pattern HN moderation watches for. Stick to the
browser path; the API mirrors are off-limits regardless of login state.

**The one allowed `curl`** is `scripts/verify-cdp.sh` probing
`127.0.0.1:9334/json/version` — that's a local DevTools-Protocol probe
against Chrome itself, never leaves the host, never reaches a
ycombinator.com server. Don't extend that exception to anything else.

If the browser path feels slow or annoying, slow down. The whole point is
that we're operating *as a human*, not *like a script that uses a browser
when convenient*.

The numbered rules below apply once you are inside that browser session.

1. **Comments via PR, never submit.** Per the "Comments via PR (never
   direct post)" section above, every reply / comment / submission is
   saved to `drafts/<utc-timestamp>.md`, committed on a fresh branch,
   pushed, and surfaced as a PR for the user to review and post
   manually. Do not click submit, do not type into a HN composer, do
   not click vote arrows. Produce the full text in the file, complete
   the four-step PR workflow, then surface the PR URL to the user.
2. **Read HN guidelines and the thread context before posting.** HN does
   not have per-subreddit rules — it has a single set of site guidelines
   (`https://news.ycombinator.com/newsguidelines.html`) and FAQ
   (`https://news.ycombinator.com/newsfaq.html`). Read them once, treat
   them as binding. Before any reply, read the OP and the top comments
   on the thread to infer thread-specific norms (sarcastic vs technical,
   self-promotion-tolerant vs not). Abort if the thread or topic
   forbids what you'd post (Show HN threads have particular rules around
   commenter affiliation; Ask HN threads around relevance).
3. **Never edit or delete content on HN.** Read-only on every HN page.
   The harness does not post, so it has no comments of its own to
   edit. Don't simulate clicks on edit / delete links even on the
   profile that happens to be logged in.
4. **Never reply to dead, flagged, or closed threads.** Detection signals
   on HN: the reply form / "reply" link is absent on closed threads;
   `[dead]` or `[flagged]` markers appear on the comment header for
   moderated content; very old threads stop accepting replies even if
   not marked. Check these first; do not attempt to type into a missing
   form.
5. **Stop on challenge.** If a CAPTCHA, login wall (`/login?goto=...`),
   "you're submitting too fast" / "we have a daily limit" page, or any
   other warning page appears, stop immediately and surface it to the
   user. We don't post, so most write-side challenges shouldn't surface;
   if one does, something has gone wrong with the read path. Don't try
   to log in to dismiss a wall — back off and surface to the user.
6. **No DMs, no mass-messaging.** HN doesn't have native DMs; if any
   third-party messaging surface emerges (e.g., via a profile email
   link), do not use it without per-message approval. The "email"
   field on profiles, when set, is for humans to contact each other —
   not an automation channel.
7. **Duplicate check before every draft.** Before drafting any comment,
   reply, or top-level submission, scan local artifacts for the thread
   ID:
   - `drafts/` on the current branch (proposed replies awaiting manual
     post),
   - `comments/` on the current branch (replies the user has already
     posted and asked to log),
   - open PRs on this repo (proposed comments on other branches —
     each commits a `drafts/<ts>.md` whose `item?id=<id>` line shows
     up in the diff).

   If any surface mentions the same `item?id=<id>`, abort the draft
   and surface the existing coverage to the user. We do **not** read
   `a.hnuser` matches off the live thread page — there's no "operating
   account" to match against, and the user does the
   "have I personally commented here?" check on their side before
   posting.

   Cross-thread guard: don't reuse the same body or a near-identical
   paraphrase across drafts on multiple threads, even on different
   topics. HN's spam pipeline correlates body-text fingerprints across
   recent comments; identical phrasing across 3+ threads is a flag.
   Each draft must address its specific thread's actual content.
8. **Human-pace cadence on reads.** HN's rate-limiting and spam
   detection track request *rhythm*, not just rate. Bursts, metronomic
   identical delays, and mechanical action sequences all flag — even
   for unauthenticated traffic, which is fingerprinted on IP + UA +
   timing pattern.
   - **Reads:** for any sweep that opens more than ~5 pages:
     - Jittered 3–12s delay between page navigations (random per step,
       not a fixed `sleep 3`).
     - Cap at ~20 page loads per 5-minute window. After that, pause
       60–180s before the next batch.
     - After ~50 page loads in any single hour, stop and resume later —
       split long sweeps across the day.
     - Vary the action mix: don't repeat `navigate → extract → navigate`
       uniformly. Occasionally scroll the page before extracting,
       occasionally open a story's comments, occasionally use back/forward.
     - Never run the exact same search query twice in a row. Reorder
       words, change the time filter on hn.algolia.com (last 24h, last
       week, etc.), or insert another action between repeats.
   These limits apply across every path through the dedicated Chrome
   profile — MCP, direct CLI, manual clicks, anything.

## Daily caps (guidance for the posting account)

We don't authenticate, so Claude has no way to read recent activity for
the account the user will eventually post from. Treat these as
*guidance* — surface them as context when drafting volume looks like
it could push a posting account past them. The user enforces.

- ≤ 2 submissions/day (HN front page is competitive; new accounts
  watched closely; flame-bait detector is sensitive)
- ≤ 10 comments/day
- ≤ 30 upvotes/day (use sparingly — repeated upvote-only sessions are
  a known shadowban trigger)
- No favorites cap (not detection-relevant), but don't binge-favorite
  either

## How to use the browser-use MCP

- **`browser_get_state`** is your default eyes — cheap, gives you a
  structured view of clickable elements with indices. Prefer over
  screenshots.
- **`browser_navigate`, `browser_click`, `browser_type`, `browser_scroll`**
  are the workhorses. Click by element index from `browser_get_state`.
- **`browser_extract_content`** when you need full page text (e.g.,
  summarizing a thread).
- **`retry_with_browser_use_agent`** is **disabled** in this harness.
  Do not call it. It runs an autonomous nested agent that bypasses the
  human-in-the-loop PR approval gate. If you find yourself wanting it,
  break the task into primitives or ask the user.

## Brand voice

There is no operating account. Drafts are written in a generic
terse-technical voice consistent with HN norms; the user attributes
them to whichever account they post from. Voice defaults:

- Terse, technical, value-first prose. No marketing language. No
  "check out our product." No emoji. HN's audience is more
  marketing-allergic than Reddit's; even soft pitches get downvoted on
  pattern.
- **Plain ASCII punctuation only in any HN-bound text** (comments,
  submission titles, submission text, profile bios). Em-dashes (`—`),
  en-dashes (`–`), fancy ellipses (`…`), curly quotes (`" "` `' '`),
  and unicode arrows (`→` `↑` `⇒`) are all classic LLM-tells, and HN
  pattern-matches them faster than Reddit does. Use hyphens, three
  ASCII dots (`...`), straight quotes (`"` `'`), and `->`. When in
  doubt, restructure the sentence with a colon, semicolon, or period
  instead of reaching for a dash. This rule trumps "but it reads more
  elegantly" — readers pattern-match those characters to bot output,
  and on HN that triggers flagging.
- For FailProof AI product discussions specifically, use the context and
  tone guidance in [`INSTRUCTIONS.md`](./INSTRUCTIONS.md).
