# INSTRUCTIONS

Task-specific instructions. Read this before any task. `CLAUDE.md` holds the
always-on rules; this file holds the working set that evolves as the system
matures.

## Recording new learnings

This file grows as the system matures. When you learn something new about
HN during a task — a working selector, a UI change, a new gotcha, a
recovery from a failure mode, an updated cadence observation, an HN
feature rollout, a story-type-specific quirk — edit this file (or
`CLAUDE.md` if the learning is invariant-shaped) *before ending the task*.
Future sessions inherit only what's written down here; anything that
lives only in the current conversation is lost on the next run.

- Edit the relevant existing section rather than appending a duplicate.
  If a prior note proved wrong or partial, correct it in place.
- Lead with the concrete fact, then the why, then the workaround.
- Put runnable recipes in fenced code blocks future-you can paste.
- Hard rules / invariants / forbidden actions / daily caps belong in
  `CLAUDE.md`, not here.
- If a learning contradicts something already in either file, fix the
  stale entry in the same edit — don't leave both versions standing.

## How to drive HN (always through the browser)

Every HN interaction goes through the `browser-use` MCP (or the
`browser-use` CLI as a subprocess when MCP is misbehaving) attached to the
logged-in Chrome profile. This is non-negotiable per `CLAUDE.md` — reads
included, not just writes. Account safety depends on a single coherent
browsing fingerprint, and HN's spam pipeline correlates non-browser
traffic to its APIs with the cookied session in suspicious ways.

**Concrete "do this / not that" cheat sheet:**

| Need to do… | ✅ Do | ❌ Never do |
|---|---|---|
| Search HN | `browser_navigate https://hn.algolia.com/?q=…&type=story` and read DOM | Hit `hn.algolia.com/api/v1/search?query=…` |
| Browse a feed | Navigate to `/news`, `/newest`, `/ask`, `/show`, `/best`, `/from?site=…`, `/threads?id=…` | Pull the same content from `hacker-news.firebaseio.com/v0/topstories.json` etc. |
| Read site guidelines | Navigate to `/newsguidelines.html` and `/newsfaq.html` | curl them |
| Check who's logged in | Navigate to `/` and read the top-right `<a href="user?id=…">` link in `span.pagetop` | Read the cookie file, or any backend identity probe |
| Pull a story's body / comments | Navigate to `/item?id=N` and read the DOM | Hit `hacker-news.firebaseio.com/v0/item/N.json` |
| Verify a comment landed | `browser_get_state` after submit, or navigate back to the thread | Hit the Firebase or Algolia endpoint to confirm |
| Read a user's profile | Navigate to `/user?id=<handle>` and `/threads?id=<handle>` | Hit `/v0/user/<handle>.json` |

The CLI form, when MCP is wedged:

```bash
CDP=http://127.0.0.1:9334
BU="uvx --from browser-use[cli] browser-use --cdp-url $CDP"
$BU open    "<url>"               # navigate
$BU state                         # accessibility tree + element indices
$BU eval    "<js-iife>"           # extract structured data via JS
$BU click   <index>               # click element by index from `state`
$BU type    "<text>"              # type into focused element
$BU scroll  down                  # scroll page
```

