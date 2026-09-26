param([switch]$UserPresent,[switch]$WithoutProbe,[ValidateRange(15,60)][int]$Seconds=20)
$safetyPath = Join-Path $PSScriptRoot 'probe-safety-state.json'
if (Test-Path -LiteralPath $safetyPath) {
    $safety = Get-Content -Raw -LiteralPath $safetyPath | ConvertFrom-Json
    if ($safety.blocked -and -not $WithoutProbe) { throw ('Tracing experiment blocked; explicit WithoutProbe is required: ' + $safety.reason) }
}
if (-not $UserPresent) {throw 'This temporary experiment requires the user to be present to operate focus. Use Prepare-Experiment.ps1 for read-only preparation.'}
. (Join-Path $PSScriptRoot 'Usb.ps1')
& (Join-Path $PSScriptRoot 'Prepare-Experiment.ps1') -Seconds $Seconds
$planPath=Join-Path $PSScriptRoot 'prepared-plan.json'
$plan=Get-Content -Raw -Encoding UTF8 $planPath | ConvertFrom-Json
$d=$plan.deviceRoot
if ($d -notmatch '^/tmp/afw-[a-f0-9]{8}$') {throw 'Invalid owned temporary directory'}
function Upload-ProbeFile([string]$LocalName,[string]$RemoteName) {
    if ($RemoteName -notmatch '^[a-z]+$') {throw 'Invalid fixed artifact name'}
    $bytes=[IO.File]::ReadAllBytes((Join-Path $PSScriptRoot $LocalName))
    $encoded=[Convert]::ToBase64String($bytes)
    $commands=[Collections.Generic.List[string]]::new()
    $commands.Add(": >$d/$RemoteName.b64")
    for($i=0;$i -lt $encoded.Length;$i+=148) {
        $part=$encoded.Substring($i,[Math]::Min(148,$encoded.Length-$i))
        $commands.Add("printf '%s' '$part' >>$d/$RemoteName.b64")
    }
    for($i=0;$i -lt $commands.Count;$i+=90) {
        $count=[Math]::Min(90,$commands.Count-$i)
        $null=Read-ReviewedUsb ($commands.GetRange($i,$count).ToArray())
    }
    $r=(Read-ReviewedUsb @("base64 -d $d/$RemoteName.b64 >$d/$RemoteName && sha256sum $d/$RemoteName")) -join "`n"
    $expected=(Get-FileHash -Algorithm SHA256 (Join-Path $PSScriptRoot $LocalName)).Hash.ToLowerInvariant()
    if (($r.Trim() -split '\s+')[0] -ne $expected) {throw 'Uploaded artifact hash mismatch'}
    $null=Read-ReviewedUsb @("rm -f $d/$RemoteName.b64")
}
$ready=(Read-ReviewedUsb @("umask 077; mkdir $d && echo READY")).Trim()
if ($ready -ne 'READY') {throw 'Cannot create owned temporary workspace'}
$dispatched=$false;$restored=$false;$timer=[Diagnostics.Stopwatch]::new()
try {
    Upload-ProbeFile 'function-original.bin' 'original'
    Upload-ProbeFile 'function-candidate.bin' 'candidate'
    Upload-ProbeFile 'prepared-window.sh' 'window'
    Upload-ProbeFile 'prepared-restore.sh' 'restore'
    $check=(Read-ReviewedUsb @("sh -n $d/window && sh -n $d/restore && echo SYNTAX_OK")).Trim()
    if ($check -ne 'SYNTAX_OK') {throw 'Device shell rejected the prepared transaction'}
    # Set before dispatch so uncertain USB delivery cannot cause a retry.
    $dispatched=$true;$timer.Start();$detachDeadline=[DateTimeOffset]::Now.AddSeconds($Seconds)
    $plan.state='DISPATCHED_OR_UNCERTAIN'
    $plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $planPath
    $windowPid=(Read-ReviewedUsb @("sh $d/window >$d/status 2>&1 </dev/null & echo `$!")).Trim()
    if ($windowPid -notmatch '^\d+$') {throw 'Start result uncertain; no retry; the device-local deadline owns restoration'}
    $plan | Add-Member -NotePropertyName windowPid -NotePropertyValue $windowPid -Force
    $plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $planPath
    $active=$false
    for($n=0;$n -lt 10;$n++) {
        $status=(Read-ReviewedUsb @("head -c 4096 $d/status; true")) -join "`n"
        if ($status -match '(?m)^ACTIVE\r?$') {$active=$true;break}
        if ($status -match 'EXIT:') {throw ('Device preflight/transaction stopped: '+$status)}
        Start-Sleep -Milliseconds 150
    }
    if (-not $active) {throw 'Activation was not confirmed; do not focus; wait for automatic restoration'}
    $plan.state='TEMPORARILY_ACTIVE';$plan.deviceCodeWritten=$true
    $plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $planPath
    $spec=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'candidate.json') | ConvertFrom-Json
    Write-Output ('Temporary type 0 x'+$spec.multiplier+' window is active. Only the user may half-press focus; do not change lenses. Automatic restoration is scheduled.')
    if ($WithoutProbe) {
        Write-Output 'No tracer attached. No measured command-speed maximum will be reported.'
    } else {
        $traceSeconds=[Math]::Min($Seconds-8,[int][Math]::Floor($Seconds-$timer.Elapsed.TotalSeconds-5))
        if ($traceSeconds -lt 3) {throw 'Too little time remains to start a trace; waiting for original-state restoration'}
        & (Join-Path $PSScriptRoot 'Capture-Scan.ps1') -Seconds $traceSeconds -LatestDetach $detachDeadline
    }
} finally {
    if ($dispatched) {
        $remaining=[Math]::Max(0,$Seconds+5-[int]$timer.Elapsed.TotalSeconds)
        if ($remaining) {Start-Sleep -Seconds $remaining}
        $status=(Read-ReviewedUsb @("head -c 4096 $d/status; true")) -join "`n"
        $status | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'last-window-status.txt')
        if ($status -match '(?m)^RESTORED\r?$' -or ($status -notmatch '(?m)^ACTIVE\r?$' -and $status -match 'EXIT:1[0123]')) {
            . (Join-Path $PSScriptRoot 'Snapshot.ps1')
            $check=Get-AfSnapshot
            $restored=$check.functionHash -eq $plan.original
            if ($restored) {
                $plan.state='ORIGINAL_VERIFIED'
                $plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $planPath
            }
        }
        if (-not $restored) {throw 'Original function not verified. Retained exact recovery files and plan; do not repeat installation. Inspect last-window-status.txt and use Restore-Experiment.ps1.'}
    }
    if (-not $dispatched -or $restored) {
        $files='original candidate window restore status recovery owner original.b64 candidate.b64 window.b64 restore.b64'.Split(' ')
        foreach($f in $files) {$null=Read-ReviewedUsb @("rm -f $d/$f")}
        $null=Read-ReviewedUsb @("rmdir $d")
    }
}
Write-Output 'Original RAM function verified and temporary files removed. No system or lens firmware was written.'
