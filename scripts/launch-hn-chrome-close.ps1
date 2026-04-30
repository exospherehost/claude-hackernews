# Stops the Chrome instance launched by launch-hn-chrome.ps1 (i.e. any
# chrome.exe whose CommandLine references the dedicated hn-profile
# user-data-dir). Idempotent: exits 0 with a log line if nothing matches.
#
# Used at end-of-run by the agent (per INSTRUCTIONS.md "End-of-run cleanup")
# so the operating Chrome session does not stay logged in 24/7 between
# cron-driven runs. Symmetric counterpart of launch-hn-chrome.ps1 and
# matches its $ProfileDir exactly so the predicate is the same one the
# launcher uses to detect "already running".

$ErrorActionPreference = 'Stop'

$ProfileDir = "$env:USERPROFILE\hn-profile"

$matches = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($ProfileDir) }

if (-not $matches) {
    Write-Host "No chrome.exe with hn profile running ($ProfileDir). Nothing to do."
    exit 0
}

$count = ($matches | Measure-Object).Count
Write-Host "Stopping $count chrome.exe process(es) with profile $ProfileDir ..."
foreach ($p in $matches) {
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-Host "  killed PID $($p.ProcessId)"
    } catch {
        Write-Host "  PID $($p.ProcessId) already gone or could not be stopped: $_"
    }
}
Write-Host "Done."