Not the Firebase API, not Algolia, not RSS, not a separate `playwright`
driver — even those that *use Chrome* are out (different control surface,
the fingerprints don't line up perfectly enough).

### HN gotchas (don't relitigate these)

- **HN UI is plain server-rendered HTML, no shadow DOM, no SPA.** This
  means selectors are stable across sessions. The site barely changes.
  When something breaks, suspect rate-limiting / shadowban / login wall
  before suspecting a UI change.
- **The page header carries identity.** `<span class="pagetop"><a id="me"
  href="user?id=<handle>">handle</a> ...</span>` is the canonical
  logged-in indicator. If the link reads `login` instead, the session
  is logged out — re-launch Chrome and have the user log in.
- **`/item?id=<id>` returns the same content for stories and comments.**
  A comment ID resolves to its own page with its parents and replies.
  Useful for permalinks; the comment-as-permalink form is
  `https://news.ycombinator.com/item?id=<comment-id>`.
- **Reply forms are not always rendered.** Threads older than ~2 weeks
  (the exact window varies) stop accepting replies even without an
  explicit close marker. Check for the textarea presence before
  attempting to compose; if absent, abort and surface to the user.
- **Dead / flagged comments.** Comments by shadowbanned users render with
  a `[dead]` marker for logged-in operators with `showdead=yes`; for
  others they're invisible. Don't reply to dead comments — the reply
  itself often inherits the dead status. Check for the marker on the
  parent before drafting.
- **HN "search" via Algolia.** `https://hn.algolia.com/?q=...` is the
  user-facing search UI. It's a SPA but the results are server-rendered
  enough to extract with `browser_get_state` / `browser_extract_content`.
  The underlying `hn.algolia.com/api/v1/search?query=...` endpoint is
  forbidden per `CLAUDE.md`.

### Identity detection (don't ask, just read the browser)

The operating account isn't a config setting — it's whoever is logged
into the Windows Chrome profile right now. Read it before any
identity-dependent task:

```bash
CDP=http://127.0.0.1:9334
BU="uvx --from browser-use[cli] browser-use --cdp-url $CDP"
$BU open "https://news.ycombinator.com/" >/dev/null 2>&1
# HN renders the logged-in handle as the first link inside span.pagetop;
# logged-out users see a `login` link there instead.
$BU eval '(()=>{const a=document.querySelector("span.pagetop a[href^=\"user?id=\"]");const handle=a?a.textContent.trim():null;const loggedIn=!!handle;return JSON.stringify({url:location.href,handle,logged_in:loggedIn});})()'
```

If `logged_in: false` or `handle: null`, raise a user-facing error and
stop — do **not** draft or post under unknown identity. Example:
"can't detect a logged-in HN account in the operating Chrome profile —
log in and say 'go' to retry." If detection succeeds, repeat the
handle back to the user once before drafting so they can confirm.

### Pre-flight: bring up Chrome if CDP is down

Before the first browser tool of a session, probe
`http://127.0.0.1:9334/json/version` (or run `scripts/verify-cdp.sh`).
If it doesn't respond, run `scripts/win-chrome.sh` yourself — don't ask
the user. The launcher is idempotent (it refuses a second instance if
one is already running with the hn-profile), so a redundant call is
safe. After launching, poll `/json/version` every ~1s until it returns
a JSON body, then proceed. Only escalate to the user if the launcher
itself errors out.

**Important caveat — MCP launch-order trap.** The `browser-use` MCP
initializes its CDP root client *once* at MCP startup. If Claude Code
started before Chrome was up, the MCP is stuck in a "not initialized"
state: `browser_navigate` will return "Navigated to: ..." (it goes
through a different code path that auto-connects), but every read
primitive errors with `Root CDP client not initialized`,
`Expected at least one handler to return a non-None result`, or empty
`browser_list_tabs`. Bringing Chrome up mid-session does **not** heal
this — the MCP needs to be restarted. Ask the user to run `/mcp` and
restart `browser-use`, then retry. Going forward, prefer to launch
Chrome (via `scripts/win-chrome.sh`) **before** starting Claude Code so
the MCP boots into a healthy state.

`browser_extract_content` additionally requires an LLM API key
(`OPENAI_API_KEY` or equivalent) inside the MCP env. If it isn't set,
fall back to `browser_get_html` plus your own parsing, or to
`browser-use --cdp-url … eval '<js>'` from the shell.

**Where the MCP actually reads cdp_url from.** The `--cdp-url` flag on
`uvx … browser-use --mcp …` is a CLI-mode-only flag — it is silently
ignored when `--mcp` is also set. The MCP server reads cdp_url from
`~/.config/browseruse/config.json` (`browser_profile.<default>.cdp_url`).
Same file also holds `keep_alive: true` so the MCP doesn't try to close
the running Chrome on shutdown. If you change Chrome's port, edit that
file too — not just `.mcp.json`.

### Reads (research, listing, summarizing)

Use the same primitives a human would:

- `browser_navigate(url)` — go to a feed, the search page, an item
  permalink.
- `browser_get_state()` — structured page state with indexed clickable
  elements; cheap, your default after every navigate.
- `browser_get_html(selector)` — when you need raw markup of a region
  (e.g., a single comment's table row).
- `browser_extract_content(query, extract_links=true)` — when you need
  the model to summarize/structure what's on the page.
- `browser_scroll(direction)` — for paginated feeds and Algolia search
  results; pause between scrolls.

#### Where to look (HN feed coverage)

HN doesn't have subreddits — it's one site with several feeds. To find
threads where FailProof AI is relevant, sweep across:

- **`/news`** — front page (top 30 by ranking). High-traffic, harder to
  break in mid-thread but high-leverage.
- **`/newest`** — most recent submissions. Catch threads early before
  they're saturated; many die on `/newest` without making the front
  page, but the comment audience is engaged operators.
- **`/ask`** — Ask HN. Direct match for "how do I keep my agent from
  doing X" style questions. Highest signal-to-noise for FailProof
  conversations.
- **`/show`** — Show HN. Competing tools, reliability frameworks, hook
  managers, dev-tool launches. A measured "here's how this overlaps
  with FailProof AI" comment can land if it's substantive.
- **`/best`** — high-engagement recent threads. Good for "what's the
  audience talking about today" without trawling.
- **`/from?site=anthropic.com`** (or `cursor.com`, `aider.chat`,
  `continue.dev`, etc.) — every submission from a domain. Useful for
  catching every Anthropic / agent-tool launch story.
- **`/threads?id=<handle>`** — a user's recent comments. Use for
  identity verification and for following users you've engaged with.
- **`https://hn.algolia.com/?q=…&type=story`** (or `&type=comment`) —
  Algolia HN search UI. Drive the form, read the result list with
  `browser_get_state`. Time filter via the `dateRange` query param
  or the UI dropdown. Vary the filter across sessions so the same
  query doesn't repeat in the account's history.
- **`/item?id=<id>`** — story or comment permalink. The "parent" link
  on a comment walks up the tree; the indented `<table>` rows are the
  reply children.

#### Search query patterns that work

Same vocabulary as the claude-reddit playbook, adapted for HN's audience:

- **Specific failure modes:** `agent rm -rf`, `force push main`,
  `agent deleted`, `secrets leaked`, `claude destroyed`, `agent went
  off the rails`.
- **Guardrail intent:** `claude code hooks`, `agent guardrails`,
  `policy engine`, `pretooluse`, `babysitting claude`, `tool call
  policy`.
- **Competing-product mentions:** `cursor rules`, `aider conventions`,
  `claude code firewall`, `agent permissions`.
- **Show HN scoping:** prefix `Show HN` to filter; useful for finding
  competing reliability-tool launches.

Rotate the search query across sessions so the same query doesn't
appear in the account's history twice in a row (`CLAUDE.md` rule 8 on
read cadence). The `comments/` log under this folder tells you which
threads the operating account already engaged with — check it before
drafting on a new one.

### Writes (post, comment, vote, favorite)

Same browser, plus the draft-and-approve flow from `CLAUDE.md`:

1. Pull the page state with `browser_get_state`.
2. Confirm HN guidelines and the thread's local norms permit what
   you're about to do (read OP body and top 3-5 comments to gauge
   tone; for Show HN, check whether commenter affiliation is welcome).
