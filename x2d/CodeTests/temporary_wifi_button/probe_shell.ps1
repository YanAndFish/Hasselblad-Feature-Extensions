param([switch]$Device)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path "$PSScriptRoot/../../..").Path
$source = (Get-Content -Raw "$projectRoot/native/WinUsbReadOnly.cs").Replace('namespace HasselbladDebug', 'namespace X2DTemporaryUi').Replace('WinUsbReadOnly', 'TemporaryUiUsb')
$methods = Get-Content -Raw "$PSScriptRoot/ShellTransport.inc.cs"
$source = $source.Replace('        public void Dispose() {', $methods + '        public void Dispose() {')
Add-Type -TypeDefinition $source
[X2DTemporaryUi.TemporaryUiUsb]::SelfTestShell()
if ($Device) {
    # 只打印固定标记：不读取设置、文件、标识或照片，不启动 GUI。
    [X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch(@('printf X2D_UI_PROBE_OK'))
}
