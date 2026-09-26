param([ValidateSet('Stage','Prepare','Activate','Rollback')][string]$Action)
$ErrorActionPreference='Stop'
if (-not $Action) { throw 'Explicit action required' }
$dir=Join-Path $PSScriptRoot 'native-input-candidate'
$stage='/blackbox/x2d-native-stage'
Add-Type -TypeDefinition (Get-Content "$PSScriptRoot/AdbUsbCheck.cs" -Raw)
if ($Action -ne 'Stage') {
 . "$PSScriptRoot/Usb.ps1"
 $baseline=(Read-ReviewedUsb @('sha256sum /system/bin/camera-gui /system/bin/camera-test')) -join "`n"
 if($baseline -notmatch '16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0' -or $baseline -notmatch 'e2621b84391d0e5601d9a22f9da460e982f7028bf5380e9f9d401a91380bb7b0'){throw 'Original executable hashes differ'}
 if($Action -eq 'Activate') {
  $readiness=(Read-ReviewedUsb @('cat /tmp/x2d-preview/status; grep NATIVE_READY /tmp/x2d-preview/native.log; grep INSPECT_OK_NO_WRITES /tmp/x2d-input-before-native/native-inspect.log')) -join "`n"
  if($readiness -notmatch 'READY_NATIVE' -or $readiness -notmatch 'NATIVE_READY 1' -or $readiness -notmatch 'INSPECT_OK_NO_WRITES 1'){throw 'Native inspection or readiness missing'}
 }
 $name='native-'+$Action.ToLowerInvariant()+'.sh'
 $hash=(Get-FileHash "$dir/$name").Hash.ToLowerInvariant()
 $command='set -- $(sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && sh '+$stage+'/'+$name
 [X2DAdbCheck.AdbUsbCheck]::RunShellBatch(@($command),'NATIVE_'+$Action.ToUpperInvariant()+'_OK')
 return
}
$commands=[Collections.Generic.List[string]]::new()
$commands.Add('test ! -L '+$stage+' && test -d '+$stage+' && echo X2D_NATIVE_STAGE_OK')
$manifest=Get-Content "$dir/package.json" -Raw | ConvertFrom-Json
$names=@($manifest.files | ForEach-Object {$_.source})+@('native-prepare.sh','native-activate.sh','native-rollback.sh','native-inspect.sh')
foreach($name in $names) {
 $path="$dir/$name"
 $hash=(Get-FileHash $path).Hash.ToLowerInvariant()
 $compressed=[IO.MemoryStream]::new()
 $gzip=[IO.Compression.GZipStream]::new($compressed,[IO.Compression.CompressionLevel]::Optimal,$true)
 $bytes=[IO.File]::ReadAllBytes($path);$gzip.Write($bytes,0,$bytes.Length);$gzip.Dispose()
 $encoded=[Convert]::ToBase64String($compressed.ToArray());$compressed.Dispose()
 for($i=0;$i -lt $encoded.Length;$i+=2800) {
  $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
  $commands.Add("test ! -L $stage/$name.gz.b64 && printf %s '$part' $op $stage/$name.gz.b64 && echo X2D_NATIVE_STAGE_OK")
 }
 $commands.Add("test ! -L $stage/$name && { base64 -d $stage/$name.gz.b64 | /system/bin/gzip -dc > $stage/$name; } && "+'set -- $(sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && echo X2D_NATIVE_STAGE_OK')
}
$result=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'X2D_NATIVE_STAGE_OK')
"NATIVE_STAGED_VERIFIED commands=$($result.Count)"