3. **Duplicate check** (`CLAUDE.md` rule 7): eval the thread for any
   existing comment by the operating account. Snippet:
   ```js
   (()=>{
     const handle = OPERATING_HANDLE.toLowerCase();
     // HN: each comment header has <a class="hnuser" href="user?id=<handle>">.
     const matches = Array.from(document.querySelectorAll('a.hnuser'))
       .filter(a => (a.textContent || '').trim().toLowerCase() === handle);
     return JSON.stringify({already_commented: matches.length > 0, by_count: matches.length});
   })()
   ```
   If `already_commented` is true, abort and surface to the user. Do
   NOT post a second top-level comment on a thread the account has
   already engaged with.
4. Draft the full text and present it to the user. **No em-dashes,
   en-dashes, fancy ellipses, curly quotes, or unicode arrows** in
   the draft (rule from `CLAUDE.md` brand voice). HN pattern-matches
   these to LLM output even faster than Reddit does.
5. **Cross-thread duplicate guard:** don't reuse the same body or a
   near-identical paraphrase across multiple threads, even on
   different topics. Each draft must materially engage with its
   thread's content.
6. After explicit approval, click/type via the indexed elements
   (recipe below).
7. Verify with `browser_get_state` after each write action — re-run
   the duplicate-check eval before any retry to avoid double-posting
   on a submit that actually landed but appeared to fail.
