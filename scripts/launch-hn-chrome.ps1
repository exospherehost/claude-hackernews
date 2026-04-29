# Launches Chrome with a dedicated profile for the Hacker News account being
# operated and exposes the Chrome DevTools Protocol on port 9334 so
# browser-use (running in WSL) can attach to it.
#
# Port 9334 is used instead of the Chrome default 9222 because Lenovo Vantage's
# BatteryWidget WebView2 binds 127.0.0.1:9222 at boot, which prevents Chrome
# from binding 0.0.0.0:9222 on the IPv4 interface that WSL reaches. 9333 is
# already used by the sibling claude-reddit harness; 9334 lets both run
# concurrently against separate profiles.
#
# First run: log in to news.ycombinator.com manually as the operating account
# (or sign up — HN signup is form-only). Cookies persist in the user-data-dir,
# so subsequent runs reuse the session.

$ErrorActionPreference = 'Stop'

$Port        = 9334
$ProfileDir  = "$env:USERPROFILE\hn-profile"
$StartUrl    = 'https://news.ycombinator.com'

$ChromeCandidates = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
)

$Chrome = $ChromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Chrome) {
    Write-Error "chrome.exe not found in any standard location. Install Chrome or edit this script."
    exit 1
}

if (-not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
}

# Refuse to launch a second instance -- Chrome can't share a user-data-dir
# across processes, and a stale CDP listener will silently shadow the new one.
$existing = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($ProfileDir) }
if ($existing) {
    Write-Host "Chrome with this profile is already running (PID $($existing[0].ProcessId))."
    Write-Host "CDP should already be at http://0.0.0.0:$Port -- run scripts/verify-cdp.sh from WSL."
    exit 0
}

$ChromeArgs = @(
    "--remote-debugging-port=$Port",
    "--remote-debugging-address=0.0.0.0",
    # Required for non-browser WebSocket clients (e.g., python websocket-client
    # used by ad-hoc CDP helpers) to attach to CDP. Without this, Chrome rejects
    # WS handshakes that include any Origin header with 403 "Rejected an
    # incoming WebSocket connection from <origin>".
    '--remote-allow-origins=*',
    "--user-data-dir=$ProfileDir",
    '--no-first-run',
    '--no-default-browser-check',
    '--new-window',
    # Force a sensible desktop viewport. Without these, Chrome can come up
    # at the previous (possibly tiny) size, which leaves window.innerHeight
    # at ~2px and breaks every CDP click/scroll because elements report as
    # off-screen. --start-maximized handles single-monitor cleanly; the
    # explicit window-size is the fallback if maximize is denied.
    '--start-maximized',
    '--window-size=1400,900',
    '--window-position=0,0',
    $StartUrl
)

Write-Host "Launching Chrome:"
Write-Host "  binary  : $Chrome"
Write-Host "  profile : $ProfileDir"
Write-Host "  CDP     : http://0.0.0.0:$Port (reachable from WSL via the Windows host IP)"
Write-Host ""

$proc = Start-Process -FilePath $Chrome -ArgumentList $ChromeArgs -PassThru
Write-Host "Chrome started, PID $($proc.Id). Leave this window open until you're done with HN work."
