param([ValidateSet('Plan','UploadScripts','Install','Restore')][string]$Action = 'Plan')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/probe_shell.ps1"
$candidateDir = (Resolve-Path "$PSScriptRoot/../../outputs/4.2.0/temporary-wifi-button").Path
$manifest = Get-Content -Raw "$candidateDir/candidate.json" | ConvertFrom-Json
$stage = Get-Content -Raw "$candidateDir/device-stage.json" | ConvertFrom-Json
if ($stage.stage -ne 'verified' -or $stage.candidateSha256 -ne $manifest.candidateSha256) { throw '尚无匹配的暂存证据' }
if ($manifest.candidateSha256 -notmatch '^[0-9a-f]{64}$') { throw '候选哈希格式错误' }
$restoreScript = @'
#!/system/bin/sh
set -eu
ram=/tmp/hbl-x2d-wifi-button
original=16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0
candidate=CANDIDATE_HASH
if [ -f "$ram/gui.pid" ]; then
    pid=$(cat "$ram/gui.pid")
    case "$pid" in ''|*[!0-9]*) exit 21;; esac
    if kill -0 "$pid" 2>/dev/null; then
        actual=$(sha256sum "/proc/$pid/exe" | cut -d ' ' -f 1)
        [ "$actual" = "$candidate" ] || exit 22
        kill -TERM "$pid"
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            actual=$(sha256sum "/proc/$pid/exe" | cut -d ' ' -f 1)
            [ "$actual" = "$candidate" ] || exit 23
            kill -KILL "$pid"
        fi
    fi
fi
mounted=$(awk '$2=="/system/bin/camera-gui" {print $2}' /proc/mounts)
if [ "$mounted" = /system/bin/camera-gui ]; then
    actual=$(sha256sum /system/bin/camera-gui | cut -d ' ' -f 1)
    [ "$actual" = "$candidate" ] || exit 24
    umount /system/bin/camera-gui
fi
actual=$(sha256sum /system/bin/camera-gui | cut -d ' ' -f 1)
[ "$actual" = "$original" ] || exit 25
start camera-gui
printf ORIGINAL_GUI_RESTART_REQUESTED
'@
$restoreScript = $restoreScript.Replace('CANDIDATE_HASH', $manifest.candidateSha256).Replace("`r`n", "`n") + "`n"
$installScript = @'
#!/system/bin/sh
set -eu
ram=/tmp/hbl-x2d-wifi-button
original=16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0
candidate=CANDIDATE_HASH
[ "$(awk '$2=="/tmp/hbl-x2d-wifi-button" {print $3}' /proc/mounts)" = tmpfs ] || exit 11
[ "$(sha256sum /system/bin/camera-gui | cut -d ' ' -f 1)" = "$original" ] || exit 12
[ "$(sha256sum "$ram/camera-gui" | cut -d ' ' -f 1)" = "$candidate" ] || exit 13
[ "$(getprop init.svc.camera-gui)" = running ] || exit 14
[ ! -e "$ram/gui.pid" ] || exit 15
mkdir -p "$ram/cache"
rollback_needed=1
trap 'code=$?; if [ "$rollback_needed" = 1 ]; then sh "$ram/restore.sh"; fi; exit "$code"' EXIT
printf UI_SWITCH_START
stop camera-gui
sleep 1
if [ "$(getprop init.svc.camera-gui)" != stopped ]; then
    start camera-gui
    exit 16
fi
if ! mount -o bind "$ram/camera-gui" /system/bin/camera-gui; then
    start camera-gui
    exit 17
fi
(
    export XDG_RUNTIME_DIR=/tmp
    export XDG_CACHE_HOME="$ram/cache"
    export QT_QPA_FONTDIR=/system/lib64/qt/lib/fonts
    export QML_DISABLE_DISK_CACHE=1
    exec /system/bin/camera-gui -platform wayland-egl --fullscreen
) </dev/null >/dev/null 2>&1 &
pid=$!
printf '%s' "$pid" >"$ram/gui.pid"
printf UI_PROCESS_LAUNCHED
for tick in 1 2 3; do
    sleep 1
    if ! kill -0 "$pid" 2>/dev/null; then
        exit 18
    fi
    printf UI_ALIVE
