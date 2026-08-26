<#
.SYNOPSIS
    One daily eCFR-versus-Federal-Register lag observation, appended to the log.

.DESCRIPTION
    Wraps `fda_lag.cli probe` (ADR-0018 open question 1) so the fortnight of daily runs cannot be
    spoiled by the three ways doing it by hand goes wrong:

      1. `>` instead of `>>` — one keystroke destroys the whole series. There is no redirect here.
      2. A polluted log — when the stack is down, `docker compose exec` writes its own error to
         *stdout* ("OCI runtime exec failed: ..."), which a blind append would file as an
         observation. This validates the output as one JSON object before touching the log.
      3. A BOM — PowerShell's `>>` writes EF BB BF when it creates the target, which costs the
         first observation. This writes UTF-8 without a BOM and with LF endings.
      4. A day filed under the wrong date — the container runs UTC and the operator may not. At
         UTC+9 every run before 09:00 local falls on the previous UTC date, which lands on a day
         already in the log; the no-op guard below would then decline it and the morning would be
         lost. This passes the host's own date with `--observed-on`.

    Running twice in one day is a no-op, not an error: `days_observed` counts distinct days, so a
    duplicate would add bytes and no information. Use -Force to record one anyway.

.PARAMETER LogPath
    Observation log. Defaults to docs/design/fda-lag-observations.jsonl in this repository.

.PARAMETER Force
    Append even when the returned observation date is already in the log.

.EXAMPLE
    .\scripts\fda-lag-probe.ps1

.EXAMPLE
    .\scripts\fda-lag-probe.ps1 -Verbose

.NOTES
    Exit codes: 0 appended or already present · 1 stack not running · 2 probe failed or output
    was not one JSON object · 3 could not write the log.
#>
[CmdletBinding()]
param(
    [string] $LogPath,
    [switch] $Force
)

Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $LogPath) {
    $LogPath = Join-Path $RepoRoot 'docs\design\fda-lag-observations.jsonl'
}

function Write-Step($Message) { Write-Host "  $Message" }

# Expected failures are reported, not thrown. `Write-Error` wraps the message in a PowerShell
# exception trace, which buries the one line that says what to do - and this is read on ten
# consecutive mornings, so legibility is the feature.
function Stop-WithReason($Message, $Code) {
    Write-Host ""
    Write-Host "  $Message" -ForegroundColor Red
    Write-Host "  The log was not touched." -ForegroundColor DarkGray
    # No Pop-Location here: `exit` runs the caller's `finally`, which pops. Doing it twice would
    # unwind a location the caller pushed.
    exit $Code
}

Push-Location $RepoRoot
try {
    # --- 1. the stack has to be up, and saying so plainly beats a docker stack trace -------------
    Write-Verbose "Checking that the regulation service is running"
    $running = docker compose ps --services --status running
    if ($LASTEXITCODE -ne 0) {
        Stop-WithReason "docker compose is not answering. Is Docker Desktop running?" 1
    }
    if ($running -notcontains 'regulation') {
        Stop-WithReason "The 'regulation' service is not running. Start the stack first:`n`n      docker compose --profile app up -d" 1
    }

    # --- 2. probe. stdout is the data; stderr carries progress and goes to the console ----------
    Write-Step "Probing eCFR and the Federal Register..."
    # The date is the host's, not the container's: `days_observed` counts distinct `observed_on`
    # values, so the day has to be the one the person running this is having. `observed_at` inside
    # the observation stays the true UTC instant of the fetch, and the two may differ by a day.
    $localDay = Get-Date -Format 'yyyy-MM-dd'
    Write-Verbose "Filing this observation under the host's local date $localDay"
    $output = docker compose exec -T -w /scripts regulation python -m fda_lag.cli probe --observed-on $localDay
    if ($LASTEXITCODE -ne 0) {
        Stop-WithReason "probe exited $LASTEXITCODE." 2
    }

    # --- 3. validate before appending. This is the whole point of the script --------------------
    $lines = @($output | Where-Object { $_ -and $_.Trim() })
    if ($lines.Count -ne 1) {
        $output | ForEach-Object { Write-Host "    | $_" -ForegroundColor DarkGray }
        Stop-WithReason "expected exactly one line of output, got $($lines.Count)." 2
    }

    $line = $lines[0].Trim([char]0xFEFF, ' ', "`t")
    try {
        $observation = $line | ConvertFrom-Json
    } catch {
        Write-Host "    | $($line.Substring(0, [Math]::Min(200, $line.Length)))" -ForegroundColor DarkGray
        Stop-WithReason "output is not JSON, so it is not an observation." 2
    }
    if ($observation.PSObject.Properties.Name -notcontains 'observed_on') {
        Stop-WithReason "JSON parsed but carries no observed_on." 2
    }

    $observedOn = $observation.observed_on
    Write-Step "observed_on=$observedOn  blind_spot=$($observation.blind_spot_days)d  freshness=$($observation.freshness_lag_days)d"

    # --- 4. a day already recorded is a no-op, not a failure ------------------------------------
    $recorded = @()
    if (Test-Path $LogPath) {
        $recorded = @(Get-Content $LogPath | Where-Object { $_.Trim() } | ForEach-Object {
            try { ($_.Trim([char]0xFEFF, ' ')) | ConvertFrom-Json | Select-Object -ExpandProperty observed_on } catch { }
        })
    }
    if ($recorded -contains $observedOn -and -not $Force) {
        Write-Host ""
        Write-Host "  $observedOn is already in the log - nothing appended." -ForegroundColor Yellow
        Write-Host "  Running twice in one day adds no information (days_observed counts distinct days)."
        Write-Host "  Use -Force if you really want a second row."
        $days = @($recorded | Sort-Object -Unique).Count
        Write-Host ""
        Write-Host "  $days of 10 days collected."
        exit 0
    }

    # --- 5. append. UTF-8 without a BOM, LF, and never overwrite --------------------------------
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        if (Test-Path $LogPath) {
            # A previous run cut short could leave the file without a trailing newline; appending
            # then would fuse two observations into one unparseable line.
            $bytes = [System.IO.File]::ReadAllBytes($LogPath)
            if ($bytes.Length -gt 0 -and $bytes[-1] -ne 0x0A) {
                [System.IO.File]::AppendAllText($LogPath, "`n", $utf8NoBom)
            }
        }
        [System.IO.File]::AppendAllText($LogPath, $line + "`n", $utf8NoBom)
    } catch {
        Stop-WithReason "could not write ${LogPath}: $_" 3
    }

    $days = @((@($recorded) + $observedOn) | Sort-Object -Unique).Count
    Write-Host ""
    Write-Host "  Appended to $(Resolve-Path -Relative $LogPath)" -ForegroundColor Green
    Write-Host "  $days of 10 days collected." -NoNewline
    if ($days -ge 10) {
        Write-Host " The sample is large enough - run the report:" -ForegroundColor Green
        Write-Host ""
        Write-Host "    Get-Content $(Resolve-Path -Relative $LogPath) | docker compose exec -T -w /scripts regulation python -m fda_lag.cli report"
    } else {
        Write-Host " $(10 - $days) more, on $(10 - $days) more days."
    }
    exit 0
} finally {
    Pop-Location
}
