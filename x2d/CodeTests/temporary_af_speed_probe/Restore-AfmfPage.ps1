$ErrorActionPreference='Stop'
. "$PSScriptRoot/Usb.ps1"
$null=Read-ReviewedUsb @('test -f /tmp/afmf-page-bridge/bridge.pid && touch /tmp/afmf-page-bridge/stop')
Start-Sleep -Seconds 2
Read-ReviewedUsb @('cat /tmp/afmf-page-bridge/status')
