<#
.SYNOPSIS
    Dispatch one IR extraction for a (document version, domain), unattended.

.DESCRIPTION
    Written for scheduled runs. Extraction over a large corpus takes hours, so it gets started at
    an hour nobody wants to sit through — and an unattended start has two ways to quietly not
    happen that an interactive one does not:

      * the stack is down, because the last thing anyone did was shut it down; and
      * the dispatch succeeds while nothing picks it up, because the worker has not finished booting.

    So this brings the stack up, waits for the database and the worker, dispatches, and then
    confirms a run row actually opened. Every step is appended to a log with a timestamp, because
    the person reading it will be reading it the next morning.

    **The domain is required and not optional on purpose.** `extract_document_version` with no
    domain extracts once per claiming cell, and 21 U.S.C. chapter 9 is claimed by both `fda_samd`
    and `fda_cosmetic` — a bare dispatch is two full passes over 12,179 clauses, about fourteen
    hours rather than seven. Naming the domain is what makes the runtime the one you predicted.

    **No `2>&1` on a native command anywhere below, and `$ErrorActionPreference` stays `Continue`.**
    Windows PowerShell 5.1 wraps each stderr line from an exe in an ErrorRecord, so with `Stop` in
    force a redirect turns `docker compose up`'s ordinary progress output — which it writes to
    stderr — into a NativeCommandError that aborts the script. Found by smoke-testing this file
    rather than at the scheduled hour, which is the only reason it is worth saying twice. Failure
    is detected with `$LASTEXITCODE` instead.

.PARAMETER VersionId
    document_versions.id — the version to extract.

.PARAMETER Domain
    samd | cosmetic. Required; see above.

.PARAMETER LogPath
    Where to append. Defaults to scripts/extract-dispatch.log beside this script.

.EXAMPLE
    .\scripts\extract-dispatch.ps1 -VersionId 5f502d96-... -Domain samd
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$VersionId,
    [Parameter(Mandatory = $true)][ValidateSet('samd', 'cosmetic')][string]$Domain,
    [string]$LogPath
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $LogPath) { $LogPath = Join-Path $PSScriptRoot 'extract-dispatch.log' }

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Output $line
    # UTF-8 without a BOM: the log is read by eye and by grep, and a BOM costs the first line of a
    # file that PowerShell created rather than appended to.
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::AppendAllText($LogPath, $line + [Environment]::NewLine, $enc)
}

Set-Location $repo
Write-Log "=== dispatch requested: version=$VersionId domain=$Domain ==="

# --- the stack ------------------------------------------------------------------------------
# `up -d` is idempotent: it starts what is stopped and leaves what is running alone. Run it
# unconditionally rather than testing first, so a half-up stack converges too.
Write-Log "bringing the stack up (idempotent)"
docker compose --profile app up -d | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "ABORT: compose up failed with exit $LASTEXITCODE - is Docker Desktop running?"
    exit 1
}

# --- wait for the two things the dispatch actually needs -------------------------------------
# The database, because the task's first act is to read the version; and the worker, because a
# task dispatched into an empty queue sits there looking exactly like one that was never sent.
$deadline = (Get-Date).AddMinutes(5)
while ($true) {
    $dbState = docker compose ps db --format '{{.Status}}' | Select-Object -First 1
    $workerState = docker compose ps regulation-worker --format '{{.State}}' | Select-Object -First 1
    if ("$dbState" -match 'healthy' -and "$workerState" -match 'running') {
        Write-Log "stack ready - db: $dbState, worker: $workerState"
        break
    }
    if ((Get-Date) -gt $deadline) {
        Write-Log "ABORT: stack not ready within 5 minutes - db: '$dbState', worker: '$workerState'"
        exit 1
    }
    Start-Sleep -Seconds 5
}

# --- dispatch -------------------------------------------------------------------------------
# By task name, into the regulation queue - the same path the API takes. Note this leaves no
# `extraction.triggered` audit row: that one is written by the endpoint, which has a principal to
# attribute it to, and a scheduled task has none.
#
# One line, not a here-string: a multi-line argument to `python -c` survives PowerShell's native
# argument handling only by luck, and this runs unattended.
$py = "from app.celery_app import celery_app; print(celery_app.send_task('regulation.extract_document_version', args=['$VersionId', '$Domain'], queue='regulation').id)"
$taskId = docker compose exec -T regulation-worker python -c $py | Select-Object -Last 1
if ($LASTEXITCODE -ne 0 -or -not $taskId) {
    Write-Log "ABORT: dispatch failed with exit $LASTEXITCODE"
    exit 1
}
Write-Log "dispatched: task_id=$("$taskId".Trim())"

# --- confirm a run actually opened ------------------------------------------------------------
# A task id proves the message was queued, not that the work started. The run row is the proof,
# and it also catches the case worth catching: the concurrency guard refusing because a live run
# already owns this (version, domain), which is a correct outcome that must not read as a start.
$sql = "select id || '|' || status || '|' || clauses_seen || '|' || rule_version || '|' || prompt_version from extraction_runs where document_version_id = '$VersionId' and domain_profile = '$Domain' order by started_at desc limit 1;"
$opened = $false
$deadline = (Get-Date).AddMinutes(3)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 15
    $row = docker compose exec -T db psql -U regops -d regops -At -c $sql | Select-Object -First 1
    if ($row) {
        Write-Log "run row: $("$row".Trim())"
        if ("$row" -match '\|running\|') { $opened = $true; break }
    }
}
if ($opened) {
    Write-Log "OK - extraction is running. Watch it with: docker compose logs -f regulation-worker"
} else {
    Write-Log "WARNING: no running run appeared within 3 minutes. Either the guard refused it (a live"
    Write-Log "         run already owns this version and domain) or the worker never picked it up."
    Write-Log "         Check: docker compose logs regulation-worker --tail=50"
}
Write-Log "=== done ==="
