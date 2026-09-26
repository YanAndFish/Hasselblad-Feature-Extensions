"""只在本模块构建第七条有界观察候选；不连接设备。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / "build/farm-route7-trace"
SITES = {0x1c4318: ("route7_normal", 0x1c3810, 0xebfffd3c),
         0x1c52a0: ("route7_normal", 0x1c3810, 0xebfff95a),
         0x1ca0b4: ("route7_normal", 0x1c3810, 0xebffe5d5),
         0x1ce150: ("route7_entry", 0x1c818c, 0xebffe80d),
         0x1c8874: ("route7_pulse", 0x23899c, 0xeb01c048),
         0x1c8950: ("route7_after_sensor", 0x1c7fdc, 0xebfffda1)}


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
    compiler = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"
    source = HERE / "native/farm_route7_trace.S"
    sys.path.insert(0, str(ROOT / "x1d/tools"))
    from binary import ArmElf
    reports = {}
    for name, base in (("simulation", 0x1000000), ("target", 0x2b2880)):
        layout = OUT / (name + ".ld")
        layout.write_text('ENTRY(route7_normal)\nSECTIONS {\n . = ' + hex(base) + ';\n' +
                          ' .text : { *(.text*) }\n .data : ALIGN(4) { *(.data*) }\n' +
                          ' ASSERT(SIZEOF(.data) == 96, "wrong record size")\n' +
                          (' ASSERT(. <= 0x2b4000, "outside padding")\n' if name == "target" else '') +
                          ' /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }\n}\n', encoding="ascii")
        destination = OUT / (name + ".elf")
        command = [str(compiler), "cc", "-target", "arm-freestanding-eabi", "-mcpu=cortex_a9", "-marm",
                   "-mfloat-abi=soft", "-nostdlib", "-Wl,--no-undefined", "-Wl,--build-id=none",
                   "-Wl,-T," + str(layout), str(source), "-o", str(destination)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr)
        elf = ArmElf(destination.read_bytes())
        if any(s["sh_type"] in ("SHT_REL", "SHT_RELA") and s["sh_size"] for s in elf.sections):
            raise RuntimeError("unresolved relocation")
        sections = [s for s in elf.sections if s["sh_flags"] & 2 and s["sh_size"]]
        end = max(s["sh_addr"] + s["sh_size"] for s in sections)
        blob = bytearray(end - base)
        for s in sections:
            blob[s["sh_addr"] - base:s["sh_addr"] - base + s["sh_size"]] = s.data()
        symbols = {s.name: s["st_value"] for sec in elf.sections if sec["sh_type"] == "SHT_SYMTAB" for s in sec.iter_symbols()}
        (OUT / (name + ".bin")).write_bytes(blob)
        reports[name] = {"base": base, "end": end, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
                         "elf_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                         "record_address": symbols["route7_record"],
                         "hooks": {hex(a): {"entry": symbols[s], "original_target": t, "original_word": w}
                                   for a, (s, t, w) in SITES.items()}}
    reports.update(hardware_requests=0, installed=False, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    (OUT / "build.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    return reports


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
