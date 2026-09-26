. (Join-Path $PSScriptRoot 'Usb.ps1')
function Read-U64([string]$ProcessId,[uint64]$Address) {
    $value=(Read-ReviewedUsb @("dd if=/proc/$ProcessId/mem bs=1 skip=$Address count=8 2>/dev/null | od -An -tu8")).Trim()
    if ($value -notmatch '^\d+$') {throw 'Cannot read pointer'}
    return [uint64]::Parse($value)
}
function Get-AfSnapshot {
    $spec=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'candidate.json') | ConvertFrom-Json
    $processId=(Read-ReviewedUsb @('pidof camera-service')).Trim()
    if ($processId -notmatch '^\d+$') {throw 'Expected exactly one camera-service'}
    $maps=(Read-ReviewedUsb @("grep libaaa.so /proc/$processId/maps")) -join "`n"
    $lines=@($maps -split "`n" | Where-Object {$_ -match '^([0-9a-f]+)-([0-9a-f]+) r-xp 00000000 .* /system/lib64/libaaa.so$'})
    if ($lines.Length -ne 1) {throw 'Unsupported ELF mapping'}
    $null=$lines[0] -match '^([0-9a-f]+)-([0-9a-f]+)'
    $begin=[Convert]::ToUInt64($Matches[1],16);$end=[Convert]::ToUInt64($Matches[2],16)
    # The official ELF starts at virtual address 0x1000, not zero.
    $bias=$begin-4096
    $address=$bias+[uint64]$spec.entry
    $length=[int]$spec.end-[int]$spec.entry
    if ($address -lt $begin -or $address+$length -gt $end) {throw 'Function outside executable mapping'}
    $start=(Read-ReviewedUsb @("awk '{print `$22}' /proc/$processId/stat")).Trim()
    if ($start -notmatch '^\d+$') {throw 'Process start-time missing'}
    $hashText=(Read-ReviewedUsb @("dd if=/proc/$processId/mem bs=1 skip=$address count=$length 2>/dev/null | sha256sum")).Trim()
    $liveHash=($hashText -split '\s+')[0]
    if ($liveHash -ne $spec.functionSha256) {throw 'Function is not original; no write is allowed'}
    $ctx=Read-U64 $processId ($bias+0xa2f2f0)
    # Confirm the lens context is within a readable/writable mapping before reading fields.
    $mapQuery='awk -v c='+$ctx+' ''$2~/rw-p/{split($1,a,"-");if(("0x"a[1])+0<=c&&("0x"a[2])+0>=c+256)print $1}'' /proc/'+$processId+'/maps'
    $allMaps=(Read-ReviewedUsb @($mapQuery)) -join "`n"
    $mapped=$false
    foreach ($line in ($allMaps -split "`n")) {
        if ($line.Trim() -match '^([0-9a-f]+)-([0-9a-f]+)$') {
            $lo=[Convert]::ToUInt64($Matches[1],16);$hi=[Convert]::ToUInt64($Matches[2],16)
            if ($ctx -ge $lo -and $ctx+0x100 -le $hi) {$mapped=$true}
        }
    }
    if (-not $mapped) {throw 'Lens context does not resolve into writable process memory'}
    $productAddress=$ctx+0x30
    $product=(Read-ReviewedUsb @("dd if=/proc/$processId/mem bs=1 skip=$productAddress count=4 2>/dev/null | od -An -tu4")).Trim()
    if ($product -ne '81470') {throw 'The connected lens is not the previously verified 55V product ID'}
    if ($spec.maximumVerifiedBoost) {
        $af=Read-U64 $processId ($bias+0xa2fa00)
        foreach($offset in @(0x9a0,0x9d0,0xa00)) {
            $bits=Read-U64 $processId ($af+$offset)
            $boost=[BitConverter]::ToDouble([BitConverter]::GetBytes($bits),0)
            if ([double]::IsNaN($boost) -or [double]::IsInfinity($boost) -or $boost -lt 0 -or $boost -gt $spec.maximumVerifiedBoost) {
                throw 'Runtime phase boost exceeds the verified candidate bound'
            }
        }
    }
    $endStart=(Read-ReviewedUsb @("awk '{print `$22}' /proc/$processId/stat")).Trim()
    if ($endStart -ne $start) {throw 'Camera service restarted while reading'}
    $boot=(Read-ReviewedUsb @('cat /proc/sys/kernel/random/boot_id')).Trim()
    if ($boot -notmatch '^[0-9a-f-]{36}$') {throw 'Boot identity unavailable'}
    [pscustomobject]@{firmware='4.2.0';model='first-generation X2D 100C';lens='55V';processId=$processId;startTime=$start;
        bias=$bias;address=$address;length=$length;functionHash=$liveHash;productAddress=$productAddress;
        bootId=$boot;deviceCodeWritten=$false;timestamp=[DateTimeOffset]::Now.ToString('o')}
}