done
actual=$(sha256sum "/proc/$pid/exe" | cut -d ' ' -f 1)
if [ "$actual" != "$candidate" ]; then
    exit 19
fi
rollback_needed=0
printf TEMPORARY_GUI_RUNNING_VERIFIED
'@
$installScript = $installScript.Replace('CANDIDATE_HASH', $manifest.candidateSha256).Replace("`r`n", "`n") + "`n"
[IO.File]::WriteAllText("$candidateDir/install.sh", $installScript, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText("$candidateDir/restore.sh", $restoreScript, [Text.UTF8Encoding]::new($false))
$commands = [System.Collections.Generic.List[string]]::new()
foreach ($name in @('install','restore')) {
    $script = if ($name -eq 'install') { $installScript } else { $restoreScript }
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
    for ($position=0; $position -lt $encoded.Length; $position+=132) {
        $chunk=$encoded.Substring($position,[Math]::Min(132,$encoded.Length-$position))
        $redirect=if($position -eq 0){'>'}else{'>>'}
        $commands.Add("printf '%s' '$chunk' $redirect /tmp/hbl-x2d-wifi-button/$name.b64")
    }
    $commands.Add("cd /tmp/hbl-x2d-wifi-button && base64 -d $name.b64 >$name.sh && sh -n $name.sh")
}
$commands.Add('sha256sum /tmp/hbl-x2d-wifi-button/install.sh /tmp/hbl-x2d-wifi-button/restore.sh')
foreach($command in $commands){if($command.Length -gt 231){throw '脚本上传命令长度超限'}}
if($commands.Count -gt 100){throw '上传批次过长'}
Write-Output "APPLY_PLAN_VALID uploadCommands=$($commands.Count)"
if($Action -eq 'UploadScripts') {
    $responses=[X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch($commands.ToArray())
    $actual=$responses[-1].Trim() -split '\r?\n'
    if($actual.Count -ne 2){throw '脚本哈希回执格式错误'}
    for($i=0;$i -lt 2;$i++){
        $name=@('install','restore')[$i]
        $expected=(Get-FileHash -LiteralPath "$candidateDir/$name.sh" -Algorithm SHA256).Hash.ToLowerInvariant()
        if($actual[$i].Trim().Split(' ')[0] -ne $expected){throw '脚本哈希不匹配'}
    }
    Write-Output 'RAM_SCRIPTS_VERIFIED guiSwitches=0'
}
if($Action -eq 'Install' -or $Action -eq 'Restore') {
    if($Action -eq 'Install') {
        $restoreHash=[X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch(@('sha256sum /tmp/hbl-x2d-wifi-button/restore.sh'))[0].Trim().Split(' ')[0]
        if($restoreHash -ne (Get-FileHash -LiteralPath "$candidateDir/restore.sh" -Algorithm SHA256).Hash.ToLowerInvariant()){throw '恢复脚本哈希不匹配'}
    }
    $name=$Action.ToLowerInvariant()
    $hash=[X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch(@("sha256sum /tmp/hbl-x2d-wifi-button/$name.sh"))[0].Trim().Split(' ')[0]
    $expected=(Get-FileHash -LiteralPath "$candidateDir/$name.sh" -Algorithm SHA256).Hash.ToLowerInvariant()
    if($hash -ne $expected){throw '机内执行脚本与本地方案不一致'}
    $result=[X2DTemporaryUi.TemporaryUiUsb]::RunReviewedBatch(@("sh /tmp/hbl-x2d-wifi-button/$name.sh"))[0]
    $expectedMarker=if($Action -eq 'Install'){'TEMPORARY_GUI_RUNNING_VERIFIED'}else{'ORIGINAL_GUI_RESTART_REQUESTED'}
    if(-not $result.EndsWith($expectedMarker)){throw '界面切换结果未确认'}
    [ordered]@{source='device-usb';action=$Action;result=$expectedMarker;candidateSha256=$manifest.candidateSha256;handlesClosed=$true;bodyReboot=$false;buttonVisuallyConfirmed=$false} | ConvertTo-Json | Set-Content -Encoding utf8 "$candidateDir/device-$name.json"
    Write-Output $expectedMarker
}
