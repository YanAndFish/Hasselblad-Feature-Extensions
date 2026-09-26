"""整体加固候选的客户端边界实验：不改发行包、不访问相机。"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'x1d/patch-distribution'
sys.path.insert(0, str(P))
import build
import licensing as lic
import release_signing


def run(args):
    return subprocess.run(list(map(str, args)), cwd=ROOT, capture_output=True,
                          timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    assert Path.cwd().resolve() == ROOT
    out = P / 'build/integrated-chain-candidate' / str(time.time_ns())
    source = out / 'source'
    source.mkdir(parents=True)
    for file in (P / 'native-client').glob('*.zig'):
        shutil.copyfile(file, source / file.name)
    verifier = (P / 'release_guard.zig').read_text(encoding='utf-8')
    verifier = verifier.split('\nfn run() !void {')[0]
    verifier = verifier.replace('fn verifySignature(', 'pub fn verifySignature(')
    verifier = verifier.replace('fn verifyClient(', 'pub fn verifyClient(')
    (source / 'release_verifier.zig').write_text(verifier, encoding='utf-8')
    public = lic.openssl('pkey', '-in', lic.PRIVATE / 'signing-key.pem', '-pubout', '-outform', 'DER')
    assert len(public) == 44 and public[:12] == bytes.fromhex('302a300506032b6570032100')
    (source / 'release_config.zig').write_text('pub const public_key: [32]u8 = .{' + ','.join(map(str, public[12:])) + '};\n')
    main_source = (source / 'native_installer_main.zig').read_text(encoding='utf-8')
    start = main_source.index('pub const Gate = struct {')
    end = main_source.index('\npub const Reporter = struct {', start)
    main_source = main_source[:start] + 'pub const Gate = @import("integrated_gate.zig").Gate;\n' + main_source[end:]
    main_source = main_source.replace('const hidden_process = @import("hidden_process.zig");\n', '')
    (source / 'native_installer_main.zig').write_text(main_source, encoding='utf-8')
    exe = out / 'installer-native-core.exe'
    compiled = run([build.ZIG, 'build-exe', source / 'native_installer_main.zig', '-O', 'ReleaseSafe', '-fstrip', '-femit-bin=' + str(exe)])
    assert compiled.returncode == 0, compiled.stderr.decode(errors='replace')
    with zipfile.ZipFile(P / 'build/candidate-r41/X1D-R41-安装包.zip') as archive:
        archive.extractall(out / 'fixture')
    package = out / 'fixture/X1D-R41-安装包'
    core = package / 'components/installer-native-core.exe'
    shutil.copyfile(exe, core)
    release_signing.protect_client(package)
    cases = []

    def check(name, passes):
        t = time.perf_counter()
        result = run([core, 'check-package'])
        assert (result.returncode == 0) == passes, (name, result.stdout, result.stderr)
        if passes:
            assert '没有连接相机'.encode() in result.stdout
        else:
            assert '发行签名校验失败'.encode() in result.stdout
        cases.append({'name': name, 'accepted': passes, 'seconds': time.perf_counter() - t})

    check('original_signed_candidate', True)
    guard = package / 'components/release-guard.exe'
    original_guard = guard.read_bytes()
    # 模拟上一轮攻击：外部程序伪造成功；测试只运行 check-package。
    stub = source / 'accept_all.zig'
    stub.write_text('const std=@import("std"); pub fn main() void { std.io.getStdOut().writer().writeAll("ARCHIVE_SHA256=' + hashlib.sha256((package / 'x1d-authorized-candidate.tgz').read_bytes()).hexdigest() + '\\n") catch {}; }')
    compiled = run([build.ZIG, 'build-exe', stub, '-O', 'ReleaseSafe', '-femit-bin=' + str(out / 'accept_all.exe')])
    assert compiled.returncode == 0, compiled.stderr.decode(errors='replace')
    guard.write_bytes((out / 'accept_all.exe').read_bytes())
    check('replacement_external_guard', False)
    manifest = package / 'client.manifest'
    original_manifest = manifest.read_bytes()
    lines = original_manifest.decode().splitlines()
    lines = [hashlib.sha256(guard.read_bytes()).hexdigest() + '  components/release-guard.exe' if line.endswith('  components/release-guard.exe') else line for line in lines]
    manifest.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    check('replacement_guard_rehashed_unsigned_manifest', False)
    manifest.write_bytes(original_manifest)
    guard.write_bytes(original_guard)
    payload = package / 'x1d-authorized-candidate.tgz'
    original_payload = payload.read_bytes()
    payload.write_bytes(original_payload[:-1] + bytes([original_payload[-1] ^ 1]))
    check('changed_payload', False)
    # 即使发行端给新清单签名，原载荷签名也不能被清单校验代替。
    release_signing.protect_client(package)
    check('signed_client_manifest_does_not_replace_payload_signature', False)
    payload.write_bytes(original_payload)
    manifest.write_bytes(original_manifest)
    # 还原原始客户端签名（前面的测试签名对应篡改后的清单）。
    release_signing.protect_client(package)
    signature = package / 'release.sig'
    original_signature = signature.read_bytes()
    signature.write_bytes(original_signature[:-1])
    release_signing.protect_client(package)
    check('signed_client_manifest_with_truncated_payload_signature', False)
    signature.write_bytes(original_signature)
    release_signing.protect_client(package)
    check('restored_signed_candidate', True)
    report = {'passed': True, 'hardwareRequests': 0, 'productionPackageChanged': False,
              'candidateOnly': True, 'cases': cases, 'binarySha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
              'sources': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in source.glob('*.zig')},
              'limitations': ['Not full-chain hardening', 'Not an independent black-box test', 'Does not prevent patching or replacing the complete native core']}
    (out / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(cases), 'hardwareRequests': 0, 'report': str(out / 'validation.json')}))


if __name__ == '__main__':
    main()
