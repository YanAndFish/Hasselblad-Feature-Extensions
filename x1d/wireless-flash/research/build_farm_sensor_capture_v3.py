"""构建 GFP3 两点观察的电脑模拟产物；不连接设备，不输出装机包。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / "build/farm-sensor-capture-v3"


def build():
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError("workspace mismatch")
    OUT.mkdir(exist_ok=True)
    env = dict(os.environ)
    for key, name in (("ZIG_GLOBAL_CACHE_DIR", "global-cache"), ("ZIG_LOCAL_CACHE_DIR", "local-cache"),
                      ("TEMP", "tmp"), ("TMP", "tmp")):
        path = OUT / name
        path.mkdir(exist_ok=True)
        env[key] = str(path)
    layout = OUT / "simulation.ld"
    layout.write_text("""ENTRY(farm_capture_start_hook)
SECTIONS {
 . = 0x01000000;
 .text : { KEEP(*(.text.farm_capture_start_hook)) KEEP(*(.text.farm_capture_encoding_hook)) *(.text*) }
 . = 0x01002000;
 .data : { *(.data.farm_capture_record) }
 ASSERT(SIZEOF(.data) == 116, "wrong GFP3 size")
 /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
""", encoding="ascii")
    compiler = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"
    sources = [HERE / "native/farm_sensor_capture_v3.c", HERE / "native/farm_sensor_capture_v3_hooks.S"]
    destination = OUT / "simulation.elf"
    command = [str(compiler), "cc", "-target", "arm-freestanding-eabi", "-mcpu=cortex_a9",
               "-mfloat-abi=soft", "-marm", "-Os", "-g", "-fno-lto", "-ffunction-sections",
               "-fdata-sections", "-ffreestanding", "-fno-stack-protector", "-fno-unwind-tables",
               "-fno-asynchronous-unwind-tables", "-fPIC", "-Wl,--no-undefined", "-nostdlib",
               "-Wl,--build-id=none", "-Wall", "-Wextra", "-Wl,-e,farm_capture_start_hook", "-Wl,-T," + str(layout),
               *map(str, sources), "-o", str(destination)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr)
    sys.path.insert(0, str(ROOT / "x1d/tools"))
    from binary import ArmElf
    elf = ArmElf(destination.read_bytes())
    data_section = elf.elf.get_section_by_name(".data")
    if data_section is None or data_section["sh_size"] != 116:
        raise RuntimeError("wrong GFP3 data size: " + str(None if data_section is None else data_section["sh_size"]))
    if any(s["sh_type"] in ("SHT_REL", "SHT_RELA") and s["sh_size"] for s in elf.sections):
        raise RuntimeError("runtime relocations")
    report = {"status": "offline simulation only; no target layout or loader",
              "command": command, "compile_exit": result.returncode, "compiler_stderr": result.stderr,
              "elf_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
              "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "sections": {s.name: {"address": s["sh_addr"], "bytes": s["sh_size"]}
                           for s in elf.sections if s["sh_flags"] & 2 and s["sh_size"]},
              "hardware_requests": 0, "installed": False, "model_tests_run": False,
              "physical_integration_event_verified": False}
    (OUT / "build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def build_target(simulation_report):
    """只为手动重启后的原厂空白区生成候选；不与驻留 AF 同时装载。"""
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError("workspace mismatch")
    layout = OUT / "target.ld"
    layout.write_text("""ENTRY(farm_capture_start_hook)
SECTIONS {
 . = 0x002b2880;
 .text : { KEEP(*(.text.farm_capture_start_hook)) KEEP(*(.text.farm_capture_encoding_hook)) *(.text*) }
 .data : ALIGN(4) { *(.data.farm_capture_record) }
 ASSERT(SIZEOF(.data) == 116, "wrong GFP3 size")
 ASSERT(ADDR(.data) + SIZEOF(.data) <= 0x002b4000, "target reaches MMU table")
 /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
""", encoding="ascii")
    destination = OUT / "target.elf"
    command = ["-Wl,-T," + str(layout) if arg.startswith("-Wl,-T,") else arg
               for arg in simulation_report["command"]]
    command[-1] = str(destination)
    env = dict(os.environ)
    for key, name in (("ZIG_GLOBAL_CACHE_DIR", "global-cache"), ("ZIG_LOCAL_CACHE_DIR", "local-cache"),
                      ("TEMP", "tmp"), ("TMP", "tmp")):
        env[key] = str(OUT / name)
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr)
    from binary import ArmElf
    elf = ArmElf(destination.read_bytes())
    sections = [elf.elf.get_section_by_name(name) for name in (".text", ".data")]
    start = sections[0]["sh_addr"]
    end = sections[-1]["sh_addr"] + sections[-1]["sh_size"]
    if start != 0x2B2880 or sections[-1]["sh_size"] != 116 or end > 0x2B4000:
        raise RuntimeError("unexpected target layout")
    if any(s["sh_type"] in ("SHT_REL", "SHT_RELA") and s["sh_size"] for s in elf.sections):
        raise RuntimeError("runtime relocations")
    payload = bytearray(end - start)
    for section in sections:
        off = section["sh_addr"] - start
        payload[off:off + section["sh_size"]] = section.data()
    symbols = {symbol.name: symbol["st_value"] for section in elf.sections
               if section["sh_type"] == "SHT_SYMTAB" for symbol in section.iter_symbols()}
    payload_path = OUT / "target.bin"
    payload_path.write_bytes(payload)
    report = {"status": "offline target candidate; requires manual restart and original AF guards",
              "command": command, "compile_exit": result.returncode, "compiler_stderr": result.stderr,
              "sources": simulation_report["sources"],
              "elf_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
              "payload_sha256": hashlib.sha256(payload).hexdigest(), "payload_bytes": len(payload),
              "base": start, "end_exclusive": end, "record_address": sections[-1]["sh_addr"],
              "hook_entries": {name: symbols[name] for name in ("farm_capture_start_hook", "farm_capture_encoding_hook")},
              "compatible_with_resident_af_r2": False, "hardware_requests": 0, "installed": False,
              "model_tests_run": False, "physical_integration_event_verified": False}
    (OUT / "target-build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