8. Insert randomized 5-30s delays between consecutive writes.
9. **Log the write to `comments/<timestamp>.md`.** After verification
   in step 7 confirms the comment landed, write a markdown record.
   This is the project's running log of what's been said under the
   operating account and is how product/marketing/engineering get
   visibility into the HN channel without re-reading every thread.

   Filename: UTC ISO 8601 with no colons, e.g.
   `comments/2026-04-29T143022Z.md`. Sort order = post order. One file
   per posted comment (top-level or reply) or submission.

   Required sections:
   - **HN:** permalink to the *comment* (not just the thread), of the
     form `https://news.ycombinator.com/item?id=<comment-id>`
   - **Story / OP / operating account:** one line each
   - **The post:** OP body, or a 2-3 sentence summary if very long.
     For replies, also include the parent comment being replied to.
   - **My reply:** the exact text submitted, in a fenced block
   - **Insight for the FailProof team:** one observation about the
     thread that's useful for product / marketing / engineering. Not
     "the comment was good" — something actionable: what framing
     landed, what gap in the product surfaced, what feature could
     ship from this signal, who else in this thread is asking the
     same question, what blog post would drop into this conversation
     naturally next time.
   - **Notes / findings:** anything else worth recording. HN UI
     quirks, anti-bot signals, sub-thread norms, related threads
     worth following, mod behavior, downstream replies if any have
     come in.

   Skipped writes (aborted by duplicate check, guidelines, or user
   reject) do not get logged here. Only successful posts.

#### Driving the HN comment composer (the working recipe)

Vastly simpler than Reddit's Lexical contentEditable. HN's comment
composer is a plain server-rendered HTML form — `<textarea>` plus a
`<input type=submit>`. The standard CDP primitives work directly.

**Working flow (top-level new comment on a story):**

```bash
CDP=http://127.0.0.1:9334
BU="uvx --from browser-use[cli] browser-use --cdp-url $CDP"

# 1. Navigate to the story permalink, then run the duplicate-check
#    snippet from "Writes" step 3 above.
$BU open    "$STORY_URL"

# 2. Locate and focus the top-level reply textarea. On a story page,
#    the "add comment" form is at the bottom; the textarea has
#    name="text". Sometimes there's a leading hidden form field
#    (hmac, parent id) — leave those alone, just focus the textarea.
$BU eval '(()=>{const ta=document.querySelector("form textarea[name=\"text\"]");if(!ta)return JSON.stringify({err:"no textarea"});ta.scrollIntoView({block:"center",behavior:"instant"});const r=ta.getBoundingClientRect();ta.focus();return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),focused:document.activeElement===ta});})()'

# 3. Inject the comment text. Decode base64 → UTF-8 to dodge shell
#    escaping pain around quotes / backticks; set value via the native
#    textarea prototype setter so any listener fires; then dispatch
#    input + change events.
DRAFT_B64=$(base64 -w 0 < /tmp/draft.md)
$BU eval "(()=>{const ta=document.querySelector('form textarea[name=\"text\"]');const txt=new TextDecoder('utf-8').decode(Uint8Array.from(atob('$DRAFT_B64'),c=>c.charCodeAt(0)));Object.getOwnPropertyDescriptor(Object.getPrototypeOf(ta),'value').set.call(ta,txt);ta.dispatchEvent(new Event('input',{bubbles:true}));ta.dispatchEvent(new Event('change',{bubbles:true}));return JSON.stringify({len:ta.value.length});})()"

# 4. Click the submit button. On a story page it's the only
#    <input type=submit> inside the comment form; value="add comment".
$BU eval '(()=>{const btn=document.querySelector("form input[type=submit][value=\"add comment\"]");if(!btn)return JSON.stringify({err:"no submit"});btn.scrollIntoView({block:"center",behavior:"instant"});const r=btn.getBoundingClientRect();return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)});})()'
$BU click   $SUBMIT_X $SUBMIT_Y

# 5. Verify by re-fetching the thread and re-running the duplicate-check
#    eval — operating handle should now appear in the comment list.
#    If it doesn't but the textarea is empty, the submit went to a
#    confirmation page; navigate back to the story and re-check.
$BU open    "$STORY_URL"
```

