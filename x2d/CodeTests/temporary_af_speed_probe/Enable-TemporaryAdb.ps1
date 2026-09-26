$ErrorActionPreference='Stop'
. "$PSScriptRoot/Usb.ps1"
$current=(Read-ReviewedUsb @('getprop sys.usb.config; getprop init.svc.adbd')) -join "`n"
if($current.Trim() -ne "rndis,mass_storage,bulk,acm`nstopped"){throw 'USB baseline differs; do not overlap USB switching timers'}
$script=@'
#!/system/bin/sh
sleep 2
setprop sys.usb.config none
sleep 1
setprop sys.usb.config rndis,mass_storage,bulk,acm,adb
sleep 90
setprop sys.usb.config none
sleep 1
setprop sys.usb.config rndis,mass_storage,bulk,acm
'@
$encoded=[Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($script.Replace("`r`n","`n")+"`n"))
$commands=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt $encoded.Length;$i+=132){
    $part=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
    $commands.Add("printf %s '$part' $op /tmp/adb-inspect.b64")
}
$commands.Add('base64 -d /tmp/adb-inspect.b64 > /tmp/adb-inspect.sh && sh -n /tmp/adb-inspect.sh')
$null=Read-ReviewedUsb $commands.ToArray()
Read-ReviewedUsb @('nohup sh /tmp/adb-inspect.sh > /tmp/adb-inspect.log 2>&1 < /dev/null & echo ADB_SWITCH_SCHEDULED')
Start-Sleep -Seconds 6
