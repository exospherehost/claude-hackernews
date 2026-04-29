#!/usr/bin/env bash
# Verifies that Windows Chrome's CDP endpoint is reachable from inside WSL.
# Defaults to 127.0.0.1 because, on this WSL, `localhost` resolves to ::1
# (IPv6) only and Chrome's --remote-debugging-port listens on IPv4 only —
# matches what `.mcp.json` and the browser-use config use. Override via
# CDP_HOST env var if you ever need to probe a non-mirrored setup,
# e.g. CDP_HOST=$(ip route show default | awk '/default/ {print $3}').
set -euo pipefail

CDP_HOST="${CDP_HOST:-127.0.0.1}"
CDP_PORT="${CDP_PORT:-9334}"
URL="http://${CDP_HOST}:${CDP_PORT}/json/version"

echo "Probing $URL ..."
if response="$(curl -fsS --max-time 5 "$URL")"; then
    echo "$response"
    echo
    echo "OK -- Chrome CDP reachable at ${CDP_HOST}:${CDP_PORT}."
else
    echo
    echo "FAILED. Check, in order:"
    echo "  1. Is Windows Chrome running with the launcher? (scripts/win-chrome.sh)"
    echo "  2. Is WSL mirrored networking active? Confirm with: wsl.exe --version"
    echo "     and that %USERPROFILE%\\.wslconfig has [wsl2] networkingMode=mirrored."
    echo "     If you just added it, run 'wsl --shutdown' from Windows and reopen."
    echo "  3. Is Windows Defender Firewall blocking inbound TCP $CDP_PORT to chrome.exe?"
    exit 1
fi