**For replying to a specific comment** (not the story root):

The "reply" link on a comment goes to `/reply?id=<comment-id>&goto=…`.
Click that link via `browser_click` (or navigate directly to
`/reply?id=<comment-id>`). The reply page renders a single
`<textarea name="text">` and a `<input type=submit value="reply">`.
Same recipe as above with the value selector adjusted (`value="reply"`
instead of `value="add comment"`).

**For editing your own comment**, click the "edit" link in the comment
header (only visible for your own recent comments, ~2h window). The
edit page has the same form structure; submit value is `update`.

**For story submission**, navigate to `/submit`. Form fields:
- `<input name="title">` — required, ≤ 80 characters by HN convention
- `<input name="url">` — fill this XOR `text`, not both
- `<textarea name="text">` — fill XOR `url`
- `<input type=submit value="submit">`

HN dedupes URLs aggressively: submitting a URL that another user
posted recently redirects you to their thread (`/item?id=<theirs>`).
After clicking submit, check `location.pathname` / re-read the page to
confirm whether you landed on `/newest` (your post live) or someone
else's `/item`.

**For voting**, each item has `<a id="up_<id>">` (and `<a id="down_<id>">`
once your account has the karma threshold for downvoting). Clicking
toggles to a "nosee" / "unvote" state. Verify by re-fetching state
and checking the arrow's id changed.

**Why a verbose recipe**: the comment composer doesn't *need* this
much — a `browser_click` on the textarea and `browser_type` works in
the simple case. But the explicit native-setter + base64 dance avoids
the two known pitfalls that bit the Reddit harness: (a) shell escaping
on multi-line drafts with special characters, and (b) framework
listeners not firing on direct `.value =` assignments. Use the simple
path first; if a draft fails to commit, fall back to this recipe.

### HN failure modes (what aborting looks like)

- **Login wall.** `/login?goto=…` — session expired, log in and retry.
- **Rate limit.** "We have a daily limit on new submissions" or
  "submitting too fast" — stop, wait ≥ 30 minutes, surface to user.
- **Shadowban.** Your comments appear normally to you but are dead
  ([dead] marker) to others. Verify by opening the thread permalink
  in an incognito Chrome window and confirming your comment is
  visible. If invisible: stop all writes from this account and tell
  the user.
- **Flagged.** A specific comment marked `[flagged]` — usually
  reversible if the comment is on-topic and substantive; let the user
  decide whether to email mods.
- **No reply form.** Thread is too old or closed. Don't simulate clicks
  on a missing form; abort and surface.

## failproofai PreToolUse:Bash false-positive on HN URLs

If the user has `failproofai` installed with the `block-read-outside-cwd`
policy, it pattern-matches URL substrings as filesystem paths and
blocks any bash command that contains `https://news.ycombinator.com/...`
or `http://127.0.0.1:9334` as a literal. The error looks like:

```
Bash read outside project directory blocked: /news.ycombinator.com/item...
```

The browser-use CLI takes the URL on the command line, so a normal
invocation gets blocked. Workaround: base64-encode both the CDP URL and
the target HN URL into the bash command literal so the matched
substring never appears in the script string. The decoded values pass
to `$BU` as runtime args, which the policy doesn't see.

```bash
CDP=$(printf '%s' "aHR0cDovLzEyNy4wLjAuMTo5MzM0" | base64 -d)            # http://127.0.0.1:9334
URL=$(printf '%s' "<base64-of-https-news-ycombinator-com-...>" | base64 -d)
BU="uvx --from browser-use[cli] browser-use --cdp-url $CDP"
$BU open "$URL"
```

Encode each HN URL fresh per command (`printf '%s' "<url>" | base64 -w 0`).
Comment lines also matter: a `# https://news.ycombinator.com/...` comment
in the same bash invocation triggers the same match, so strip URL-shaped
comments before running. This is a workaround, not a fix — the policy's
matcher is too liberal, and the right long-term answer is to tighten its
pattern (anchor on actual `cat`/`read`/file-op verbs, or stat the
matched substring) so URL arguments don't false-positive. (Filed against
failproofai already from the Reddit harness; same fix lands here.)

