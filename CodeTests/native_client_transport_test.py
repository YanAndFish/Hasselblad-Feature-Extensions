"""X1D 原生传输离线测试；不导入安装器、不实例化 WinUSB、不枚举设备。"""
from __future__ import annotations

import ast
import binascii
import hashlib
import io
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "x1d/patch-distribution/native-client"
OUT = ROOT / "build/native-client"
ZIG = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"
REFERENCE = ROOT / "x1d/patch-distribution/usb_transport.py"


def run(arguments: list[str], *, input_bytes: bytes | None = None, check: bool = True):
    result = subprocess.run(arguments, cwd=ROOT, input=input_bytes, capture_output=True, timeout=180)
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace") + result.stdout.decode("utf-8", "replace"))
    return result


def reference_contract():
    # 只提取三个纯函数；从结构上避免导入 read_usb_link_once 或安装器。
    tree = ast.parse(REFERENCE.read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ("crc", "request", "response")]
    assert [node.name for node in functions] == ["crc", "request", "response"]
    namespace = {"binascii": binascii, "struct": struct}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(REFERENCE), "exec"), namespace)
    return namespace


def make_reply(token: int, text: bytes = b"ok", *, kind: int = 52, operation: int = 0, status: int = 0) -> bytes:
    assert len(text) <= 232
    packet = bytearray(512)
    packet[:5] = bytes.fromhex("09000508fc")
    struct.pack_into("<5I", packet, 5, kind, operation, token, 0, status)
    packet[25:25 + len(text)] = text
    struct.pack_into("<I", packet, 17, binascii.crc_hqx(packet[21:257], 0))
    return bytes(packet)


def expected(reference, operation: int, token: int, payload: bytes) -> str:
    if operation == 1:
        try:
            return "request " + reference["request"](payload.decode("latin1"), token).hex()
        except (ValueError, UnicodeError):
            return "error CommandBoundary"
    if operation == 2:
        try:
            value = reference["response"](payload, token)
            return "stale" if value is None else "matched " + value.encode("ascii").hex()
        except UnicodeError:
            return "error USB_ASCII"
        except ValueError:
            return "error USB_FORMAT" if len(payload) != 512 or payload[:5] != bytes.fromhex("09000508fc") else "error USB_REPLY"
    return "crc " + str(reference["crc"](payload))


def corpus() -> list[tuple[int, int, bytes]]:
    cases: list[tuple[int, int, bytes]] = []
    rng = random.Random(20260922)
    for length in range(235):
        cases.append((1, rng.randrange(0x100000000), b"x" * length))
    for payload in [b"offline-fixture", b"x\nx", b"x\0x", b"\r", b"\t\v\f", b"\xff", b"\x80", b"\x7f"]:
        for token in [0, 1, 0x80000000, 0xffffffff]:
            cases.append((1, token, payload))
    for _ in range(400):
        cases.append((1, rng.randrange(0x100000000), bytes(rng.randrange(256) for _ in range(rng.randrange(260)))))
    base = make_reply(7)
    for length in range(512):
        cases.append((2, 7, base[:length]))
    for length in [513, 1024, 65536]:
        cases.append((2, 7, base + bytes(length - len(base))))
    for token in [0, 1, 7, 0x80000000, 0xffffffff]:
        for text in [b"", b"ok\n", b" \t\x1cok\x1f\r\n", b"x" * 232, b"a\0\xff", bytes(range(1, 128)), b"\x80"]:
            cases.append((2, token, make_reply(token, text)))
        for kind, operation, status in [(53, 0, 0), (52, 1, 0), (52, 0, 1), (52, 0, 0xffffffff)]:
            frame = make_reply(token, kind=kind, operation=operation, status=status)
            cases.extend([(2, token, frame), (2, token ^ 1, frame)])
    for offset in range(512):
        mutated = bytearray(base)
        mutated[offset] ^= 0x80
        cases.extend([(2, 7, bytes(mutated)), (2, 8, bytes(mutated))])
    for _ in range(400):
        token = rng.randrange(0x100000000)
        text = bytes(rng.randrange(1, 128) for _ in range(rng.randrange(233)))
        frame = make_reply(token, text)
        cases.append((2, token, frame))
        cases.append((2, token ^ 1, frame))
    for length in [0, 1, 2, 3, 31, 128, 232, 236, 256, 512, 65536]:
        cases.append((3, 0, bytes(rng.randrange(256) for _ in range(length))))
    cases.append((3, 0, b"123456789"))
    return cases


