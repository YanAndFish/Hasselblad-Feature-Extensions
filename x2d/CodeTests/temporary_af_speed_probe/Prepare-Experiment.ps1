param([ValidateRange(5,60)][int]$Seconds=15,[switch]$UntilRestart)
. (Join-Path $PSScriptRoot 'Snapshot.ps1')
$snapshot=Get-AfSnapshot
$spec=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'candidate.json') | ConvertFrom-Json
foreach ($pair in @(@('function-original.bin',$spec.functionSha256),@('function-candidate.bin',$spec.candidateSha256))) {
    if ((Get-FileHash -Algorithm SHA256 (Join-Path $PSScriptRoot $pair[0])).Hash.ToLowerInvariant() -ne $pair[1]) {throw 'Local function artifact mismatch'}
}
$deviceRoot='/tmp/afw-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$prefix=@"
P=$($snapshot.processId)
START=$($snapshot.startTime)
BOOT='$($snapshot.bootId)'
ADDRESS=$($snapshot.address)
LENGTH=$($snapshot.length)
PRODUCT=$($snapshot.productAddress)
ORIGINAL='$($spec.functionSha256)'
CANDIDATE='$($spec.candidateSha256)'
WINDOW=$Seconds
D='$deviceRoot'
"@
$backend=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'device_backend.sh')
$transaction=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'transaction.sh')
$entry=if($UntilRestart){'tx_install_until_restart'}else{'tx_run'}
$script=($prefix+"`n"+$backend+"`n"+$transaction+"`necho `$`$ >`"`$D/owner`" || exit 80`n$entry`nexit `$?`n").Replace("`r`n","`n")
$restore=($prefix+"`n"+$backend+"`n"+$transaction+@'

# Offline recovery entry; refuse unknown or partial bytes from another writer.
backend_same || exit 81
if backend_is_original; then backend_log ALREADY_ORIGINAL; exit 0; fi
backend_is_candidate || { backend_log UNKNOWN_BYTES_NO_WRITE; exit 82; }
tx_dirty=1
trap tx_finish EXIT
trap 'exit 97' HUP INT TERM
tx_restore
exit $?
'@).Replace("`r`n","`n")
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'prepared-window.sh'),$script,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'prepared-restore.sh'),$restore,[Text.UTF8Encoding]::new($false))
$plan=[ordered]@{state='PREPARED_NOT_UPLOADED';snapshot=$snapshot;deviceRoot=$deviceRoot;seconds=$Seconds;untilRestart=[bool]$UntilRestart;
    original=$spec.functionSha256;candidate=$spec.candidateSha256;deviceCodeWritten=$false}
$plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'prepared-plan.json')
$plan | ConvertTo-Json -Depth 5
