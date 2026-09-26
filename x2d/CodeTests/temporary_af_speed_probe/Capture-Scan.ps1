param([ValidateRange(3,60)][int]$Seconds=10,[DateTimeOffset]$LatestDetach=[DateTimeOffset]::MinValue)
$safetyPath = Join-Path $PSScriptRoot 'probe-safety-state.json'
if (Test-Path -LiteralPath $safetyPath) {
    $safety = Get-Content -Raw -LiteralPath $safetyPath | ConvertFrom-Json
    if ($safety.blocked) { throw ('Probe blocked after observed camera freeze: ' + $safety.reason) }
}
. (Join-Path $PSScriptRoot 'Usb.ps1')
$p=(Read-ReviewedUsb @('pidof camera-service')).Trim()
if ($p -notmatch '^\d+$') {throw 'Expected a single camera-service process'}
$statusCommand="awk '/TracerPid:/{n++;if(`$2!=0)t++} END{print n,t+0}' /proc/$p/task/*/status"
$before=(Read-ReviewedUsb @($statusCommand)).Trim()
if ($before -notmatch '^\d+ 0$') {throw 'Another tracer is attached or status is unavailable'}
$root='/tmp/afp-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$result=[ordered]@{purpose='passive-manual-focus-window';seconds=$Seconds;cameraPid=$p;deviceRoot=$root;probeWritesSpeed=$false;captureVerified=$false}
$trace='';$created=$false
$started=[Diagnostics.Stopwatch]::StartNew()
try {
    $mount=(Read-ReviewedUsb @("grep ' /tmp tmpfs ' /proc/mounts")) -join "`n"
    if ($mount -notmatch ' /tmp tmpfs ') {throw 'Temporary path is not tmpfs'}
    $r=(Read-ReviewedUsb @("umask 077; mkdir $root && echo READY")) -join "`n"
    if ($r.Trim() -ne 'READY') {throw 'Temporary directory could not be created'}
    $created=$true
    if ($LatestDetach -ne [DateTimeOffset]::MinValue -and [DateTimeOffset]::Now.AddSeconds($Seconds+3) -ge $LatestDetach) {
        throw 'Not enough time to detach before RAM restoration; no tracer started'
    }
    $start="ulimit -f 256; timeout -s INT -k 1 $Seconds strace -q -f -e trace=write -e signal=none -P /dev/lens -xx -s 128 -o $root/t -p $p >$root/e 2>&1 </dev/null & echo `$!"
    $result.timeoutPid=(Read-ReviewedUsb @($start)).Trim()
    if ($result.timeoutPid -notmatch '^\d+$') {throw 'Trace start uncertain; wait for built-in timeout, do not retry'}
    Start-Sleep -Milliseconds 250
    $during=(Read-ReviewedUsb @($statusCommand)).Trim()
    if ($during -notmatch '^\d+ (\d+)$') {throw 'Trace status unavailable'}
    $result.attachedThreads=[int]$Matches[1]
    if ($result.attachedThreads -eq 0) {throw 'No attached thread was observed'}
    Write-Output ('Passive trace active for '+$Seconds+' seconds. Only the user operates focus.')
    Start-Sleep -Seconds ($Seconds+2)
    $after=(Read-ReviewedUsb @($statusCommand)).Trim()
    $result.tracerDetached=$after -match '^\d+ 0$'
    if (-not $result.tracerDetached) {throw 'Tracer did not detach; do not start another experiment'}
    $result.diagnostics=(Read-ReviewedUsb @("head -c 4096 $root/e; true")) -join "`n"
    $sizeText=(Read-ReviewedUsb @("wc -c <$root/t")).Trim()
    if ($sizeText -notmatch '^\d+$') {throw 'Trace length unavailable'}
    $size=[int]$sizeText
    if ($size -ge 131072) {throw 'Trace too large; measurement is incomplete'}
    for ($offset=0;$offset -lt $size;$offset+=4096) {
        $trace+=(Read-ReviewedUsb @("dd if=$root/t bs=1 skip=$offset count=4096 2>/dev/null")) -join ''
    }
    if ([Text.Encoding]::ASCII.GetByteCount($trace) -ne $size) {throw 'Trace readback length mismatch'}
    $result.captureVerified=[string]::IsNullOrWhiteSpace($result.diagnostics)
} finally {
    # Hardware timeout owns detachment, including loss of the USB connection.
    if ($created) {
        $remaining=[Math]::Max(0,$Seconds+3-[int]$started.Elapsed.TotalSeconds)
        if ($remaining) {Start-Sleep -Seconds $remaining}
        $check=(Read-ReviewedUsb @($statusCommand)).Trim()
        if ($check -notmatch '^\d+ 0$') {
            $result.cleanup='Deferred until automatic trace timeout; do not remove active trace files'
        } else {
            $result.cleanup=(Read-ReviewedUsb @("rm -f $root/t $root/e; rmdir $root; test ! -e $root && echo CLEAN")) -join "`n"
        }
    }
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'last-trace.txt'),$trace,[Text.UTF8Encoding]::new($false))
    $result | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'last-capture.json')
}
$result | ConvertTo-Json -Depth 4
if ($result.captureVerified) {
    & py -3 -B (Join-Path $PSScriptRoot 'probe_protocol.py') (Join-Path $PSScriptRoot 'last-trace.txt')
    if ($LASTEXITCODE -ne 0) {throw 'Trace decoder failed'}
} else {throw 'Capture not verified; no measured maximum is valid'}