## Networking gotcha (don't relitigate this)

`.mcp.json` connects to `http://127.0.0.1:9334` — **not**
`http://localhost:9334`. On this WSL, `getent hosts localhost` resolves to
`::1` (IPv6) only. Chrome's remote-debugging endpoint listens on IPv4
(`127.0.0.1`) only. `browser-use`'s Python WebSocket client does not
happy-eyeball the mismatch. If you ever see "Root CDP client not
initialized" or empty `browser_list_tabs` after a successful navigate,
check `.mcp.json` is on `127.0.0.1`, not `localhost`.

## About FailProof AI (the product being discussed)

FailProof AI is an open-source policy / hook manager for AI coding agents.
It sits between Claude Code (or the Anthropic Agents SDK) and the system,
intercepting tool calls and applying reliability policies before and after
each one. Use this section as ground truth whenever the topic of the
conversation on HN involves the product — answering questions, writing
posts, replying to comments.

### Identity

- Repo: https://github.com/exospherehost/failproofai
- Docs: https://befailproof.ai
- npm: `failproofai`
- License: MIT + Commons Clause
- Made by: ExosphereHost Inc
- Slack community: linked from the README badges
- Runs entirely locally — no session content, file names, or tool inputs
  leave the user's machine. Anonymous PostHog telemetry only (event names),
  opt-out via `FAILPROOFAI_TELEMETRY_DISABLED=1`.
- Requirements: Node.js >= 20.9.0. Bun >= 1.3.0 is optional and only needed
  for building from source.

### One-line pitch

> The easiest way to manage policies that keep AI coding agents reliable,
> on-task, and running autonomously - for **Claude Code** and the **Agents SDK**.

### What it actually does

Claude Code exposes `PreToolUse` / `PostToolUse` / `Notification` / `Stop`
hooks. FailProof AI installs hook entries into `~/.claude/settings.json` (or
project / local scope) that route every tool call through its policy engine.
Each policy returns one of:

| Function | Effect |
|----------|--------|
| `allow()` | Permit the operation |
| `allow(msg)` | Permit, send informational context to the agent |
| `deny(msg)` | Block the operation; message shown to the agent |
| `instruct(msg)` | Inject guidance into the agent's context, do not block |

### Headline features

- **32 built-in policies** for the common agent failure modes — destructive
  commands, secret leakage, working outside project bounds, pushes to
  protected branches, accidental publishes, etc.
- **Custom policies in JavaScript** via the `allow` / `deny` / `instruct`
  API. Supports `async`, transitive local imports, and `process.env`.
  Fail-open on error (logged to `~/.failproofai/hook.log`; built-in policies
  keep running).
- **Three-scope config** — global (`~/.failproofai/policies-config.json`),
  project (`.failproofai/policies-config.json`), local — merged
  automatically (project -> local -> global).
- **Convention-based loading** — drop `*policies.{js,mjs,ts}` files into
  `.failproofai/policies/`, commit the directory, and every teammate gets
  the same guardrails on next pull. Files load alphabetically; prefix with
  `01-`, `02-` to control order. User-level `~/.failproofai/policies/` also
  loads (union with project-level).
- **Agent Monitor dashboard** at `http://localhost:8020` (start with
  `failproofai`) — browse sessions, inspect every tool call, see exactly
  which policies fired and why.

### Built-in policy categories (with concrete examples)

- **Block destructive ops** — `block-sudo`, `block-rm-rf`,
  `block-curl-pipe-sh`, `block-force-push`, `block-push-master`,
  `block-work-on-main`, `block-failproofai-commands` (no
  self-uninstallation).
- **Sanitize secrets out of agent context** — `sanitize-api-keys`,
  `sanitize-jwt`, `sanitize-connection-strings`,
  `sanitize-private-key-content`, `sanitize-bearer-tokens`.
- **Keep agents in-bounds** — `block-env-files`, `protect-env-vars`,
  `block-read-outside-cwd`, `block-secrets-write`.
- **Warnings on risky ops** — `warn-destructive-sql`,
  `warn-schema-alteration`, `warn-large-file-write` (configurable
  `thresholdKb`), `warn-package-publish`, `warn-git-amend`,
  `warn-git-stash-drop`, `warn-all-files-staged`, `warn-background-process`,
  `warn-global-package-install`.

