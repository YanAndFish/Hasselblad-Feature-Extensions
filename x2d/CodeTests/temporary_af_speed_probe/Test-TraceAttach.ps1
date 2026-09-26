. (Join-Path $PSScriptRoot 'Usb.ps1')
# One second only, factory tracer, lens fd only; no focus or capture command.
# Device path must be tmpfs and is unique to this probe.
$path = '/tmp/hbl-af-trace-' + [Guid]::NewGuid().ToString('N').Substring(0,12)
$p = (Read-ReviewedUsb @('pidof camera-service')).Trim()
if ($p -notmatch '^\d+$') { throw 'Expected one camera-service PID.' }
$cmd = "ulimit -f 128; timeout -s INT 1 strace -q -f -e trace=write,writev,ioctl -e signal=none -P /dev/lens -xx -s 128 -o $path -p $p 2>&1; echo TRACE_RC:`$?"
$result = [ordered]@{ purpose='attach-only-no-focus'; devicePid=$p; traceCommand='factory-strace-lens-only-one-second' }
try {
    $result.attach = (Read-ReviewedUsb @($cmd)) -join "`n"
    $result.trace = (Read-ReviewedUsb @("head -c 4096 $path; true")) -join "`n"
} finally {
    # Delete only our exact tmpfs path. Do not stop the camera service.
    $result.cleanup = (Read-ReviewedUsb @("rm -f $path; test ! -e $path && echo CLEAN", "grep -E 'State:|TracerPid:' /proc/$p/status")) -join "`n"
    $result | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'trace-attach-result.json')
}
$result | ConvertTo-Json -Depth 4
