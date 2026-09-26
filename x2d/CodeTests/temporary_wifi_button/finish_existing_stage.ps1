$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/probe_shell.ps1"
$candidateDir = (Resolve-Path "$PSScriptRoot/../../outputs/4.2.0/temporary-wifi-button").Path
$manifest = Get-Content -Raw "$candidateDir/candidate.json" | ConvertFrom-Json
# 仅用于已核实的首次暂存：文件复制完整，第一处写入因 Android dd 不支持 conv 而未执行。
$check = [X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch(@(
    'sha256sum /tmp/hbl-x2d-wifi-button/camera-gui',
    'sha256sum /tmp/hbl-x2d-wifi-button/p0.bin',
    'awk ''$2=="/tmp/hbl-x2d-wifi-button" {print $3}'' /proc/mounts'
))
if ($check[0].Trim().Split(' ')[0] -ne $manifest.sourceSha256 -or $check[1].Trim().Split(' ')[0] -ne $manifest.patches[0].afterSha256 -or $check[2].Trim() -ne 'tmpfs') { throw '已有暂存不是可恢复的已知状态' }
$commands = @(
    'cd /tmp/hbl-x2d-wifi-button && (exec 3<>camera-gui; dd if=p0.bin bs=1 seek=26305338 >&3 2>/dev/null)',
    'cd /tmp/hbl-x2d-wifi-button && (exec 3<>camera-gui; printf X | dd bs=1 seek=24952400 >&3 2>/dev/null)',
    'sha256sum /tmp/hbl-x2d-wifi-button/camera-gui'
)
$response = [X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch($commands)
$stagedHash = $response[-1].Trim().Split(' ')[0]
if ($stagedHash -ne $manifest.candidateSha256) { throw '暂存候选哈希不匹配' }
[ordered]@{source='device-usb'; stage='verified'; guiSwitched=$false; ramDirectory='/tmp/hbl-x2d-wifi-button'; candidateSha256=$stagedHash; resumedKnownUnmodifiedCopy=$true; handlesClosed=$true} | ConvertTo-Json | Set-Content -Encoding utf8 "$candidateDir/device-stage.json"
Write-Output 'RAM_STAGE_VERIFIED guiSwitches=0 persistentWrites=0 handlesClosed=True'
