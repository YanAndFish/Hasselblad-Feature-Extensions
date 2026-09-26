param([switch]$Install)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/Usb.ps1"
$meta=Get-Content -Raw "$PSScriptRoot/resident-page-candidate.json" | ConvertFrom-Json
if(-not $Install){$meta;return}
$stage='/tmp/afmf-resident'
function Send-File([string]$name,[byte[]]$bytes){
    $s=[Convert]::ToBase64String($bytes);$commands=[Collections.Generic.List[string]]::new()
    for($i=0;$i -lt $s.Length;$i+=132){
        $chunk=$s.Substring($i,[Math]::Min(132,$s.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
        $commands.Add("printf %s '$chunk' $op $stage/$name.b64")
        if($commands.Count -eq 50){$null=Read-ReviewedUsb $commands.ToArray();$commands.Clear()}
    }
    if($commands.Count){$null=Read-ReviewedUsb $commands.ToArray()}
    $actual=(Read-ReviewedUsb @("base64 -d $stage/$name.b64 > $stage/$name && sha256sum $stage/$name")).Trim().Split(' ')[0]
    $sha=[Security.Cryptography.SHA256]::Create()
    try{$expected=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
    if($actual -ne $expected){throw "Upload mismatch: $name"}
}
function Mem-Hash([string]$proc,[uint64]$address,[int]$length){
    (Read-ReviewedUsb @("dd if=/proc/$proc/mem bs=1 skip=$address count=$length 2>/dev/null | sha256sum")).Trim().Split(' ')[0]
}
function Mem-Num([string]$proc,[uint64]$address,[int]$length){
    [uint64]::Parse((Read-ReviewedUsb @("dd if=/proc/$proc/mem bs=1 skip=$address count=$length 2>/dev/null | od -An -tu$length")).Trim())
}
$hash=(Read-ReviewedUsb @('sha256sum /system/bin/camera-gui')).Trim().Split(' ')[0]
if($hash -ne $meta.guiSha256){throw 'Unsupported camera GUI'}
$state=(Read-ReviewedUsb @('cat /tmp/afmf-page-bridge/state.sh')).Trim()+"`n"
if($state -notmatch '(?m)^gui_pid=(\d+)$'){throw 'Missing original GUI identity'}
$originalPid=$Matches[1]
$null=Read-ReviewedUsb @("test ! -e $stage && mkdir $stage")
foreach($pair in @(@('code','resident-code.bin'),@('hook','resident-hook.bin'),@('bridge.sh','afmf_resident_bridge.sh'))){Send-File $pair[0] ([IO.File]::ReadAllBytes("$PSScriptRoot/$($pair[1])"))}
$null=Read-ReviewedUsb @("cp /tmp/afmf-page-bridge/page.png $stage/page.png","sh -n $stage/bridge.sh")
& "$PSScriptRoot/Restore-AfmfPage.ps1"
$oldStatus=(Read-ReviewedUsb @('cat /tmp/afmf-page-bridge/status')).Trim()
if($oldStatus -ne 'RESTORED'){throw 'Old bridge restoration not confirmed'}
if((Read-ReviewedUsb @('pidof camera-gui')).Trim() -ne $originalPid){throw 'Unexpected GUI processes'}
$launch="#!/system/bin/sh`nexport XDG_RUNTIME_DIR=/tmp XDG_CACHE_HOME=$stage QT_QPA_FONTDIR=/system/lib64/qt/lib/fonts QML_DISABLE_DISK_CACHE=1`nexec /system/bin/camera-gui -platform wayland-egl --fullscreen --bus none --imagetest -u file:$stage/page.png -o 2147483647 -e 2147483646 --timeout 30`n"
Send-File 'launch.sh' ([Text.Encoding]::ASCII.GetBytes($launch))
$pageProc=''
try{
    $pageProc=(Read-ReviewedUsb @("nohup sh $stage/launch.sh > $stage/page.log 2>&1 < /dev/null & echo `$!")).Trim()
    if($pageProc -notmatch '^\d+$' -or $pageProc -eq $originalPid){throw 'Preview identity invalid'}
    $started=Get-Date
    Start-Sleep -Seconds 1
    $cmd=(Read-ReviewedUsb @("tr '\000' ' ' < /proc/$pageProc/cmdline")).Trim()
    if($cmd -notlike "*--imagetest*file:$stage/page.png*--timeout 30*"){throw 'Preview command mismatch'}
    $line=(Read-ReviewedUsb @("awk '/\/system\/bin\/camera-gui`$/ && `$2==`"r-xp`" {print}' /proc/$pageProc/maps")).Trim()
    if($line -notmatch '^([0-9a-f]+)-[0-9a-f]+ r-xp 00000000 '){throw 'Preview executable mapping missing'}
    $bias=[Convert]::ToUInt64($Matches[1],16)
    $cave=$bias+[uint64]$meta.cave;$hook=$bias+[uint64]$meta.hook;$box=$bias+[uint64]$meta.mailbox
    $pageStart=(Read-ReviewedUsb @("awk '{print `$22}' /proc/$pageProc/stat")).Trim()
    if((Mem-Hash $pageProc $cave $meta.length) -ne $meta.originalCaveHash -or (Mem-Hash $pageProc $hook 4) -ne $meta.originalHookHash){throw 'Original preview instructions differ'}
    if(((Get-Date)-$started).TotalSeconds -gt 15){throw 'Insufficient time before original timeout'}
    $null=Read-ReviewedUsb @("busybox dd if=$stage/code of=/proc/$pageProc/mem bs=1 seek=$cave count=$($meta.length) conv=notrunc")
    if((Mem-Hash $pageProc $cave $meta.length) -ne $meta.codeHash){throw 'Callback verification failed'}
    $null=Read-ReviewedUsb @("busybox dd if=$stage/hook of=/proc/$pageProc/mem bs=1 seek=$hook count=4 conv=notrunc")
    if((Mem-Hash $pageProc $hook 4) -ne $meta.hookHash){throw 'Hook verification failed'}
    $state+="page_pid=$pageProc`npage_start=$pageStart`nmailbox=$box`n"
    Send-File 'state.sh' ([Text.Encoding]::ASCII.GetBytes($state))
    $wait=[Math]::Max(1,33-((Get-Date)-$started).TotalSeconds);Start-Sleep -Seconds ([int]$wait)
    $count=Mem-Num $pageProc ($bias+0x21cf850+16) 8
    if($count -ne 1){throw 'Resident window count differs'}
    $array=Mem-Num $pageProc ($bias+0x21cf850+8) 8
    $window=Mem-Num $pageProc $array 8
    $private=Mem-Num $pageProc ($window+8) 8
    $visibleAddress=$private+0x90
    if((Mem-Num $pageProc $visibleAddress 1) -ne 0){throw 'Preloaded window did not hide'}
    $null=Read-ReviewedUsb @("printf '\001' > $stage/show","busybox dd if=$stage/show of=/proc/$pageProc/mem bs=1 seek=$box count=1 conv=notrunc")
    Start-Sleep -Milliseconds 200
    if((Mem-Num $pageProc $visibleAddress 1) -ne 1){throw 'Resident show failed'}
    $null=Read-ReviewedUsb @("busybox dd if=/dev/zero of=/proc/$pageProc/mem bs=1 seek=$box count=1 conv=notrunc")
    Start-Sleep -Milliseconds 200
    if((Mem-Num $pageProc $visibleAddress 1) -ne 0){throw 'Resident hide failed'}
    $null=Read-ReviewedUsb @("nohup sh $stage/bridge.sh > $stage/bridge.log 2>&1 < /dev/null & echo `$! > $stage/bridge.pid")
    Start-Sleep -Seconds 1
    $status=(Read-ReviewedUsb @("cat $stage/status")).Trim()
    if($status -ne 'READY'){throw 'Resident button listener not ready'}
    [ordered]@{installed=$true;previewPid=$pageProc;previewStart=$pageStart;originalPid=$originalPid;mailbox=$box;visibleAddress=$visibleAddress;sameProcessShowHide=$true;status=$status;temporary=$true} | ConvertTo-Json | Tee-Object -FilePath "$PSScriptRoot/resident-install-result.json"
}catch{
    if($pageProc -match '^\d+$' -and $pageProc -ne $originalPid){$null=Read-ReviewedUsb @("kill -TERM $pageProc 2>/dev/null; true")}
    throw
}
