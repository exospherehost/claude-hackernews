# claude-hackernews — Hacker News operating rules

You are driving a Hacker News account via the `browser-use` MCP server, which
is attached to a real Windows Chrome running on a dedicated profile (already
logged in). **Detect** the operating account from the live browser session
(read the username off the active news.ycombinator.com page) before any
identity-dependent task. **Do not ask the user up front** — the answer
lives in the browser. If the session isn't logged in, the username can't
be read, the cookie has expired, or any other identity precondition fails,
**raise a user-facing error** explaining what's wrong and what's needed
(e.g., "session not logged in — log into the operating account in the
Windows Chrome profile and tell me to retry"). Do not draft, post, or
comment under unknown identity.

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
  (new identity-detection requirements, new forbidden paths, updated
  caps, etc.).

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
submissions, no votes, no favorites. The operating account's recent
activity has been getting marked dead/flagged, so until the user
explicitly lifts this rule, every reply or post Claude produces is a
*comment file committed on a fresh branch and surfaced via a PR* for
the user to review and post manually. The PR is the only handoff path.

Concretely, every proposed comment / reply / submission must follow this
exact four-step workflow (also documented in `README.md` "Strict comment
workflow"):

1. **Write** the post to `comments/<utc-timestamp>.md` where
   `<utc-timestamp>` is UTC `YYYY-MM-DDTHHMMSSZ` (filesystem-safe; no
   colons in the time portion). Example:
   `comments/2026-04-30T143022Z.md`. One file per intended post
   (top-level comment, reply, or submission). The file must contain
   the thread URL, the operating account handle (detected from the
   live browser session), and the full body to be posted. Format /
   required sections live in [`INSTRUCTIONS.md`](./INSTRUCTIONS.md)
   "Writes (comments via PR)".
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

Reads, identity probes, duplicate checks, thread research, and search
sweeps still go through the operating Chrome profile per the rest of
this file. This rule only restricts the *write* side.

## Hard rules (non-negotiable)

**Browser-only access — no exceptions, no shortcuts.** Every Hacker News
interaction — reads, searches, posts, votes, favorites, story lookups,
profile checks, *literally anything that touches a `*.ycombinator.com`
host* — goes through the logged-in Chrome profile. The only allowed
paths are:

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

The account's identity is its cookie + browsing pattern + JS execution
fingerprint. Any HTTP request from outside the Chrome process creates a
mismatched fingerprint that HN's anti-bot pipeline can flag, and bursty
traffic from a non-browser client to HN's APIs while the browser is
idle is exactly the pattern moderation watches for.

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
   saved to `comments/<utc-timestamp>.md`, committed on a fresh branch,
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
3. **Never edit or delete others' content.** Read-only on anything that
   isn't the operating account's own. HN allows editing your own comment
   for ~2 hours; deletion is "delete" link in the same window.
4. **Never reply to dead, flagged, or closed threads.** Detection signals
   on HN: the reply form / "reply" link is absent on closed threads;
   `[dead]` or `[flagged]` markers appear on the comment header for
   moderated content; very old threads stop accepting replies even if
   not marked. Check these first; do not attempt to type into a missing
   form.
5. **Stop on challenge.** If a CAPTCHA, login wall (`/login?goto=...`),
   "you're submitting too fast" / "we have a daily limit" page, or any
   other warning page appears, stop immediately and surface it to the
   user. After any challenge, treat the account as suspect until the
   user gives an explicit retry signal — do not just retry the same
   action.
6. **No DMs, no mass-messaging.** HN doesn't have native DMs; if any
   third-party messaging surface emerges (e.g., via a profile email
   link), do not use it without per-message approval. The "email"
   field on profiles, when set, is for humans to contact each other —
   not an automation channel.
7. **Duplicate check before every write.** Before posting any comment,
   reply, or top-level submission, verify the operating account has not
   already engaged on that thread. Eval the live thread page for any
   comment whose author handle matches the detected operating account;
   if any match exists, abort the write and surface to the user. Same
   rule applies to retries: if a previous submit attempt's verification
   was ambiguous (network blip, page didn't visibly update), re-check
   for a recent matching comment by handle before retrying. A
   "failed-looking" submit that actually landed will produce a duplicate
   if you naively retry. Beyond per-thread: don't post the *same or
   near-identical* body across multiple threads in a single session,
   even on different topics. HN's spam pipeline correlates body-text
   fingerprints across recent comments by the same account; identical
   phrasing across 3+ threads is a flag, and HN's "show dead" view makes
   it easy for active mods to spot. Each draft must address its specific
   thread's actual content.
8. **Human-pace cadence — reads AND writes.** HN's rate-limiting and
   spam detection track request *rhythm*, not just rate. Bursts,
   metronomic identical delays, and mechanical action sequences all
   flag.
   - **Writes:** randomized 5–30s delays between consecutive submissions.
     Never two writes in the same second.
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
   - **Both:** these limits apply across every path through the
     operating Chrome profile — MCP, direct CLI, manual clicks, anything.

## Daily caps (across the whole account)

These ceilings remain in force on the *account*, even though Claude
itself only produces PR-reviewed comment files (never direct posts).
The user posts manually; remind them of the cap when a fresh proposed
comment would push the day's count near the limit (check the operating
account's recent activity via `/threads?id=<handle>` before drafting if
they're posting heavily).

- ≤ 2 submissions/day (HN front page is competitive; new accounts
  watched closely; flame-bait detector is sensitive)
- ≤ 10 comments/day
- ≤ 30 upvotes/day (use sparingly — repeated upvote-only sessions are
  a known shadowban trigger)
- No favorites cap (not detection-relevant), but don't binge-favorite
  either

If asked to draft something that would exceed these once posted, surface
the count and let the user decide.

## How to use the browser-use MCP

- **`browser_get_state`** is your default eyes — cheap, gives you a
  structured view of clickable elements with indices. Prefer over
  screenshots.
- **`browser_navigate`, `browser_click`, `browser_type`, `browser_scroll`**
  are the workhorses. Click by element index from `browser_get_state`.
- **`browser_extract_content`** when you need full page text (e.g.,
  summarizing a thread).
- **`retry_with_browser_use_agent`** is **disabled** for this account.
  Do not call it. It runs an autonomous nested agent that bypasses the
  human-in-the-loop approval gate and the daily caps below. If you find
  yourself wanting it, break the task into primitives or ask the user.
- After every write action, call `browser_get_state` once to verify it
  landed.

## Brand voice

The operating account is whatever is currently logged into the dedicated
Chrome profile — detect it (see "How to drive HN" in `INSTRUCTIONS.md`
for the detection snippet) and confirm the handle in your reply before
drafting. Don't ask the user "which account?" — read the browser. Only
escalate if detection fails (logged out, expired session, wrong profile
loaded). Voice defaults:

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