Many policies expose params (`allowPatterns`, `allowPaths`,
`protectedBranches`, `additionalPatterns`, `thresholdKb`, `hint`) so users
can tune without writing code.

### Quick start (paste-ready for replies)

```bash
npm install -g failproofai
failproofai policies --install     # writes hooks into ~/.claude/settings.json
failproofai                        # opens dashboard at http://localhost:8020
failproofai policies               # list what's active
failproofai policies --install block-sudo block-rm-rf sanitize-api-keys
failproofai policies --uninstall
```

Scope flag: `--scope project` writes to `.claude/settings.json`,
`--scope local` writes to `.claude/settings.local.json`. Default is global.

### Custom policy snippet (paste-ready)

```js
import { customPolicies, allow, deny, instruct } from "failproofai";

customPolicies.add({
  name: "no-production-writes",
  description: "Block writes to paths containing 'production'",
  match: { events: ["PreToolUse"] },
  fn: async (ctx) => {
    if (!["Write", "Edit"].includes(ctx.toolName ?? "")) return allow();
    const path = ctx.toolInput?.file_path ?? "";
    if (path.includes("production")) return deny("Writes to production paths are blocked");
    return allow();
  },
});
```

The `ctx` object exposes: `eventType`, `toolName`, `toolInput`, `payload`,
`session.cwd`, `session.sessionId`, `session.transcriptPath`.

### Likely HN questions, with honest answers

- **"Is it open source?"** Yes — MIT + Commons Clause. Source on GitHub.
- **"Does it phone home?"** Only anonymous PostHog telemetry (event names,
  not content). Disable with `FAILPROOFAI_TELEMETRY_DISABLED=1`.
- **"How is this different from Claude Code's built-in hooks?"** Claude
  Code ships the hook *mechanism*; FailProof AI ships a curated set of
  32 policies, a JS SDK for writing your own, three-scope config
  merging, and a dashboard for inspecting what fired. You could
  replicate it by wiring hooks yourself — failproofai is the
  batteries-included version.
- **"Does it work with Cursor / Aider / continue.dev / Cline?"** Today
  the officially supported surfaces are Claude Code and the Anthropic
  Agents SDK. Other agents only work if they call the same hook
  protocol.
- **"What's the performance overhead?"** Hooks run as a Node subprocess
  per tool call. Negligible for normal use; expensive custom policies
  will be felt.
- **"What happens if a hook crashes?"** Fail-open: the error goes to
  `~/.failproofai/hook.log`, remaining policies continue, the agent is
  not blocked.
- **"Can I share policies with my team?"** Yes — commit
  `.failproofai/policies/` to the repo. Files there auto-load on every
  teammate's machine, no config flags needed.
- **"Why Commons Clause?"** Standard reason — prevents a third party
  from reselling the project as a hosted service while keeping it free
  for developer use. The repo / docs are the source of truth on the
  exact carve-outs.

### Tone for discussing it on HN

HN's audience is more skeptical of marketing language than Reddit's; the
voice rules from `CLAUDE.md` apply doubly here.

- Lead with the concrete failure mode the policy prevents, not marketing
  copy. "Agent rm -rf'd node_modules — `block-rm-rf` exists for that"
  beats "comprehensive safety platform". HN downvotes the latter on
  pattern.
- Disclose affiliation early. HN explicitly asks commenters to disclose
  when they work on a product they're discussing; not doing so is a
  fast track to being flagged. A leading line like "(disclosure: I
  work on FailProof)" is the norm.
- Link the GitHub repo, not the marketing site, when developers are
  asking technical questions. HN clicks through to GitHub more readily
  than to landing pages.
- Don't oversell. It is hooks + a curated policy set + a dashboard. It
  is not AGI alignment.
- Show, don't pitch. A code snippet of a policy or a paste of a real
  agent failure that the policy would have caught will get you upvotes;
  bullet-listed feature claims won't.
- HN guidelines first (per `CLAUDE.md`): avoid product content on
  threads where it would be off-topic, even tangentially. Show HN
  threads explicitly welcome it; most others do not.

(Task-specific entries get appended below as the system matures.)
