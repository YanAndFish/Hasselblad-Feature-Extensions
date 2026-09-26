"""构建 GFP2 单段模拟与分段候选；不连接设备、不更改 AF 文件。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / "build"
CACHE = ROOT / ".research-cache/x1d-1.25.0"

SPLIT_LAYOUT = """ENTRY(farm_sensor_probe_hook)
SECTIONS {
  . = 0x002b26a0;
  .text : { *(.text.farm_sensor_probe_after_start) }
  ASSERT(SIZEOF(.text) <= 0x160, "head exceeds 352-byte padding")
  . = 0x002b3e80;
  .hook : { *(.text.farm_sensor_probe_hook) *(.text.read_time) *(.text*) }
  .data : ALIGN(4) { *(.data.farm_sensor_probe_record) }
  ASSERT(SIZEOF(.data) == 88, "wrong GFP2 record size")
  ASSERT(ADDR(.data) + SIZEOF(.data) <= 0x002b4000, "tail reaches MMU table")
  /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
"""


def build():
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError("workspace mismatch")
    env = dict(os.environ)
    for key, name in (("ZIG_GLOBAL_CACHE_DIR", "zig-global-cache"),
                      ("ZIG_LOCAL_CACHE_DIR", "zig-local-cache"), ("TEMP", "probe-tmp"), ("TMP", "probe-tmp")):
        path = OUT / name
        path.mkdir(exist_ok=True)
        env[key] = str(path)
    split_ld = OUT / "farm-sensor-split.ld"
    split_ld.write_text(SPLIT_LAYOUT, encoding="ascii")
    compiler = CACHE / "toolchain/zig-windows-x86_64-0.13.0/zig.exe"
    flags = [str(compiler), "cc", "-target", "arm-freestanding-eabi", "-mcpu=cortex_a9",
             "-mfloat-abi=soft", "-marm", "-Os", "-g", "-fno-lto", "-ffunction-sections",
             "-fdata-sections", "-ffreestanding", "-fno-stack-protector", "-fno-unwind-tables",
             "-fno-asynchronous-unwind-tables", "-fPIC", "-Wl,--no-undefined", "-nostdlib",
             "-Wl,--build-id=none", "-Wall", "-Wextra"]
    definitions = (
        ("farm-sensor-probe", "farm_sensor_probe_after_start", False, "farm-sensor-probe.ld"),
        ("farm-sensor-hook-simulation", "farm_sensor_probe_hook", True, "farm-sensor-hook-simulation.ld"),
        ("farm-sensor-split", "farm_sensor_probe_hook", True, "farm-sensor-split.ld"),
    )
    commands = []
    for name, entry, hook, layout in definitions:
        sources = [HERE / "native/farm_sensor_probe.c"]
        if hook:
            sources.append(HERE / "native/farm_sensor_probe_hook.S")
        command = flags + ["-Wl,-e," + entry, "-Wl,-T," + str(OUT / layout)] + [str(p) for p in sources] + ["-o", str(OUT / (name + ".elf"))]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
        commands.append({"command": command, "exit": result.returncode, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(result.stderr)
    sys.path.insert(0, str(ROOT / "x1d/tools"))
    from binary import ArmElf
    artifacts = {}
    for name, _, _, _ in definitions:
        path = OUT / (name + ".elf")
        elf = ArmElf(path.read_bytes())
        if any(s["sh_type"] in ("SHT_REL", "SHT_RELA") and s["sh_size"] for s in elf.sections):
            raise RuntimeError("unexpected runtime relocation")
        artifacts[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "entry": elf.elf.header["e_entry"],
                           "sections": {s.name: {"address": s["sh_addr"], "bytes": s["sh_size"]}
                                        for s in elf.sections if s["sh_flags"] & 2 and s["sh_size"]}}
    split = ArmElf((OUT / "farm-sensor-split.elf").read_bytes())
    segments = {}
    for name, sections in (("head", (".text",)), ("tail", (".hook", ".data"))):
        parts = [split.elf.get_section_by_name(s) for s in sections]
        start, end = parts[0]["sh_addr"], parts[-1]["sh_addr"] + parts[-1]["sh_size"]
        payload = bytearray(end - start)
        for part in parts:
            offset = part["sh_addr"] - start
            payload[offset:offset + part["sh_size"]] = part.data()
        if len(payload) % 4:
            raise RuntimeError("unaligned split payload")
        filename = "farm-sensor-split-" + name + ".bin"
        (OUT / filename).write_bytes(payload)
        segments[name] = {"address": start, "end_exclusive": end, "bytes": len(payload),
                          "file": filename, "sha256": hashlib.sha256(payload).hexdigest()}
    report = {"status": "compiled split candidate; target installation and physical timing unverified",
              "source_hashes": {p: hashlib.sha256((HERE / p).read_bytes()).hexdigest() for p in (
                  "native/farm_sensor_probe.c", "native/farm_sensor_probe_hook.S")},
              "artifacts": artifacts, "segments": segments, "commands": commands,
              "record_address": split.elf.get_section_by_name(".data")["sh_addr"],
              "model_tests_run": False, "camera_installed": False, "hardware_requests": 0}
    (OUT / "farm-sensor-split-build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
