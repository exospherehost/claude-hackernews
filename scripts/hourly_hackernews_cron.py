#!/usr/bin/env python3
"""hourly_hackernews_cron.py - hourly trigger for the claude-hackernews HN job.

Wire this into system cron at the top of every hour. The script itself
decides whether THIS PARTICULAR hour actually does work, via two gates:

  1. Working-hours window. Outside the window, exit immediately (success).
  2. A random pre-run sleep. Even on hours that run, we don't all fire
     at HH:00:00 sharp.

When both pass, the script first ensures the operating Chrome is up
(via scripts/win-chrome.sh, idempotent; polls scripts/verify-cdp.sh until
CDP responds) and then shells out to:

    luv <LUV_REPO> "<LUV_PROMPT>" -nit

(luv: https://github.com/exospherehost/luv -- a thin launcher that clones
the repo and runs Claude non-interactively against it.)

The wrapper does NOT close Chrome on its own. The agent (running inside
luv) is responsible for closing the browser at end-of-run, per the
"End-of-run cleanup" section in INSTRUCTIONS.md. This split exists
because (a) browser_close_all in the MCP is a no-op against chrome.exe
when keep_alive: true is set in the browser-use config, so an OS-level
Stop-Process is required, and (b) bringing Chrome up here (before the
MCP boots) sidesteps the "MCP launch order" trap documented in
CLAUDE.md.

HN runs are PR-only by policy (see CLAUDE.md "Comments via PR (never
direct post)" and README.md "Strict comment workflow"). The default
LUV_PROMPT asks the agent to find a relevant thread, write the proposed
reply to comments/<utc-timestamp>.md, commit on a fresh branch, push,
and open a PR for human review. The agent never types into the HN
composer or clicks submit.

Monitoring posts to a Discord webhook (one message per lifecycle event):

    start           -- "this run started"
    skip            -- "outside working hours"
    chrome-fail     -- Chrome bring-up failed
    ok              -- luv finished OK AND a new PR was opened on GH_REPO
                       this run (body = full output + log buffer + PR URL)
    noop            -- luv finished OK but no new PR appeared (body =
                       full output + log buffer); yellow embed so silent
                       no-ops are visible to the operator
    fail            -- luv finished non-zero (body = full output + log buffer)

Each event is a colored Discord embed. If the body exceeds Discord's
embed-description limit it is attached as a `cron.log` file via
multipart instead of being truncated.

Set CRON_DISCORD_WEBHOOK_URL via env var (or edit the constant below).
Leave it empty to disable Discord posting entirely.

Crontab line (every hour at minute 0, run as the user that owns
claude-hackernews and has `luv` + `claude` + `gh` on PATH):

    PATH=/home/<user>/.local/bin:/usr/local/bin:/usr/bin:/bin
    CRON_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
    0 * * * * /usr/bin/python3 /absolute/path/to/scripts/hourly_hackernews_cron.py >> ~/claude-hackernews-cron.log 2>&1

The PATH= line is required because cron's default PATH does not include
~/.local/bin where luv/claude live.

If you also run the sibling claude-reddit cron on the same machine, give
each line its own CRON_DISCORD_WEBHOOK_URL value (cron honors per-line
env overrides) so HN and Reddit lifecycle events can land in separate
Discord channels.

Smoke-testing without waiting for cron, working-hours bypassed and zero
pre-run sleep:

    CRON_FORCE=1 python3 scripts/hourly_hackernews_cron.py

All other constants below are also overridable by env var (CRON_<NAME>),
so individual gates can be tweaked without editing the source.

Stdlib only - no pip install required.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

_rng = random.SystemRandom()

# --------------------------------------------------------------------------
# CONFIG. Each constant has a CRON_<name> env-var override (parsed below).
# --------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        print(
            f"[cron] WARN: env {name}={v!r} is not an int, using default {default}",
            file=sys.stderr,
        )
        return default


def _env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


# Working hours, in the system's local timezone. Inclusive start, exclusive
# end. Default 09:00 - 21:00.
WORK_HOURS_START = _env_int("CRON_WORK_HOURS_START", 9)
WORK_HOURS_END = _env_int("CRON_WORK_HOURS_END", 21)

# Random pre-run sleep range, in seconds. Picked uniformly per run so the
# real start time is jittered across the hour. Keep MAX comfortably under
# 3600 so a slow run can still finish before the next cron tick.
WAIT_MIN_SECONDS = _env_int("CRON_WAIT_MIN_SECONDS", 30)
WAIT_MAX_SECONDS = _env_int("CRON_WAIT_MAX_SECONDS", 25 * 60)

# luv invocation. LUV_REPO is what you'd type after `luv` on the CLI;
# LUV_PROMPT is the natural-language task. Both are configurable here.
LUV_BINARY = _env_str("CRON_LUV_BINARY", "luv")
LUV_REPO = _env_str("CRON_LUV_REPO", "claude-hackernews")
LUV_PROMPT = _env_str(
    "CRON_LUV_PROMPT",
    "Take a fresh context of everything on failproofai on "
    "github.com/exospherehost/failproofai and find a Hacker News thread "
    "where failproofai is genuinely relevant to the discussion. Follow "
    "the strict comment workflow in README.md: write the proposed reply "
    "to comments/<utc-timestamp>.md on a fresh branch, commit, push, and "
    "open a PR for human review before posting. Do not type into the HN "
    "composer or click submit; the PR is the only handoff path.",
)

# Hard wall on how long luv may run before we kill it and report failure.
LUV_TIMEOUT_SECONDS = _env_int("CRON_LUV_TIMEOUT_SECONDS", 45 * 60)

# GitHub repo (owner/name) the agent is expected to open PRs against. Used
# by the no-op detector below: cron snapshots PR numbers before / after the
# run, and a green "ok" only fires when a new PR appeared. Any clean luv
# exit without a new PR posts a yellow "noop" instead, so silent dead-ends
# are visible.
GH_REPO = _env_str("CRON_GH_REPO", "exospherehost/claude-hackernews")
GH_PR_LIST_TIMEOUT_SECONDS = _env_int("CRON_GH_PR_LIST_TIMEOUT_SECONDS", 30)
GH_PR_LIST_LIMIT = _env_int("CRON_GH_PR_LIST_LIMIT", 200)

# Discord webhook URL. Empty = no posting.
# Format:
#   https://discord.com/api/webhooks/<id>/<token>
# Channel-specific; create via Discord channel "Edit Channel -> Integrations
# -> Webhooks -> New Webhook -> Copy Webhook URL".
DISCORD_WEBHOOK_URL = _env_str("CRON_DISCORD_WEBHOOK_URL", "")

# Optional override for the bot's display name / avatar on each post.
# Empty = use whatever was configured on the webhook itself in Discord.
DISCORD_USERNAME = _env_str("CRON_DISCORD_USERNAME", "")
DISCORD_AVATAR_URL = _env_str("CRON_DISCORD_AVATAR_URL", "")

# Discord caps: content <= 2000 chars, embed.description <= 4096 chars.
# Leave headroom for the surrounding code-fence and "...[truncated]" marker.
DISCORD_INLINE_BODY_MAX = 3500
# Anything longer than this in the raw body goes as a file attachment so the
# user gets the full log without losing data to truncation.
DISCORD_FILE_THRESHOLD = DISCORD_INLINE_BODY_MAX

# Chrome lifecycle helpers (paths resolved relative to this script so the
# crontab line doesn't need to cwd into the repo).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WIN_CHROME_LAUNCH = os.path.join(SCRIPT_DIR, "win-chrome.sh")
VERIFY_CDP_SCRIPT = os.path.join(SCRIPT_DIR, "verify-cdp.sh")
CHROME_BRINGUP_TIMEOUT_SECONDS = _env_int("CRON_CHROME_BRINGUP_TIMEOUT_SECONDS", 30)


# --------------------------------------------------------------------------
# Helpers.
# --------------------------------------------------------------------------

_DISCORD_COLORS = {
    "start": 0x3498DB,  # blue
    "skip":  0x95A5A6,  # gray
    "ok":    0x2ECC71,  # green
    "noop":  0xF1C40F,  # yellow -- ran clean but produced no PR
    "fail":  0xE74C3C,  # red
}

# Buffer of every _log() line in this run. Included as a "log trail" field
# in each Discord post so the user sees the full lifecycle, not just the
# event-specific body.
_LOG_BUFFER: list[str] = []


def _log(msg: str) -> None:
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    line = f"[cron {stamp}] {msg}"
    _LOG_BUFFER.append(line)
    print(line, flush=True)


def _build_multipart(payload_json: dict, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
    """Hand-roll multipart/form-data for Discord webhook file attachments.

    Discord's webhook file upload uses:
      - field "payload_json": JSON for the message
      - field "files[0]": the attached file
    """
    boundary = "----claudehackernews" + uuid.uuid4().hex
    parts: list[bytes] = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="payload_json"\r\n')
    parts.append(b"Content-Type: application/json\r\n\r\n")
    parts.append(json.dumps(payload_json).encode("utf-8"))
    parts.append(b"\r\n")
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'.encode()
    )
    parts.append(b"Content-Type: text/plain; charset=utf-8\r\n\r\n")
    parts.append(file_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _discord_notify(level: str, title: str, body: str = "") -> None:
    """Best-effort Discord webhook post. Never raises; failures hit stderr.

    `level` drives the embed color and is one of: start, skip, ok, fail.
    `title` is the embed title (<= 256 chars; we don't enforce, just trust
    the caller).  `body` is the freeform log content; if it fits inline
    it's embedded as a fenced code block, otherwise it's attached as a
    `cron.log` file via multipart.
    """
    if not DISCORD_WEBHOOK_URL:
        return

    color = _DISCORD_COLORS.get(level, 0x95A5A6)
    host = socket.gethostname()
    footer = {"text": f"{host} - claude-hackernews cron"}
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    embed: dict = {
        "title": title,
        "color": color,
        "footer": footer,
        "timestamp": timestamp,
    }

    long_body = len(body) > DISCORD_FILE_THRESHOLD
    if body and not long_body:
        embed["description"] = f"```\n{body}\n```"

    payload: dict = {"embeds": [embed]}
    if DISCORD_USERNAME:
        payload["username"] = DISCORD_USERNAME
    if DISCORD_AVATAR_URL:
        payload["avatar_url"] = DISCORD_AVATAR_URL

    if long_body:
        # Attach the full body as cron.log; embed gets a short note.
        embed["description"] = (
            f"_Body too long for an embed ({len(body)} chars); "
            f"see attached `cron.log`._"
        )
        data, content_type = _build_multipart(
            payload, "cron.log", body.encode("utf-8")
        )
        headers = {
            "Content-Type": content_type,
            "User-Agent": "claude-hackernews-cron/1",
        }
    else:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "claude-hackernews-cron/1",
        }

    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL, data=data, method="POST", headers=headers
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except (urllib.error.URLError, OSError) as e:
        print(f"[discord] WARN: webhook post failed: {e}", file=sys.stderr)


def _compose_body(event_body: str = "") -> str:
    """Combine the event-specific body with the accumulated _log trail.

    Order: event body first (the headline content - error message, luv
    stdout/stderr, etc.), then a "--- log trail ---" section with every
    _log() line emitted so far. The user gets a single message that
    contains both "what happened" and "how we got here".
    """
    trail = "\n".join(_LOG_BUFFER)
    if event_body and trail:
        return f"{event_body}\n\n--- log trail ---\n{trail}"
    return event_body or trail


def _within_working_hours(now: dt.datetime) -> bool:
    return WORK_HOURS_START <= now.hour < WORK_HOURS_END


def _random_wait_seconds() -> int:
    lo, hi = sorted((WAIT_MIN_SECONDS, WAIT_MAX_SECONDS))
    return _rng.randint(lo, hi)


def _ensure_chrome_up() -> None:
    """Run win-chrome.sh (idempotent) then poll verify-cdp.sh until ready.

    Sidesteps the "MCP launch order" trap (CLAUDE.md): every cron firing
    brings Chrome up before the luv subprocess starts Claude Code, so the
    browser-use MCP boots into a healthy state. Raises RuntimeError on
    failure; caller posts a fail event to Discord and exits non-zero.
    """
    _log(f"ensuring Chrome is up via {WIN_CHROME_LAUNCH}")
    try:
        proc = subprocess.run(
            ["bash", WIN_CHROME_LAUNCH],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"missing launcher script: {e}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Chrome launcher hung past 60s")
    if proc.returncode != 0:
        raise RuntimeError(
            f"Chrome launcher exited {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )

    _log(f"polling CDP via {VERIFY_CDP_SCRIPT} (up to {CHROME_BRINGUP_TIMEOUT_SECONDS}s)")
    deadline = time.time() + CHROME_BRINGUP_TIMEOUT_SECONDS
    last_err = ""
    while time.time() < deadline:
        check = subprocess.run(
            ["bash", VERIFY_CDP_SCRIPT],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if check.returncode == 0:
            _log("Chrome CDP is up")
            return
        last_err = check.stderr or check.stdout
        time.sleep(1)
    raise RuntimeError(
        f"CDP did not come up within {CHROME_BRINGUP_TIMEOUT_SECONDS}s; "
        f"last verify-cdp output: {last_err.strip()[-500:]}"
    )


def _run_luv() -> tuple[int, str]:
    cmd = [LUV_BINARY, LUV_REPO, LUV_PROMPT, "-nit"]
    _log(f"launching: {cmd!r}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=LUV_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"luv binary not found on PATH: {LUV_BINARY!r}"
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return 124, (
            f"timeout after {LUV_TIMEOUT_SECONDS}s\n"
            f"--- stdout ---\n{out}\n--- stderr ---\n{err}"
        )
    return proc.returncode, (
        f"exit={proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )


def _snapshot_pr_numbers() -> set[int] | None:
    """Return the set of PR numbers (any state) currently on GH_REPO.

    Returns None on any failure (gh missing, auth lapsed, network
    hiccup, timeout, non-zero exit, malformed output). The caller treats
    None as "couldn't tell" and posts a noop event rather than risk a
    false-positive "new PR" diff (e.g. failed before-snapshot + clean
    after-snapshot would otherwise look like every existing PR was new).
    """
    try:
        proc = subprocess.run(
            [
                "gh", "pr", "list",
                "--repo", GH_REPO,
                "--state", "all",
                "--limit", str(GH_PR_LIST_LIMIT),
                "--json", "number",
                "--jq", ".[].number",
            ],
            capture_output=True,
            text=True,
            timeout=GH_PR_LIST_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        _log("gh binary not found on PATH; skipping PR-diff snapshot")
        return None
    except subprocess.TimeoutExpired:
        _log(f"gh pr list timed out after {GH_PR_LIST_TIMEOUT_SECONDS}s")
        return None

    if proc.returncode != 0:
        _log(
            f"gh pr list exit {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[:200]}"
        )
        return None

    nums: set[int] = set()
    for ln in proc.stdout.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            nums.add(int(ln))
        except ValueError:
            continue
    return nums


# --------------------------------------------------------------------------
# Main.
# --------------------------------------------------------------------------

def main() -> int:
    now = dt.datetime.now()
    _log(f"cron triggered at {now.isoformat(timespec='seconds')}")
    _discord_notify(
        "start",
        "claude-hackernews cron - run started",
        _compose_body(),
    )

    force = bool(os.environ.get("CRON_FORCE"))

    if force:
        _log("CRON_FORCE=1 - bypassing working-hours and pre-run sleep")
    else:
        if not _within_working_hours(now):
            msg = (
                f"skip: outside working hours "
                f"(hour={now.hour:02d}, window={WORK_HOURS_START:02d}-{WORK_HOURS_END:02d})"
            )
            _log(msg)
            _discord_notify(
                "skip",
                "claude-hackernews cron - skipped (outside working hours)",
                _compose_body(msg),
            )
            return 0

        wait = _random_wait_seconds()
        _log(f"within working hours; sleeping {wait}s before luv")
        time.sleep(wait)

    try:
        _ensure_chrome_up()
    except RuntimeError as e:
        msg = f"abort: Chrome bring-up failed: {e}"
        _log(msg)
        _discord_notify(
            "fail",
            "claude-hackernews cron - Chrome bring-up failed",
            _compose_body(msg),
        )
        return 2

    prs_before = _snapshot_pr_numbers()
    _log(
        f"PR snapshot before run on {GH_REPO}: "
        f"{'unavailable' if prs_before is None else f'{len(prs_before)} PRs'}"
    )

    rc, output = _run_luv()
    _log(f"luv finished with exit {rc}")
    print(output, flush=True)

    if rc != 0:
        _discord_notify(
            "fail",
            f"claude-hackernews cron - run failed (exit {rc})",
            _compose_body(output),
        )
        return rc

    prs_after = _snapshot_pr_numbers()
    if prs_before is None or prs_after is None:
        new_prs: list[int] = []
        _log(
            "PR snapshot incomplete (before or after query failed); "
            "treating run as noop to avoid false-positive new-PR claim"
        )
    else:
        new_prs = sorted(prs_after - prs_before)
        _log(
            f"PR snapshot after run on {GH_REPO}: {len(prs_after)} PRs "
            f"(new this run: {new_prs or 'none'})"
        )

    if new_prs:
        pr_lines = "\n".join(
            f"https://github.com/{GH_REPO}/pull/{n}" for n in new_prs
        )
        body = f"{output}\n\n--- new PRs opened this run ---\n{pr_lines}"
        title = (
            f"claude-hackernews cron - run finished OK "
            f"({len(new_prs)} new PR{'s' if len(new_prs) != 1 else ''})"
        )
        _discord_notify("ok", title, _compose_body(body))
        return 0

    _discord_notify(
        "noop",
        "claude-hackernews cron - run finished OK but no new PR was opened",
        _compose_body(output),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
