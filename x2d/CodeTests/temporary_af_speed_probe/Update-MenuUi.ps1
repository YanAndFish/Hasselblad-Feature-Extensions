param([ValidateSet('Build','Stage','StageAdb','Install','Rollback')][string]$Action='Build',
      [ValidateSet('Flash','Input')][string]$Variant='Flash',
      [switch]$FromWindowInput,
      [switch]$FromFrameInput,
      [switch]$FromResidentInput,
      [switch]$FromTimingInput,
      [switch]$FromDirectInput,
      [switch]$FromFastHideInput)
$ErrorActionPreference='Stop'
$dir=Join-Path $PSScriptRoot 'menu-candidate'
$stage='/blackbox/x2d-menu-stage'
$files=@(
 @{source='x2d-menu-v1-main.qml'; target='/system/etc/x2d-menu-v1-main.qml'; old='39ef3ee7b2e65db1776c769c03dc36333ced31c3e822ace90128a9ea901c7a0d'},
 @{source='boot_menu_candidate.sh'; target='/system/etc/x2d-preview-loader.sh'; old='f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68'},
 @{source='boot_menu_candidate.sh'; target='/system/etc/x2d-menu-candidate.sh'; old='f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68'}
)
if($Variant -eq 'Input'){
 $dir=Join-Path $PSScriptRoot 'input-candidate'
 $stage='/blackbox/x2d-input-stage'
 $files[0].old='f7305289e6d92e77288bca2e9f08e7b85fa7333eea4580976de0aad3c51c9ff8'
 $files[1].old='bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457'
 $files[2].old=$files[1].old
}
foreach($f in $files){$f.new=(Get-FileHash "$dir/$($f.source)").Hash.ToLowerInvariant();$f.current=$f.old}
if($FromWindowInput){
 if($Variant -ne 'Input'){throw 'FromWindowInput is only valid for the known Input candidate'}
 $files[0].current='c8893223a3e510a887e209623506063fc91251e09191fe14782ac803d5ff6017'
 $files[1].current='7392ef47b017c6bce866f2d6a3def2c7c381e8947dbe9efb6e2941df35f61aa9'
 $files[2].current=$files[1].current
}
if($FromFrameInput){
 if($Variant -ne 'Input' -or $FromWindowInput){throw 'FromFrameInput requires Input and excludes FromWindowInput'}
 $files[0].current='db22db6e7a50d4934bdf6821fb19b6378a597aaebb18c588346c7dbd27257d93'
 $files[1].current='a029add3b68af1b6040fd0284f8483c01a461a0537d52b39cf6b6587ae9776d5'
 $files[2].current=$files[1].current
}
if($FromResidentInput){
 if($Variant -ne 'Input' -or $FromWindowInput -or $FromFrameInput){throw 'FromResidentInput requires Input and excludes other source revisions'}
 $files[0].current='db22db6e7a50d4934bdf6821fb19b6378a597aaebb18c588346c7dbd27257d93'
 $files[1].current='1c31e10c0bfdc5a69298e9f0759db50e32b26b46a833ecc9d72da9c4bdccfc38'
 $files[2].current=$files[1].current
}
if($FromTimingInput){
 if($Variant -ne 'Input' -or $FromWindowInput -or $FromFrameInput -or $FromResidentInput){throw 'FromTimingInput requires Input and excludes other source revisions'}
 $files[0].current='1d6ed58559c3ef3f2c8015121b0fb5ecb4aa1854e6eb003cdb5d81f6f41695b1'
 $files[1].current='2fe1e1c0c6bf2c8a2447d6192d2e6b6e3d28c08fa2286ce8a9c94f63fc0acf7c'
 $files[2].current=$files[1].current
}
if($FromDirectInput){
 if($Variant -ne 'Input' -or $FromWindowInput -or $FromFrameInput -or $FromResidentInput -or $FromTimingInput){throw 'FromDirectInput requires Input and excludes other source revisions'}
 $files[0].current='1d6ed58559c3ef3f2c8015121b0fb5ecb4aa1854e6eb003cdb5d81f6f41695b1'
 $files[1].current='fcab807960bafee6d05fd0425a37ea4d5a0e13d40775b1460802852b3408376d'
 $files[2].current=$files[1].current
}
if($FromFastHideInput){
 if($Variant -ne 'Input' -or $FromWindowInput -or $FromFrameInput -or $FromResidentInput -or $FromTimingInput -or $FromDirectInput){throw 'FromFastHideInput requires Input and excludes other source revisions'}
 $files[0].current='1d6ed58559c3ef3f2c8015121b0fb5ecb4aa1854e6eb003cdb5d81f6f41695b1'
 $files[1].current='c4eff9745c4630354e956612211fc9f04647ca5da7b80b4bc05ed70af3a610c9'
 $files[2].current=$files[1].current
}
$header=@'
set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }

