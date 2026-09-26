param([switch]$Install)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/Usb.ps1"
$expected='16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0'
function Read-MemoryWords([string]$proc,[uint64]$address,[int]$length) {
    $v=(Read-ReviewedUsb @("dd if=/proc/$proc/mem bs=1 skip=$address count=$length 2>/dev/null | od -An -tu8")) -join ' '
    @($v.Trim() -split '\s+' | ForEach-Object {[uint64]::Parse($_)})
}
$guiProcess=(Read-ReviewedUsb @('pidof camera-gui')).Trim()
if($guiProcess -notmatch '^\d+$'){throw 'Expected one original GUI'}
$hash=(Read-ReviewedUsb @('sha256sum /system/bin/camera-gui')).Trim().Split(' ')[0]
if($hash -ne $expected){throw 'Unsupported GUI version'}
$mapCommand='awk ''$2=="rw-p" {print $1,$2} /\/system\/bin\/camera-gui$/ && $2=="r-xp" {print}'' /proc/'+$guiProcess+'/maps'
$maps=(Read-ReviewedUsb @($mapCommand)) -join "`n"
$m=[regex]::Match($maps,'(?m)^([0-9a-f]+)-[0-9a-f]+ r-xp 00000000 .* /system/bin/camera-gui$')
if(-not $m.Success){throw 'GUI mapping missing'}
$bias=[Convert]::ToUInt64($m.Groups[1].Value,16)
function Assert-Rw([uint64]$address,[int]$length) {
    foreach($line in ($maps -split "`n")) {
        if($line -match '^([0-9a-f]+)-([0-9a-f]+) rw-p(?: |$)') {
            $lo=[Convert]::ToUInt64($Matches[1],16); $hi=[Convert]::ToUInt64($Matches[2],16)
            if($address -ge $lo -and $address+$length -le $hi){return}
        }
    }
    throw 'Pointer outside readable writable mapping'
}
$instance=(Read-MemoryWords $guiProcess ($bias+0x21bc838) 8)[0]
Assert-Rw $instance 32
$head=Read-MemoryWords $guiProcess $instance 32
if($head[0] -ne ($bias+0x20d5620)){throw 'Unexpected key-handler type'}
$tree=$head[2]; Assert-Rw $tree 24
$node=(Read-MemoryWords $guiProcess ($tree+16) 8)[0]
$found=$false
for($i=0;$i -lt 16 -and $node -ne 0;$i++) {
    Assert-Rw $node 40
    $w=Read-MemoryWords $guiProcess $node 40
    $key=[int]($w[3] -shr 32)
    if($key -eq 70){$found=$true; break}
    $node=if($key -lt 70){$w[1]}else{$w[0]}
}
if(-not $found -or ($w[4] -shr 32) -ne 0){throw 'Front-key mapping not found'}
$original=$w[4] -band 255
if($original -gt 43){throw 'Unknown original function'}
$start=(Read-ReviewedUsb @("awk '{print `$22}' /proc/$guiProcess/stat")).Trim()
if($start -notmatch '^\d+$'){throw 'Process identity missing'}
$state="gui_pid=$guiProcess`ngui_start=$start`nmap_pointer_address=$($instance+16)`nmap_pointer=$tree`nkey_address=$($node+28)`nmodifiers_address=$($node+36)`nfunction_address=$($node+32)`noriginal_function=$original`n"
$plan=[ordered]@{source='device-read-only';originalFunction=$original;physicalKey='AF/MF';temporary=$true;imageSha256=(Get-FileHash "$PSScriptRoot/afmf-custom-page.png").Hash.ToLowerInvariant();installed=$false}
if(-not $Install){$plan | ConvertTo-Json; return}
$stage='/tmp/afmf-page-bridge'
$ready=Read-ReviewedUsb @("test ! -e $stage && mkdir $stage && printf STAGE_CREATED")
if($ready.Trim() -ne 'STAGE_CREATED'){throw 'Stage creation not confirmed'}
$files=@{
    'state.sh'=[Text.Encoding]::ASCII.GetBytes($state)
    'bridge.sh'=[IO.File]::ReadAllBytes("$PSScriptRoot/afmf_page_bridge.sh")
    'page.png'=[IO.File]::ReadAllBytes("$PSScriptRoot/afmf-custom-page.png")
}
foreach($name in @('state.sh','bridge.sh','page.png')) {
    $bytes=$files[$name]; $encoded=[Convert]::ToBase64String($bytes)
    $commands=[Collections.Generic.List[string]]::new()
    for($offset=0;$offset -lt $encoded.Length;$offset+=132) {
        $chunk=$encoded.Substring($offset,[Math]::Min(132,$encoded.Length-$offset))
        $redirect=if($offset -eq 0){'>'}else{'>>'}
        $commands.Add("printf %s '$chunk' $redirect $stage/$name.b64")
        if($commands.Count -eq 60){$null=Read-ReviewedUsb $commands.ToArray();$commands.Clear()}
    }
    if($commands.Count){$null=Read-ReviewedUsb $commands.ToArray()}
    $actual=(Read-ReviewedUsb @("base64 -d $stage/$name.b64 > $stage/$name && sha256sum $stage/$name")).Trim().Split(' ')[0]
    $sha=[Security.Cryptography.SHA256]::Create()
    try{$expectedFile=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
    if($actual -ne $expectedFile){throw "Uploaded $name differs"}
}
$syntax=Read-ReviewedUsb @("sh -n $stage/bridge.sh && sh -n $stage/state.sh && printf SYNTAX_OK")
if($syntax.Trim() -ne 'SYNTAX_OK'){throw 'Device syntax check failed'}
$null=Read-ReviewedUsb @("nohup sh $stage/bridge.sh > $stage/bridge.log 2>&1 < /dev/null & echo `$! > $stage/bridge.pid")
Start-Sleep -Seconds 1
$status=(Read-ReviewedUsb @("cat $stage/status")).Trim()
$plan.installed=($status -eq 'READY');$plan.source='device-install';$plan['status']=$status
$plan | ConvertTo-Json | Set-Content -Encoding utf8 "$PSScriptRoot/afmf-install-result.json"
$plan | ConvertTo-Json
if(-not $plan.installed){throw 'Bridge is not ready; inspect restoration state'}
