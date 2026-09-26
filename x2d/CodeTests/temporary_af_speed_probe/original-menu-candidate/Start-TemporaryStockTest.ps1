$ErrorActionPreference='Stop'
. "$(Split-Path $PSScriptRoot -Parent)/Usb.ps1"
$bytes=[IO.File]::ReadAllBytes("$PSScriptRoot/temporary-stock-test.sh")
$encoded=[Convert]::ToBase64String($bytes)
$commands=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt $encoded.Length;$i+=132) {
 $part=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
 $commands.Add("printf %s '$part' $op /tmp/x2d-native-menu-test.b64")
}
$commands.Add('base64 -d /tmp/x2d-native-menu-test.b64 > /tmp/x2d-native-menu-test.sh && sh -n /tmp/x2d-native-menu-test.sh')
$null=Read-ReviewedUsb $commands.ToArray()
$hash=(Get-FileHash "$PSScriptRoot/temporary-stock-test.sh").Hash.ToLowerInvariant()
$check=(Read-ReviewedUsb @('sha256sum /tmp/x2d-native-menu-test.sh')) -join "`n"
if(-not $check.StartsWith($hash)){throw 'Test script readback mismatch'}
Read-ReviewedUsb @('nohup sh /tmp/x2d-native-menu-test.sh > /tmp/x2d-native-menu-test.log 2>&1 < /dev/null & echo NATIVE_MENU_TEST_STARTED')
