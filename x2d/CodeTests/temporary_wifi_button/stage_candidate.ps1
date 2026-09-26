param([switch]$Device)
$ErrorActionPreference = 'Stop'
$stageDeviceRequested = [bool]$Device
. "$PSScriptRoot/probe_shell.ps1"
$candidateDir = (Resolve-Path "$PSScriptRoot/../../outputs/4.2.0/temporary-wifi-button").Path
$manifest = Get-Content -Raw "$candidateDir/candidate.json" | ConvertFrom-Json
$validation = Get-Content -Raw "$candidateDir/host-validation.json" | ConvertFrom-Json
if ($manifest.sourceSha256 -ne '16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0' -or $manifest.patches.Count -ne 2 -or $validation.wholeCandidateSyntax -ne 'pass' -or $validation.fiveEmptyClicks -ne 'pass') { throw '未验证候选' }
$commands = [System.Collections.Generic.List[string]]::new()
$ram = '/tmp/hbl-x2d-wifi-button'
$commands.Add("test ! -e $ram && mkdir $ram && mount -t tmpfs -o size=64m tmpfs $ram && printf RAM_STAGE_READY")
$commands.Add("cp /system/bin/camera-gui $ram/camera-gui && chmod 755 $ram/camera-gui")
for ($index = 0; $index -lt 2; $index++) {
    $patch = $manifest.patches[$index]
    if ($patch.file -ne "patch-$index.bin") { throw '补丁名称不匹配' }
    if (($index -eq 0 -and ($patch.offset -ne 26305338 -or $patch.length -ne 5753)) -or ($index -eq 1 -and ($patch.offset -ne 24952400 -or $patch.length -ne 1))) { throw '补丁范围不匹配' }
    $localPatch = Join-Path $candidateDir $patch.file
    if ((Get-FileHash -LiteralPath $localPatch -Algorithm SHA256).Hash.ToLowerInvariant() -ne $patch.afterSha256) { throw '补丁哈希不匹配' }
    $encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($localPatch))
    for ($position = 0; $position -lt $encoded.Length; $position += 144) {
        $chunk = $encoded.Substring($position, [Math]::Min(144, $encoded.Length - $position))
        $redirection = if ($position -eq 0) { '>' } else { '>>' }
        $commands.Add("printf '%s' '$chunk' $redirection $ram/p$index.b64")
    }
    $commands.Add("base64 -d $ram/p$index.b64 >$ram/p$index.bin")
    $commands.Add("cd $ram && (exec 3<>camera-gui; dd if=p$index.bin bs=1 seek=$($patch.offset) >&3 2>/dev/null)")
}
$commands.Add("sha256sum $ram/camera-gui")
foreach ($command in $commands) { if ([Text.Encoding]::UTF8.GetByteCount($command) -gt 231) { throw '命令长度超限' } }
if ($commands.Count -gt 100) { throw '批次长度超限' }
Write-Output "STAGE_PLAN_VALID commands=$($commands.Count) guiSwitches=0 persistentWrites=0"
if ($stageDeviceRequested) {
    $sourceHash = [X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch(@('sha256sum /system/bin/camera-gui'))[0].Trim().Split(' ')[0]
    if ($sourceHash -ne $manifest.sourceSha256) { throw '实机原始界面哈希不匹配' }
    $responses = [X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch($commands.ToArray())
    if ($responses[0] -ne 'RAM_STAGE_READY') { throw '暂存初始化回执错误' }
    $stagedHash = $responses[-1].Trim().Split(' ')[0]
    if ($stagedHash -ne $manifest.candidateSha256) { throw '相机暂存哈希不匹配' }
    $report = [ordered]@{ source='device-usb'; stage='verified'; guiSwitched=$false; ramDirectory=$ram; candidateSha256=$stagedHash; shellCommands=$commands.Count+1; handlesClosed=$true }
    $report | ConvertTo-Json | Set-Content -Encoding utf8 "$candidateDir/device-stage.json"
    Write-Output 'RAM_STAGE_VERIFIED guiSwitches=0 persistentWrites=0 handlesClosed=True'
}
