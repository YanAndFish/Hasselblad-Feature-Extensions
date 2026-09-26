"""只构建固定 RAM 目录的 Linux 夹具，不上传、不运行、不连接相机。"""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "x1d/patch-distribution/native-camera-launch"
BASE = ROOT / "build/native-camera-launch"
OUT = BASE / "fixture-bootstrap"
ZIG = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def inspect(path):
    data = path.read_bytes()
    assert data[:7] == b"\x7fELF\x01\x01\x01"
    assert struct.unpack_from("<HH", data, 16) == (2, 40)
    flags = struct.unpack_from("<I", data, 36)[0]
    assert flags & 0xFF000000 == 0x05000000 and flags & 0x400
    offset = struct.unpack_from("<I", data, 28)[0]
    size, count = struct.unpack_from("<HH", data, 42)
    assert not ({2, 3} & {struct.unpack_from("<I", data, offset + i * size)[0] for i in range(count)})
    forbidden = [b"/opt/hbl-", b"/sys/bus/", b"/usr/bin/victory-gui", b"/usr/bin/msg2dbus", b"/usr/bin/configstore", b"/usr/bin/jpeg-daemon", b"/usr/bin/bodystate-daemon", b"/bin/sh", b"systemctl", b"dbus-send"]
    found = [text.decode() for text in forbidden if text in data]
    assert not found, ("Fixture includes a production execution or device path", found)
    # Static musl startup embeds /dev/null for its own secure-fd initialization.
    # The tested backend's guard stdio is explicitly the private fixture file.
    return {"sha256": sha(path), "size": len(data), "armStaticElf": True, "productionPathsAbsent": True, "libcRuntimeDevNullString": b"/dev/null" in data}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "fixture-build.json"
    manifest.write_text(json.dumps({"passed": False, "status": "building", "hardwareRequests": 0}, indent=2), encoding="utf-8")
    run([sys.executable, "-B", str(ROOT / "CodeTests/native_camera_launch_test.py")])
    production = json.loads((BASE / "validation.json").read_text(encoding="utf-8"))
    assert production["passed"]
    for name, digest in production["sources"].items():
        assert sha(ROOT / name) == digest
    binding = {"productionBinarySha256": production["binarySha256"], "sources": production["sources"]}
    binding_path = OUT / "source-binding.json"
    binding_path.write_text(json.dumps(binding, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    common = ["-O", "ReleaseSafe", "-fstrip", "-static", "-target", "arm-linux-musleabihf", "-mcpu", "cortex_a9", "-lc"]
    cache = ["--cache-dir", str(BASE / "zig-cache"), "--global-cache-dir", str(BASE / "zig-global-cache")]
    helper = OUT / "hbl-nla-fixture-helper"
    run([str(ZIG), "build-exe", str(SOURCE / "fixture_helper.zig"), *common, "-femit-bin=" + str(helper), *cache])
    helper_record = inspect(helper)
    embed = OUT / "fixture_embed.zig"
    embed.write_text('pub const helper = @embedFile("hbl-nla-fixture-helper");\npub const binding = @embedFile("source-binding.json");\n', encoding="utf-8")
    runner = OUT / "hbl-nla-fixture-runner"
    run([str(ZIG), "build-exe", *common, "--dep", "fixture_payload", "-Mroot=" + str(SOURCE / "fixture_runner.zig"), "-Mfixture_payload=" + str(embed), "-femit-bin=" + str(runner), *cache])
    runner_record = inspect(runner)
    report = {
        "passed": True,
        "builtOnly": True,
        "linuxCasesExecuted": 0,
        "hardwareRequests": 0,
        "cameraBusinessRequests": 0,
        "productionRolesExecuted": 0,
        "expectedCases": 30,
        "fixtureRoot": "/tmp/hbl-nla-bootstrap-fixture",
        "workDirectory": "/tmp/hbl-nla-bootstrap-fixture/work",
        "targetResultPath": "/tmp/hbl-nla-bootstrap-fixture/result.json",
        "guardStdioPath": "/tmp/hbl-nla-bootstrap-fixture/work/guard-stdio",
        "requiresRootUid": 0,
        "directoryMode": "0700",
        "acceptsArguments": False,
        "reusesExistingWork": False,
        "runner": runner_record,
        "helper": helper_record,
        "sourceBindingSha256": sha(binding_path),
        **binding,
    }
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: fixture ARM ELFs built and production paths absent; 30 Linux cases await parent-reviewed execution; hardwareRequests=0")


if __name__ == "__main__":
    main()
