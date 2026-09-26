. (Join-Path $PSScriptRoot 'Usb.ps1')
$commands = @(
 'uname -r; command -v timeout; timeout --help 2>&1 | head -18; true',
 'cat /proc/mounts | grep -E " /tmp | /dev | /system "; p=$(pidof camera-service); grep -E "State:|TracerPid:|Threads:" /proc/$p/status',
 'p=$(pidof camera-service); cat /proc/$p/attr/current; ls -Z /system/bin/strace; command -v dd; command -v cmp; command -v sha256sum',
 'p=$(pidof camera-service); for t in /proc/$p/task/*/comm; do cat $t; done | grep -iE "lens|hbmount|motor"; true'
)
$r=Read-ReviewedUsb $commands
for ($i=0;$i -lt $r.Length;$i++){Write-Output ('CHECK '+$i);Write-Output $r[$i]}
