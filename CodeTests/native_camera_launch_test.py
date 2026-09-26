"""原生相机启动器离线验证；只执行注入式 Windows 测试，不执行生产角色。"""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "x1d/patch-distribution/native-camera-launch"
OUT = ROOT / "build/native-camera-launch"
ZIG = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(arguments):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "validation.json"
    report_path.write_text(json.dumps({"passed": False, "hardwareRequests": 0, "status": "running"}, indent=2), encoding="utf-8")
    cache = ["--cache-dir", str(OUT / "zig-cache"), "--global-cache-dir", str(OUT / "zig-global-cache")]
    result = run([str(ZIG), "test", str(SOURCE / "core_test.zig"), "-O", "ReleaseSafe", "-femit-bin=" + str(OUT / "core-test.exe"), *cache])
    (OUT / "core-tests.txt").write_text(result, encoding="utf-8")
    count = re.search(r"All (\d+) tests passed", result)
    assert count, result
    binary = OUT / "hbl-native-launch"
    run([str(ZIG), "build-exe", str(SOURCE / "main.zig"), "-O", "ReleaseSafe", "-fstrip", "-static", "-target", "arm-linux-musleabihf", "-mcpu", "cortex_a9", "-lc", "-femit-bin=" + str(binary), *cache])
    data = binary.read_bytes()
    assert data[:7] == b"\x7fELF\x01\x01\x01", "Expected little-endian ELF32"
    kind, machine = struct.unpack_from("<HH", data, 16)
    assert (kind, machine) == (2, 40), (kind, machine)
    flags = struct.unpack_from("<I", data, 36)[0]
    assert flags & 0xFF000000 == 0x05000000 and flags & 0x400, hex(flags)
    offset = struct.unpack_from("<I", data, 28)[0]
    size, number = struct.unpack_from("<HH", data, 42)
    segments = [struct.unpack_from("<I", data, offset + i * size)[0] for i in range(number)]
    assert 2 not in segments and 3 not in segments, "No dynamic section or interpreter is allowed"
    sources = sorted(SOURCE.glob("*.zig")) + sorted((ROOT / "CodeTests").glob("native_camera_launch*.py"))
    report = {
        "passed": True,
        "hardwareRequests": 0,
        "productionRolesExecuted": 0,
        "nativeCoreTests": int(count[1]),
        "binarySha256": sha(binary),
        "binarySize": len(data),
        "target": "arm-linux-musleabihf cortex_a9",
        "elfFlags": hex(flags),
        "staticElf": True,
        "linuxBackendRuntimeValidated": False,
        "cameraValidated": False,
        "packaged": False,
        "sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in sources},
        "referenceScripts": {p.relative_to(ROOT).as_posix(): sha(p) for p in [SOURCE.parent / "launch.sh", SOURCE.parent / "body.sh"]},
        "remainingScriptDispatch": [],
        "nativeBootstrapRequired": True,
        "behaviorChanges": ["enhanced exec failure falls back once", "guard parent timeout 75 seconds", "enabled marker capped at 32 bytes", "guard must be a regular non-symlink file", "guard output replaced by bounded fixed status codes"],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {count[1]} native model tests; ARM EABI5 hard-float static ELF; hardwareRequests=0")


if __name__ == "__main__":
    main()
