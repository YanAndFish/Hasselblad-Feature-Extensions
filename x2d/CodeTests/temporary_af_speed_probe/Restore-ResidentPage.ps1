$ErrorActionPreference='Stop'
. "$PSScriptRoot/Usb.ps1"
$null=Read-ReviewedUsb @('test -f /tmp/afmf-resident/bridge.pid && touch /tmp/afmf-resident/stop')
Start-Sleep -Seconds 2
Read-ReviewedUsb @('cat /tmp/afmf-resident/status','pidof camera-gui')
