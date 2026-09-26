$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$source = (Get-Content -Raw -Encoding UTF8 (Join-Path $repo 'native/WinUsbReadOnly.cs')).Replace('namespace HasselbladDebug','namespace X2DTemporaryUi').Replace('WinUsbReadOnly','TemporaryUiUsb')
$methods = Get-Content -Raw -Encoding UTF8 (Join-Path $repo 'x2d/CodeTests/temporary_wifi_button/ShellTransport.inc.cs')
$source = $source.Replace('        public void Dispose() {', $methods + '        public void Dispose() {')
Add-Type -TypeDefinition $source
[X2DTemporaryUi.TemporaryUiUsb]::SelfTestShell()
$commands = @(
 'pidof camera-service; pidof camera-gui; id -Z',
 'p=$(pidof camera-service); cat /proc/$p/maps | grep -E "libaaa.so|librcam.so"',
 'p=$(pidof camera-service); ls -l /proc/$p/fd | grep /dev/lens; /system/bin/strace -V 2>&1; true',
 '/system/bin/strace -h 2>&1 | head -65; true'
)
$results = [X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch($commands)
for ($i=0; $i -lt $results.Length; $i++) { Write-Output ('CHECK ' + $i); Write-Output $results[$i] }