def archive_fixtures():
    baseline = {
        "install.sh": b"#!/bin/sh\nexit 0\n",
        "remove.sh": b"#!/bin/sh\nprintf 'offline-removal\\n'\n",
        "files/authorization-guard": b"offline-guard-fixture",
        "files/authorization.bin": b"offline-authorization-fixture",
        "files/manifest.sha256": b"offline-manifest-fixture",
        "files/payload": b"\x00\x01\xff" * 103,
    }

    def make(case):
        files = dict(baseline)
        if case == "missing-remove":
            del files["remove.sh"]
        if case == "empty-remove":
            files["remove.sh"] = b""
        if case in ["traversal", "absolute", "nested", "backslash", "dot"]:
            name = {"traversal": "files/../payload", "absolute": "/tmp/payload", "nested": "files/d/payload", "backslash": "files\\payload", "dot": "./payload"}[case]
            files[name] = files.pop("files/payload")
        manifest = "".join(hashlib.sha256(value).hexdigest() + "  " + name + "\n" for name, value in sorted(files.items()))
        if case == "duplicate-check":
            manifest += manifest.splitlines()[0] + "\n"
        if case == "missing-check":
            manifest = "\n".join(manifest.splitlines()[:-1]) + "\n"
        if case == "unknown-check":
            manifest += "0" * 64 + "  unknown\n"
        if case == "wrong-digest":
            manifest = "0" * 64 + manifest[64:]
        if case == "crlf-manifest":
            manifest = manifest.replace("\n", "\r\n")
        files["package.sha256"] = manifest.encode("ascii")
        if case == "changed-payload":
            files["files/payload"] += b"changed"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT, pax_headers={"comment": "offline"} if case == "global-pax" else None) as tar:
            for name, value in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(value)
                member.mtime = 123.25 if case == "pax-mtime" else 0
                if name == "files/payload":
                    if case in ["symlink", "hardlink", "directory"]:
                        member.type = {"symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE, "directory": tarfile.DIRTYPE}[case]
                        member.linkname = "install.sh"
                    if case == "pax-path":
                        member.name = "files/short"
                        member.pax_headers = {"path": "files/payload"}
                tar.addfile(member, io.BytesIO(value))
                if case == "duplicate-name" and name == "files/payload":
                    tar.addfile(member, io.BytesIO(value))
        return buffer.getvalue()

    normal = make("normal")
    cases = [(case, make(case), case in ["normal", "pax-mtime", "empty-remove", "crlf-manifest"], case in ["pax-path", "global-pax"]) for case in [
        "normal", "pax-mtime", "empty-remove", "crlf-manifest", "missing-remove", "traversal", "absolute", "nested", "backslash", "dot",
        "duplicate-check", "missing-check", "unknown-check", "wrong-digest", "changed-payload", "symlink", "hardlink", "directory", "duplicate-name", "pax-path", "global-pax",
    ]]
    for length in [0, 1, 10, len(normal) // 2, len(normal) - 8, len(normal) - 1]:
        cases.append(("gzip-truncated-" + str(length), normal[:length], False, True))
    return cases


def transaction_elf_fixture():
    """结构化人工 ELF，仅测试包解析，不是可执行产物。"""
    data = bytearray(88)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HHI', data, 16, 2, 40, 1)
    struct.pack_into('<I', data, 28, 52)
    struct.pack_into('<I', data, 36, 0x05000400)
    struct.pack_into('<HHHHHH', data, 40, 52, 32, 1, 0, 0, 0)
    struct.pack_into('<IIIIIIII', data, 52, 1, 0, 0x10000, 0x10000, 88, 88, 5, 4096)
    return bytes(data)


def native_archive_fixtures():
    elf = transaction_elf_fixture()
    names = ['native-valid', 'mixed-install', 'mixed-remove', 'missing-marker', 'missing-elf',
             'wrong-marker', 'empty-elf', 'bad-magic', 'wrong-class', 'wrong-machine',
             'soft-float', 'elf-dynamic', 'elf-interpreter', 'no-executable-load',
             'truncated-phdr', 'oversize-phdr', 'no-phdr', 'native-wrong-hash']
    for case in names:
        files = {'transaction-profile': b'native-v1\n', 'camera-transaction': elf,
                 'files/authorization-guard': b'fixture', 'files/authorization.bin': b'fixture',
                 'files/manifest.sha256': b'fixture'}
        if case.startswith('mixed-'): files[case[6:] + '.sh'] = b'#!/bin/sh\nexit 0\n'
        if case == 'missing-marker': del files['transaction-profile']
        if case == 'missing-elf': del files['camera-transaction']
        if case == 'wrong-marker': files['transaction-profile'] = b'native-v2\n'
        if case == 'empty-elf': files['camera-transaction'] = b''
        mutations = {'bad-magic': (0, b'X'), 'wrong-class': (4, b'\x02'),
                     'wrong-machine': (18, struct.pack('<H', 62)), 'soft-float': (36, struct.pack('<I', 0x05000200)),
                     'elf-dynamic': (52, struct.pack('<I', 2)), 'elf-interpreter': (52, struct.pack('<I', 3)),
                     'no-executable-load': (76, struct.pack('<I', 4)),
                     'truncated-phdr': (28, struct.pack('<I', 87)), 'oversize-phdr': (42, struct.pack('<H', 0xffff)),
                     'no-phdr': (44, b'\0\0')}
        if case in mutations:
            at, value = mutations[case]
            payload = bytearray(elf)
            payload[at:at + len(value)] = value
            files['camera-transaction'] = bytes(payload)
        files['package.sha256'] = ''.join(hashlib.sha256(value).hexdigest() + '  ' + name + '\n'
                                          for name, value in sorted(files.items())).encode()
        if case == 'native-wrong-hash': files['camera-transaction'] += b'changed'
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as tar:
            for name, value in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(value)
                tar.addfile(member, io.BytesIO(value))
        yield case, output.getvalue(), case == 'native-valid', hashlib.sha256(elf).hexdigest()


def check_archives(probe: Path):
    installer = ROOT / "x1d/patch-distribution/installer.py"
    tree = ast.parse(installer.read_text(encoding="utf-8"))
    function = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "validate_archive"]
    assert len(function) == 1
    scope = {"tarfile": tarfile, "io": io, "hashlib": hashlib}
    exec(compile(ast.Module(body=function, type_ignores=[]), str(installer), "exec"), scope)
    report = []
    for case, data, should_pass, stricter in archive_fixtures():
        reference_ok = False
        removal = b""
        try:
            removal = scope["validate_archive"](data)
            reference_ok = True
        except (ValueError, tarfile.TarError, OSError, EOFError):
            pass
        native = run([str(probe), "offline-archive-contract"], input_bytes=data, check=False)
        native_ok = native.returncode == 0
        assert native_ok == should_pass, (case, native.returncode, native.stdout, native.stderr)
        if not stricter:
            assert native_ok == reference_ok, (case, native_ok, reference_ok)
        if should_pass:
            assert native.stdout.decode().split()[1] == hashlib.sha256(removal).hexdigest(), case
        report.append({"case": case, "nativeAccepted": native_ok, "referenceAccepted": reference_ok, "allowedStricterRejection": stricter})
    for case, data, should_pass, digest in native_archive_fixtures():
        result = run([str(probe), 'offline-archive-contract'], input_bytes=data, check=False)
        assert (result.returncode == 0) == should_pass, (case, result.stdout, result.stderr)
        if should_pass: assert result.stdout.decode().split()[1] == digest
        report.append({'case': case, 'nativeAccepted': result.returncode == 0, 'profile': 'native-v1', 'hardwareRequests': 0})
    return report


def native_fixture(native_transaction=False) -> bytes:
    manifest = b"offline-manifest-fixture"
    blob = b"HBLWL001" + hashlib.sha256(manifest).digest() + struct.pack("<I", 1)
    blob += hashlib.sha256(b"HBL-X1D-1250-SERIAL-V1\0TEST000001").digest() + bytes(64)
    files = {
        "install.sh": b"#!/bin/sh\nexit 0\n",
        "remove.sh": b"#!/bin/sh\nprintf 'offline-removal\\n'\n",
        "files/authorization-guard": b"offline-guard-fixture",
        "files/authorization.bin": blob,
        "files/manifest.sha256": manifest,
        "files/baseline.sha256": hashlib.sha256(b"offline-firmware").hexdigest().encode() + b"  /usr/bin/configstore\n",
        "files/payload": bytes(range(256)) * 4,
    }
    if native_transaction:
        del files['install.sh'], files['remove.sh']
        files['transaction-profile'] = b'native-v1\n'
        files['camera-transaction'] = transaction_elf_fixture()
    files["package.sha256"] = "".join(hashlib.sha256(content).hexdigest() + "  " + name + "\n" for name, content in sorted(files.items())).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 123.25
            tar.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def main() -> None:
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError("必须在当前 Hasselblad 工作区根目录执行")
    if not ZIG.is_file():
        raise RuntimeError("缺少仓库固定 Zig 0.13.0 工具链")
    OUT.mkdir(parents=True, exist_ok=True)
    version = run([str(ZIG), "version"]).stdout.decode().strip()
    assert version == "0.13.0", version
    cache = ["--cache-dir", str(OUT / "cache"), "--global-cache-dir", str(OUT / "global-cache")]
    probe = OUT / "x1d-native-offline.exe"
    build = [str(ZIG), "build-exe", str(SOURCE / "offline_probe.zig"), "-O", "ReleaseSafe", "-fstrip", "-femit-bin=" + str(probe), *cache]
    native_tests = [str(ZIG), "test", str(SOURCE / "offline_test.zig"), "-O", "Debug", "-femit-bin=" + str(OUT / "native-tests.exe"), *cache]
    run(build)
    native = run(native_tests)
    (OUT / "native-tests.txt").write_bytes(native.stdout + native.stderr)
    selftest = json.loads(run([str(probe), "offline-selftest"]).stdout)
    assert selftest == {"passed": True, "hardwareRequests": 0, "kind": "offline-contract"}
    cases = corpus()
    input_bytes = b"".join(struct.pack("<BII", operation, token, len(payload)) + payload for operation, token, payload in cases)
    reference = reference_contract()
    actual = run([str(probe), "offline-contract"], input_bytes=input_bytes).stdout.decode("ascii").splitlines()
    assert len(actual) == len(cases), (len(actual), len(cases))
    for index, (operation, token, payload) in enumerate(cases):
        wanted = expected(reference, operation, token, payload)
        assert actual[index] == wanted, f"case {index}: op={operation}, bytes={len(payload)}, expected={wanted[:80]}, actual={actual[index][:80]}"
    cli_checks = 0
    for arguments in [[], ["command", "offline-fixture"], ["--run-authorized-once"], ["install"], ["offline-contract", "extra"]]:
        assert run([str(probe), *arguments], check=False).returncode == 2
        cli_checks += 1
    for malformed in [b"\x01", struct.pack("<BII", 1, 1, 2) + b"x", struct.pack("<BII", 4, 1, 0), struct.pack("<BII", 1, 1, 65537)]:
        assert run([str(probe), "offline-contract"], input_bytes=malformed, check=False).returncode == 2
        cli_checks += 1
    # 离线探针在构建依赖上不含后端，因此不能打开硬件。
    artifact = probe.read_bytes()
    assert artifact[:2] == b"MZ"
    for forbidden in [b"WinUsb_", b"SetupDi", b"winusb.dll", b"setupapi.dll"]:
        assert forbidden.lower() not in artifact.lower(), forbidden
    native_output = (native.stdout + native.stderr).decode("utf-8", "replace")
    methods = re.search(r"All (\d+) tests passed\.", native_output)
    assert methods, native_output
    native_methods = int(methods[1])
    archive_cases = check_archives(probe)
    # 固定 awk 解码器仍须与旧客户端逐字节一致；测试仅解析字面量。
    installer_tree = ast.parse((ROOT / "x1d/patch-distribution/installer.py").read_text(encoding="utf-8"))
    python_decoder = next(ast.literal_eval(node.value) for node in installer_tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "DECODER" for target in node.targets))
    zig_literal = re.search(r'pub const decoder = (".*");', (SOURCE / "upload.zig").read_text(encoding="utf-8"))[1]
    assert ast.literal_eval(zig_literal) == python_decoder
    tested_modules = ["protocol.zig", "interface.zig", "transport.zig", "winusb.zig", "offline_probe.zig", "offline_test.zig", "archive.zig", "state_machine.zig", "upload.zig"]
    source_paths = [REFERENCE, ROOT / "x1d/tools/read_usb_link_once.py", ROOT / "x1d/patch-distribution/installer.py", Path(__file__), *(SOURCE / name for name in tested_modules)]
    report = {
        "passed": True,
        "scope": "X1D-50c 官方 1.25.0 现有维护通道的离线原生迁移",
        "zigVersion": version,
        "nativeTestMethods": native_methods,
        "differentialCases": len(cases),
        "differentialByOperation": {str(op): sum(1 for row in cases if row[0] == op) for op in [1, 2, 3]},
        "invalidCliAndCorpusChecks": cli_checks,
        "archiveCases": archive_cases,
        "archiveCaseCount": len(archive_cases),
        "uploadDecoderMatchesPython": True,
        "hardwareRequests": 0,
        "nativeSystemBackendExecuted": False,
        "installerIntegrated": False,
        "backendCompileCheck": "std.testing.refAllDecls(SystemApi / NativeWinUsb)，仅编译，不调用真实设备方法",
        "offlineProbeSha256": hashlib.sha256(artifact).hexdigest(),
        "sourceSha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
        "buildCommands": [build, native_tests],
    }
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixtures = OUT / "fixtures"
    fixtures.mkdir(exist_ok=True)
    (fixtures / "ops-valid.tgz").write_bytes(native_fixture())
    (fixtures / "ops-native.tgz").write_bytes(native_fixture(native_transaction=True))
    native_core = OUT / "installer-native-core.exe"
    core_build = [str(ZIG), "build-exe", str(SOURCE / "native_installer_main.zig"), "-O", "ReleaseSafe", "-fstrip", "-femit-bin=" + str(native_core), *cache]
    ops_tests = [str(ZIG), "test", str(SOURCE / "offline_installer_test.zig"), "-O", "Debug", "-femit-bin=" + str(OUT / "native-installer-tests.exe"), *cache]
    run(core_build)
    operations = run(ops_tests)
    operations_output = (operations.stdout + operations.stderr).decode("utf-8", "replace")
    (OUT / "native-installer-tests.txt").write_text(operations_output, encoding="utf-8")
    operations_count = re.search(r"All (\d+) tests passed\.", operations_output)
    assert operations_count, operations_output
    for arguments in [[], ["command", "offline-fixture"], ["--run-authorized-once"], ["detect", "unexpected"]]:
        result = run([str(native_core), *arguments], check=False)
        assert result.returncode == 1 and "仅支持".encode() in result.stdout
    installer_report = {
        "passed": True,
        "hardwareRequests": 0,
        "binarySha256": hashlib.sha256(native_core.read_bytes()).hexdigest(),
        "sources": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(SOURCE.glob("*.zig"))},
        "opsTestMethods": int(operations_count[1]),
        "transportTestMethods": native_methods,
        "simulatedActions": ["check-package", "detect", "install", "remove", "diagnose"],
        "simulatedBoundaries": ["client/release/digest gates", "power before and after upload", "bounded cleanup", "upload sha256", "single dispatch", "unknown exit no retry", "idempotent completion marker", "exit75 rejection", "readonly diagnostic allowlist", "serial redaction"],
        "actualSignedPackageEntryPointTested": False,
        "actualWindowsUsbBackendExecuted": False,
        "buildCommands": [core_build, ops_tests],
    }
    (OUT / "native-installer-validation.json").write_text(json.dumps(installer_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["passed", "nativeTestMethods", "differentialCases", "archiveCaseCount", "invalidCliAndCorpusChecks", "hardwareRequests", "installerIntegrated"]}, ensure_ascii=False))
    print(json.dumps({"nativeInstallerPassed": True, "opsTestMethods": int(operations_count[1]), "hardwareRequests": 0, "binarySha256": installer_report["binarySha256"]}))


if __name__ == "__main__":
    main()
