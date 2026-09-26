param([ValidateSet('Compile','Stage','Install','Remove')][string]$Action='Compile')
$ErrorActionPreference='Stop'
$dir=$PSScriptRoot
$source=Get-Content -Raw "$dir/AdbUsbCheck.cs"
$methods=''
foreach($entry in @(@('InstallBootDiagnostic','install_boot_diagnostic.sh'),@('RemoveBootDiagnostic','remove_boot_diagnostic.sh'))){
    $script=([IO.File]::ReadAllText("$dir/$($entry[1])")).Replace("`r`n","`n")
    if([Text.Encoding]::ASCII.GetByteCount("shell:$script`0") -gt 4096){throw 'ADB command exceeds frame limit'}
    $methods+='public static string '+$entry[0]+'(){ return RunShell(@"'+$script.Replace('"','""')+'"); }'+"`n"
}
$anchor='        private static string RunShell(string script) {'
if(-not $source.Contains($anchor)){throw 'ADB helper source changed'}
if(-not ('X2DAdbCheck.AdbUsbCheck' -as [type])){Add-Type -TypeDefinition $source.Replace($anchor,$methods+$anchor)}
if($Action -eq 'Compile'){ 'BOOT_TOOL_COMPILED_NO_CAMERA_ACCESS'; return }
if($Action -eq 'Install'){[X2DAdbCheck.AdbUsbCheck]::InstallBootDiagnostic(); return}
if($Action -eq 'Remove'){[X2DAdbCheck.AdbUsbCheck]::RemoveBootDiagnostic(); return}
. "$dir/Usb.ps1"
$stage='/blackbox/x2d-autoload-probe'
$baseline=(Read-ReviewedUsb @('sha256sum /system/bin/camera-test','test ! -e /blackbox/x2d-autoload-probe && test ! -L /blackbox/x2d-autoload-probe && echo STAGE_ABSENT')) -join "`n"
if($baseline -notmatch 'e2621b84391d0e5601d9a22f9da460e982f7028bf5380e9f9d401a91380bb7b0' -or $baseline -notmatch 'STAGE_ABSENT'){throw 'Stage or firmware baseline differs'}
$null=Read-ReviewedUsb @("mkdir -m 700 $stage")
foreach($entry in @(@('libx2d_preview_probe.so','libx2d_preview_probe.so'),@('x2d-preview-probe.rc','x2d-preview-probe.rc.candidate'))){
    $bytes=[IO.File]::ReadAllBytes("$dir/$($entry[1])")
    $encoded=[Convert]::ToBase64String($bytes)
    $commands=[Collections.Generic.List[string]]::new()
    for($i=0;$i -lt $encoded.Length;$i+=132){
        $chunk=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i))
        $op=if($i -eq 0){'>'}else{'>>'}
        $commands.Add("printf %s '$chunk' $op $stage/$($entry[0]).b64")
        if($commands.Count -eq 50){$null=Read-ReviewedUsb $commands.ToArray();$commands.Clear()}
    }
    if($commands.Count){$null=Read-ReviewedUsb $commands.ToArray()}
    $remote=(Read-ReviewedUsb @("base64 -d $stage/$($entry[0]).b64 > $stage/$($entry[0]) && sha256sum $stage/$($entry[0])")).Trim().Split(' ')[0]
    $expected=(Get-FileHash -LiteralPath "$dir/$($entry[1])" -Algorithm SHA256).Hash.ToLowerInvariant()
    if($remote -ne $expected){throw 'Staging hash differs'}
}
'BOOT_DIAGNOSTIC_STAGED_NOT_INSTALLED'
