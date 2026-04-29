#!/usr/bin/env bash
# WSL wrapper around launch-hn-chrome.ps1: invokes the PowerShell launcher
# on the Windows side using powershell.exe (available in WSL2 by default).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WIN_PATH="$(wslpath -w "$HERE/launch-hn-chrome.ps1")"

exec powershell.exe -ExecutionPolicy Bypass -NoProfile -File "$WIN_PATH"
