<#
.SYNOPSIS
    Sample host resources every few seconds so the next Postgres crash has a before, not just an
    after.

.DESCRIPTION
    Five crashes (2026-08-13, 08-27 x2, 08-28, 09-03) share one signature: a backend exits with
    code 2 — SIGQUIT, reproduced against a scratch postgres — having never logged a line, not even
    `connection received`. Around it the container healthcheck, which runs every 5 seconds, widens:
    11s, then 27s, then 16s, then the crash. Nothing appears in the Windows System log, the WSL
    kernel log, or Docker Desktop's own log. A suspend and resume leaves no error, which is why
    four post-mortems found nothing.

    So this watches from the host while the stack works, and writes one CSV row per tick.

    **The load-bearing column is `sleep_overshoot_s`, not any resource number.** The sampler sleeps
    for exactly the interval and records how much longer than that it actually took to wake. On a
    healthy machine that is 0.0. That splits the hypothesis in two, and the split is the point:

      * overshoot stays ~0 while the container healthcheck widens -> the stall is inside the WSL VM
        or Docker, and the Windows side never noticed;
      * overshoot widens with it -> the whole machine stalls, and the VM is a victim rather than a
        cause.

    Those two findings point at completely different culprits, and no amount of reading postgres
    logs afterwards can tell them apart. Everything else here — CPU, available memory, disk queue,
    vmmem, Ollama, VRAM — is there to say *why*, once that first question is answered.

    Cheap on purpose: one `Get-Counter` call, two process lookups, one `nvidia-smi`. It is meant to
    run for hours beside an extraction without being part of the problem it is measuring.

    Delete this once the cause is known. It is a diagnostic for one open incident, not a fixture.

.PARAMETER IntervalSeconds
    Requested seconds between samples. Default 5, matching the db healthcheck it is compared against.

.PARAMETER OutPath
    CSV to append to. Defaults to scripts/host-samples.csv.

.EXAMPLE
    Start-Process powershell -ArgumentList '-NoProfile','-WindowStyle','Hidden','-File','C:\RegOps\RegOps\scripts\host-sampler.ps1'
#>
[CmdletBinding()]
param(
    [int]$IntervalSeconds = 5,
    [string]$OutPath
)

$ErrorActionPreference = 'Continue'
if (-not $OutPath) { $OutPath = Join-Path $PSScriptRoot 'host-samples.csv' }

$enc = New-Object System.Text.UTF8Encoding($false)
if (-not (Test-Path $OutPath)) {
    $header = 'ts,sleep_overshoot_s,cycle_s,cpu_pct,avail_mb,disk_queue,disk_idle_pct,vmmem_cpu_s,vmmem_ws_mb,ollama_cpu_s,ollama_ws_mb,gpu_util_pct,gpu_mem_mb'
    [System.IO.File]::AppendAllText($OutPath, $header + [Environment]::NewLine, $enc)
}

$counters = @(
    '\Processor(_Total)\% Processor Time',
    '\Memory\Available MBytes',
    '\PhysicalDisk(_Total)\Current Disk Queue Length',
    '\PhysicalDisk(_Total)\% Idle Time'
)

$last = Get-Date
while ($true) {
    # Timed around the sleep alone. The first version timed the whole loop, which folded this
    # script's own cost — `Get-Counter` and an `nvidia-smi` spawn, together a second or three — into
    # the number meant to detect starvation, and read 8.8s on an idle machine. Measuring only the
    # sleep means a healthy sample is 5.0 and *any* excess is the scheduler failing to wake us.
    $t0 = Get-Date
    Start-Sleep -Seconds $IntervalSeconds
    $now = Get-Date
    $overshoot = [math]::Round(($now - $t0).TotalSeconds - $IntervalSeconds, 2)
    # Kept beside it: total cycle time, so the sampler's own cost stays visible rather than
    # hidden. If this climbs while the overshoot does not, the machine is slow at work but still
    # scheduling us on time — a different finding again.
    $cycle = [math]::Round(($now - $last).TotalSeconds, 2)
    $last = $now

    $cpu = $mem = $dq = $idle = ''
    try {
        $s = (Get-Counter -Counter $counters -ErrorAction Stop).CounterSamples
        $cpu  = [math]::Round($s[0].CookedValue, 1)
        $mem  = [math]::Round($s[1].CookedValue, 0)
        $dq   = [math]::Round($s[2].CookedValue, 2)
        $idle = [math]::Round($s[3].CookedValue, 1)
    } catch { }

    $vmCpu = $vmWs = ''
    $vm = Get-Process -Name 'vmmem*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($vm) { $vmCpu = [math]::Round($vm.CPU, 1); $vmWs = [int]($vm.WorkingSet64 / 1MB) }

    $olCpu = $olWs = ''
    $ol = Get-Process -Name 'ollama' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ol) { $olCpu = [math]::Round($ol.CPU, 1); $olWs = [int]($ol.WorkingSet64 / 1MB) }

    $gpuUtil = $gpuMem = ''
    try {
        $g = (nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits) -split ','
        $gpuUtil = $g[0].Trim(); $gpuMem = $g[1].Trim()
    } catch { }

    $row = '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12}' -f `
        $now.ToString('yyyy-MM-dd HH:mm:ss'), $overshoot, $cycle, $cpu, $mem, $dq, $idle,
        $vmCpu, $vmWs, $olCpu, $olWs, $gpuUtil, $gpuMem
    # Append per row rather than buffering: the interesting sample is the one written immediately
    # before the machine stopped answering, and a buffer loses exactly that one.
    [System.IO.File]::AppendAllText($OutPath, $row + [Environment]::NewLine, $enc)
}
