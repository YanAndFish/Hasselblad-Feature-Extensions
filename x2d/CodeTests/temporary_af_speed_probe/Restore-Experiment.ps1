. (Join-Path $PSScriptRoot 'Snapshot.ps1')
$path=Join-Path $PSScriptRoot 'prepared-plan.json'
$plan=Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
try {
    $s=Get-AfSnapshot
    if ($s.functionHash -eq $plan.original) {Write-Output 'ALREADY_ORIGINAL';exit 0}
} catch {
    # Only continue for the exact expected candidate, checked again on device.
    Write-Output 'Reading exact candidate state before recovery.'
}
$d=$plan.deviceRoot
if ($d -notmatch '^/tmp/afw-[a-f0-9]{8}$') {throw 'Invalid owned temporary directory'}
if ($plan.state -eq 'PREPARED_NOT_UPLOADED') {throw 'No experiment was uploaded; do not run a write-based recovery'}
$owner=(Read-ReviewedUsb @("cat $d/owner; true")).Trim()
if ($owner -notmatch '^\d+$') {throw 'Transaction owner is unknown; no concurrent recovery will be started'}
$alive=(Read-ReviewedUsb @("test -d /proc/$owner && echo ACTIVE || echo GONE")).Trim()
if ($alive -eq 'ACTIVE') {throw 'The automatic transaction may still be active. Wait for its deadline before recovery.'}
$check=(Read-ReviewedUsb @("sh -n $d/restore && echo READY")).Trim()
if ($check -ne 'READY') {throw 'Exact recovery script is unavailable'}
# Dispatch once only. A lost reply must not result in another write attempt.
$result=(Read-ReviewedUsb @("sh $d/restore >$d/recovery 2>&1; cat $d/recovery")) -join "`n"
$result | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'last-recovery.txt')
$verified=Get-AfSnapshot
if ($verified.functionHash -ne $plan.original) {throw 'Original function could not be verified'}
$plan.state='ORIGINAL_VERIFIED'
$plan | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $path
Write-Output 'RESTORED_AND_VERIFIED. Recovery did not touch system or lens firmware.'
