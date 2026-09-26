$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$env:ZIG_LOCAL_CACHE_DIR=Join-Path $PSScriptRoot '.zig-cache'
$env:ZIG_GLOBAL_CACHE_DIR=Join-Path $PSScriptRoot '.zig-global'
$zig=Join-Path $repo '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
& $zig cc -g0 -target aarch64-linux-gnu -c (Join-Path $PSScriptRoot 'fastscan.S') -o (Join-Path $PSScriptRoot 'fastscan.o')
if ($LASTEXITCODE -ne 0) {throw 'Assembler failed'}
& py -3 -B (Join-Path $PSScriptRoot 'verify_candidate.py')
if ($LASTEXITCODE -ne 0) {throw 'Machine-code comparison failed'}
& py -3 -B (Join-Path $PSScriptRoot 'probe_protocol.py') --self-test
if ($LASTEXITCODE -ne 0) {throw 'Trace parser test failed'}
& py -3 -B (Join-Path $PSScriptRoot 'test_transaction.py')
if ($LASTEXITCODE -ne 0) {throw 'Restoration transaction test failed'}
