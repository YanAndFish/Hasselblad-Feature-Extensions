"""在当前项目内编译、运行正式无线业务的纯离线状态机测试。"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ZIG = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"
MODULE = HERE.parent
REPORT = HERE / "formal_policy_output/validation.json"


def source_hashes() -> dict[str, str]:
    sources = [HERE / name for name in ("formal_policy.test.cpp", "formal_policy_adapter.test.cpp",
               "formal_policy_build.py", "formal_radio_fake_platform.h")]
    pending = [MODULE / "native" / name for name in ("formal_policy.h", "formal_worker.cpp", "formal_bridge.h", "formal_radio.h")]
    seen = set(sources)
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        for name in re.findall(r'^\s*#include\s+"([^"\r\n]+)"', path.read_text(encoding="utf-8"), re.MULTILINE):
            dependency = (path.parent / name).resolve()
            if dependency.is_file():
                pending.append(dependency)
    return {str(p.relative_to(MODULE)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(seen)}


def save_report(value: dict) -> None:
    REPORT.parent.mkdir(exist_ok=True)
    temporary = REPORT.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(REPORT)


def main() -> None:
    if not ZIG.is_file():
        raise SystemExit("缺少项目现有 Zig 工具链；不下载或改装工具。")
    before = source_hashes()
    report = {"passed": False, "hardwareRequests": 0, "installed": False,
              "physicalTimingVerified": False, "sourceHashes": before, "tests": []}
    save_report(report)
    with tempfile.TemporaryDirectory(prefix="formal_policy_", dir=HERE) as directory:
        output = Path(directory).resolve()
        if not output.is_relative_to(HERE):
            raise SystemExit("测试输出必须留在当前模块 CodeTests 内。")
        environment = os.environ.copy()
        environment["ZIG_GLOBAL_CACHE_DIR"] = str(output / "global-cache")
        environment["ZIG_LOCAL_CACHE_DIR"] = str(output / "local-cache")
        for name in ("formal_policy.test.cpp", "formal_policy_adapter.test.cpp"):
            executable = output / (name + ".exe")
            command = [str(ZIG), "c++", "-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror",
                       "-I", str(HERE), str(HERE / name), "-o", str(executable)]
            compiled = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True)
            if compiled.returncode:
                raise SystemExit(compiled.stdout + compiled.stderr)
            result = subprocess.run([str(executable)], cwd=ROOT, env=environment, text=True, capture_output=True)
            print(result.stdout, end="")
            if result.returncode:
                raise SystemExit(result.stderr or result.stdout)
            counts = re.findall(r"checks=(\d+) hardware-requests=0", result.stdout)
            if len(counts) != 1:
                raise SystemExit("测试没有返回唯一的明确通过计数。")
            report["tests"].append({"name": name, "passed": True, "checks": int(counts[0]),
                                    "stdout": result.stdout.strip()})
        if before != source_hashes():
            raise SystemExit("测试期间源码变化，拒绝绑定过期通过结果。")
        report.update(passed=True, checks=sum(test["checks"] for test in report["tests"]), randomizedSteps=10000,
                      installationGate={"workerInitiallyLocked": True, "oldEnableRequestsReplayed": False,
                                        "enableRequest": "/tmp/hbl-wireless-flash/formal-enable.ready",
                                        "confirmation": "/tmp/hbl-wireless-flash/formal-enable.confirmed",
                                        "confirmationOwner": "native/formal_worker.cpp",
                                        "confirmationRequiresUnlockedAndNotStopped": True,
                                        "stopHasPriority": True})
        save_report(report)


if __name__ == "__main__":
    main()