'@
$install=$header;$rollback=$header
foreach($f in $files){
 $target=$f.target;$backup=$target+'.before-flash-ui'
 $install+='[ ! -L '+$target+' ] && [ ! -L '+$backup+' ] || exit 34'+"`n"
 $install+="if [ -e $backup ]; then hashok $backup $($f.old); fi`n"
 if($FromWindowInput -or $FromFrameInput -or $FromResidentInput -or $FromTimingInput -or $FromDirectInput -or $FromFastHideInput){$install+="hashok $backup $($f.old)`n"}
 $install+="hashok $target $($f.current)`nhashok $stage/flash-$($f.source) $($f.new)`n"
 $rollback+='[ ! -L '+$target+' ] && [ ! -L '+$backup+' ] || exit 34'+"`n"
 $rollback+="hashok $target $($f.new)`nhashok $backup $($f.old)`n"
}
$install+=@'
done_ok=0; saved=''
finish() {
 if [ "$done_ok" = 0 ]; then
  for path in $saved; do /system/bin/cat "$path.before-flash-ui" > "$path"; /system/bin/chmod 0644 "$path"; done
  /system/bin/sync
 fi
 restore_mount
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system

'@
foreach($f in $files){
 $target=$f.target;$backup=$target+'.before-flash-ui'
 $install+="if [ ! -e $backup ]; then`n(set -C; : > $backup)`n/system/bin/cat $target > $backup`n/system/bin/chmod 0644 $backup`nfi`nhashok $backup $($f.old)`n"
 $install+='saved="'+$target+' $saved"'+"`n"
}
foreach($f in $files){$install+="/system/bin/cat $stage/flash-$($f.source) > $($f.target)`n/system/bin/chmod 0644 $($f.target)`nhashok $($f.target) $($f.new)`n"}
$install+="/system/bin/sync`nrestore_mount`n"+'[ "$(state)" = "$original" ] || exit 44'+"`ndone_ok=1`necho FLASH_UI_INSTALLED`n"
$rollback+="trap restore_mount EXIT`n( /system/bin/sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &`n/system/bin/mount -o remount,rw /system`n"
foreach($f in $files){$rollback+="/system/bin/cat $($f.target).before-flash-ui > $($f.target)`n/system/bin/chmod 0644 $($f.target)`nhashok $($f.target) $($f.old)`n"}
$rollback+="/system/bin/sync`nrestore_mount`necho PRE_FLASH_MENU_RESTORED`n"
if($Variant -eq 'Input'){
 $install=$install.Replace('.before-flash-ui','.before-input-ui').Replace('FLASH_UI_INSTALLED','INPUT_UI_INSTALLED')
 $rollback=$rollback.Replace('.before-flash-ui','.before-input-ui').Replace('PRE_FLASH_MENU_RESTORED','PRE_INPUT_MENU_RESTORED')
}
[IO.File]::WriteAllText("$dir/flash-install.sh",$install.Replace("`r`n","`n"),[Text.Encoding]::ASCII)
[IO.File]::WriteAllText("$dir/flash-rollback.sh",$rollback.Replace("`r`n","`n"),[Text.Encoding]::ASCII)
[IO.File]::WriteAllText("$dir/flash-update-manifest.json",($files | ConvertTo-Json -Depth 5),[Text.Encoding]::ASCII)
if($Action -eq 'Build'){'FLASH_UPDATE_BUILT_NO_DEVICE_ACCESS';return}
if($Action -eq 'StageAdb'){
 $src=Get-Content "$PSScriptRoot/AdbUsbCheck.cs" -Raw
 Add-Type -TypeDefinition $src
 $commands=[Collections.Generic.List[string]]::new()
 $commands.Add('test -x /system/bin/gzip && test ! -L '+$stage+' && test -d '+$stage+' && echo X2D_STAGE_OK')
 foreach($pair in @(@('x2d-menu-v1-main.qml','flash-x2d-menu-v1-main.qml'),@('boot_menu_candidate.sh','flash-boot_menu_candidate.sh'),@('flash-install.sh','flash-install.sh'),@('flash-rollback.sh','flash-rollback.sh'))){
  $path="$dir/$($pair[0])";$name=$pair[1];$hash=(Get-FileHash $path).Hash.ToLowerInvariant()
  $compressed=[IO.MemoryStream]::new()
  $gzip=[IO.Compression.GZipStream]::new($compressed,[IO.Compression.CompressionLevel]::Optimal,$true)
  $bytes=[IO.File]::ReadAllBytes($path);$gzip.Write($bytes,0,$bytes.Length);$gzip.Dispose()
  $encoded=[Convert]::ToBase64String($compressed.ToArray());$compressed.Dispose()
  for($i=0;$i -lt $encoded.Length;$i+=2800){
   $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
   $commands.Add("test ! -L $stage/$name.adb.gz.b64 && printf %s '$part' $op $stage/$name.adb.gz.b64 && echo X2D_STAGE_OK")
  }
  $commands.Add("test ! -L $stage/$name && { base64 -d $stage/$name.adb.gz.b64 | /system/bin/gzip -dc > $stage/$name; } && "+'set -- $(/system/bin/sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && echo X2D_STAGE_OK')
 }
 $result=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'X2D_STAGE_OK')
 "ADB_STAGED_ALL_VERIFIED commands=$($result.Count)"
 return
}
if($Action -in @('Install','Rollback')){
 $name=if($Action -eq 'Install'){'flash-install.sh'}else{'flash-rollback.sh'}
 $hash=(Get-FileHash "$dir/$name").Hash.ToLowerInvariant()
 $command='set -- $(/system/bin/sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && /system/bin/sh '+$stage+'/'+$name
 $src=Get-Content "$PSScriptRoot/AdbUsbCheck.cs" -Raw
 Add-Type -TypeDefinition $src
 [X2DAdbCheck.AdbUsbCheck]::RunShellBatch(@($command),'');return
}
. "$PSScriptRoot/Usb.ps1"
$null=Read-ReviewedUsb @('[ ! -L '+$stage+' ] && { [ -d '+$stage+' ] || mkdir -m 700 '+$stage+'; }')
foreach($pair in @(@('x2d-menu-v1-main.qml','flash-x2d-menu-v1-main.qml'),@('boot_menu_candidate.sh','flash-boot_menu_candidate.sh'),@('flash-install.sh','flash-install.sh'),@('flash-rollback.sh','flash-rollback.sh'))){
 $path="$dir/$($pair[0])";$name=$pair[1];$hash=(Get-FileHash $path).Hash.ToLowerInvariant()
 $compressed=[IO.MemoryStream]::new()
 $gzip=[IO.Compression.GZipStream]::new($compressed,[IO.Compression.CompressionLevel]::Optimal,$true)
 $bytes=[IO.File]::ReadAllBytes($path)
 $gzip.Write($bytes,0,$bytes.Length);$gzip.Dispose()
 $encoded=[Convert]::ToBase64String($compressed.ToArray());$compressed.Dispose()
 $cmds=[Collections.Generic.List[string]]::new()
 for($i=0;$i -lt $encoded.Length;$i+=132){
  $part=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
  $cmds.Add("printf %s '$part' $op $stage/$name.gz.b64")
  if($cmds.Count -eq 20){$null=Read-ReviewedUsb $cmds.ToArray();$cmds.Clear()}
 }
 if($cmds.Count){$null=Read-ReviewedUsb $cmds.ToArray()}
 $out=(Read-ReviewedUsb @("base64 -d $stage/$name.gz.b64 | busybox gzip -dc > $stage/$name && sha256sum $stage/$name")) -join "`n"
 if($out -notmatch $hash){throw "Staging hash mismatch: $name"}
 "STAGED $name"
}
