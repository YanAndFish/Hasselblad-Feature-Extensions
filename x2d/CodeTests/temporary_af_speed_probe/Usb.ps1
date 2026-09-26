$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
if (-not ('X2DTemporaryUi.TemporaryUiUsb' -as [type])) {
    $source = (Get-Content -Raw -Encoding UTF8 (Join-Path $repo 'native/WinUsbReadOnly.cs')).Replace('namespace HasselbladDebug','namespace X2DTemporaryUi').Replace('WinUsbReadOnly','TemporaryUiUsb')
    # Allow slower filesystem acknowledgements during reviewed staging uploads.
    # Host handle timeout only; no driver/device settings change or automatic retry.
    $source = $source.Replace('uint timeout = 2000;', 'uint timeout = 5000;')
    $methods = Get-Content -Raw -Encoding UTF8 (Join-Path $repo 'x2d/CodeTests/temporary_wifi_button/ShellTransport.inc.cs')
    $source = $source.Replace('        public void Dispose() {', $methods + '        public void Dispose() {')
    Add-Type -TypeDefinition $source
}
function Read-ReviewedUsb([string[]]$Commands) {
    # Never retry an uncertain response: hardware state might already have changed.
    [X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch($Commands)
}
