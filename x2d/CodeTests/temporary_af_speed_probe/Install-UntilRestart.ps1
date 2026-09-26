param([switch]$UserPresent)
$ErrorActionPreference='Stop'
if (-not $UserPresent) {throw 'The user must be present for initial installation'}
. (Join-Path $PSScriptRoot 'Usb.ps1')
& (Join-Path $PSScriptRoot 'Prepare-Experiment.ps1') -UntilRestart
$planPath=Join-Path $PSScriptRoot 'prepared-plan.json'
$plan=Get-Content -Raw $planPath | ConvertFrom-Json
$d=$plan.deviceRoot
if ($d -notmatch '^/tmp/afw-[a-f0-9]{8}$') {throw 'Invalid owned temporary directory'}
function Upload-RamFile([string]$LocalName,[string]$RemoteName) {
    if ($RemoteName -notmatch '^[a-z]+$') {throw 'Invalid artifact name'}
    $path=Join-Path $PSScriptRoot $LocalName
    $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
    $commands=[Collections.Generic.List[string]]::new()
    $commands.Add(": >$d/$RemoteName.b64")
    for($i=0;$i -lt $encoded.Length;$i+=148) {
        $part=$encoded.Substring($i,[Math]::Min(148,$encoded.Length-$i))
        $commands.Add("printf '%s' '$part' >>$d/$RemoteName.b64")
    }
    for($i=0;$i -lt $commands.Count;$i+=90) {
        $null=Read-ReviewedUsb ($commands.GetRange($i,[Math]::Min(90,$commands.Count-$i)).ToArray())
    }
    $r=(Read-ReviewedUsb @("base64 -d $d/$RemoteName.b64 >$d/$RemoteName && sha256sum $d/$RemoteName")).Trim()
    if (($r -split '\s+')[0] -ne (Get-FileHash -Algorithm SHA256 $path).Hash.ToLowerInvariant()) {throw 'RAM upload hash mismatch'}
    $null=Read-ReviewedUsb @("rm -f $d/$RemoteName.b64")
}
if ((Read-ReviewedUsb @("umask 077; mkdir $d && echo READY")).Trim() -ne 'READY') {throw 'Cannot create RAM workspace'}
$dispatched=$false
try {
    Upload-RamFile 'function-original.bin' 'original'
    Upload-RamFile 'function-candidate.bin' 'candidate'
    Upload-RamFile 'prepared-window.sh' 'window'
    Upload-RamFile 'prepared-restore.sh' 'restore'
    if ((Read-ReviewedUsb @("sh -n $d/window && sh -n $d/restore && echo SYNTAX_OK")).Trim() -ne 'SYNTAX_OK') {throw 'Device syntax check failed'}
    $plan.state='DISPATCHED_OR_UNCERTAIN'
    $plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $planPath
    $dispatched=$true
    $owner=(Read-ReviewedUsb @("sh $d/window >$d/status 2>&1 </dev/null & echo `$!")).Trim()
    if ($owner -notmatch '^\d+$') {throw 'Dispatch uncertain; do not retry'}
    $plan | Add-Member -NotePropertyName windowPid -NotePropertyValue $owner -Force
    $status=''
    for($n=0;$n -lt 20;$n++) {
        $status=(Read-ReviewedUsb @("head -c 4096 $d/status; true")) -join "`n"
        if ($status -match '(?m)^EXIT:') {break}
        Start-Sleep -Milliseconds 150
    }
    $status | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'last-window-status.txt')
    if ($status -notmatch '(?m)^ACTIVE_UNTIL_RESTART\r?$' -or $status -notmatch '(?m)^EXIT:0\r?$') {
        throw ('Installation did not finish successfully: '+$status)
    }
    $p=$plan.snapshot.processId;$address=$plan.snapshot.address;$length=$plan.snapshot.length
    $identity=(Read-ReviewedUsb @("cat /proc/sys/kernel/random/boot_id; awk '{print `$22}' /proc/$p/stat")) -join "`n"
    if ($identity.Trim() -ne ($plan.snapshot.bootId+"`n"+$plan.snapshot.startTime)) {throw 'Runtime identity changed; do not retry'}
    $hash=(Read-ReviewedUsb @("dd if=/proc/$p/mem bs=1 skip=$address count=$length 2>/dev/null | sha256sum")).Trim()
    if (($hash -split '\s+')[0] -ne $plan.candidate) {throw 'Installed function hash mismatch; inspect recovery files'}
    $stateCommand='awk ''/TracerPid:/{n++;if($2)t++} /State:/{if($2=="T"||$2=="t")s++} END{print n,t+0,s+0}'' /proc/'+$p+'/task/*/status'
    $states=(Read-ReviewedUsb @($stateCommand)).Trim()
    if ($states -notmatch '^\d+ 0 0$') {throw ('Threads are traced or paused: '+$states)}
    $plan.state='ACTIVE_UNTIL_RESTART_VERIFIED';$plan.deviceCodeWritten=$true
    $plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $planPath
    [ordered]@{state=$plan.state;probeAttached=$false;threadState=$states;maximumMeasuredSpeed=$null;manualRestoreAvailable=$true} |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'last-install-result.json')
    Write-Output 'RAM candidate verified active until process restart. No tracer or timer remains; manual recovery files retained in tmpfs.'
} catch {
    if (-not $dispatched) {
        foreach($f in 'original candidate window restore original.b64 candidate.b64 window.b64 restore.b64'.Split(' ')) {
            $null=Read-ReviewedUsb @("rm -f $d/$f")
        }
        $null=Read-ReviewedUsb @("rmdir $d")
    } else {
        $plan.state='DISPATCHED_REQUIRES_INSPECTION'
        $plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $planPath
    }
    throw
}
