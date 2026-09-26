"""在 ARM 指令层验证相同 C 像素核心；无 Linux/Qt/驱动或设备映射。"""
from __future__ import annotations
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
OUT = HERE / "artifacts/pixels"
sys.path.insert(0, str(ROOT / "x1d/tools"))
from binary import ArmElf, CACHE
from PIL import Image
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn import arm_const as R


class Arm:
    def __init__(self, path):
        self.elf = ArmElf(path.read_bytes())
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        loads = [p for p in self.elf.elf.iter_segments() if p["p_type"] == "PT_LOAD"]
        low = min(p["p_vaddr"] for p in loads) & ~4095
        high = (max(p["p_vaddr"] + p["p_memsz"] for p in loads) + 4095) & ~4095
        self.uc.mem_map(low,high-low)
        for segment in loads: self.uc.mem_write(segment["p_vaddr"],segment.data())
        self.uc.mem_map(0x10000000,0x1000000)
        self.uc.mem_map(0x20000000,0x100000)
        self.uc.reg_write(R.UC_ARM_REG_C1_C0_2,0xf << 20)
        self.uc.reg_write(R.UC_ARM_REG_FPEXC,0x40000000)
        self.exports = {s.name:s["st_value"] for s in self.elf.symbols if s.name.startswith("xj_") and s["st_value"]}
        self.stack,self.stop = 0x200f0000,0x200ff000

    def call(self, name, args):
        for index,value in enumerate(args[:4]): self.uc.reg_write(getattr(R,f"UC_ARM_REG_R{index}"),value)
        for index,value in enumerate(args[4:]): self.uc.mem_write(self.stack+index*4,struct.pack("<I",value))
        saved = [getattr(R,f"UC_ARM_REG_R{i}") for i in range(4,12)]
        for index,reg in enumerate(saved): self.uc.reg_write(reg,index+0x34500)
        self.uc.reg_write(R.UC_ARM_REG_SP,self.stack)
        self.uc.reg_write(R.UC_ARM_REG_LR,self.stop)
        self.uc.emu_start(self.exports[name],self.stop,count=500_000_000)
        assert self.uc.reg_read(R.UC_ARM_REG_PC) == self.stop, "ARM 指令预算耗尽"
        assert self.uc.reg_read(R.UC_ARM_REG_SP) == self.stack
        assert [self.uc.reg_read(r) for r in saved] == list(range(0x34500,0x34508))
        return self.uc.reg_read(R.UC_ARM_REG_R0)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(OUT / "zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(OUT / "zig-local-cache")
    env["TEMP"] = env["TMP"] = str(OUT / "tmp")
    (OUT / "tmp").mkdir(exist_ok=True)
    compiler = CACHE / "toolchain/zig-windows-x86_64-0.13.0/zig.exe"
    common = [str(compiler),"cc","-std=c11","-O2","-Wall","-Wextra","-Werror","-ffreestanding","-fno-builtin",
              "-fno-stack-protector","-nostdlib","-shared",str(HERE / "native/display_pixels.c")]
    paths = [OUT / "pixels-arm.so",OUT / "pixels-host.dll"]
    configs = [
        ["-target","arm-linux-musleabihf","-mcpu=cortex_a9","-marm","-fPIC","-Wl,--no-undefined","-Wl,-Bsymbolic"],
        ["-target","x86_64-windows-gnu","-Wl,--entry,DllMain","-Wl,--export-all-symbols",str(ROOT / "x1d/CodeTests/jpeg_container/host_entry.c")],
    ]
    for path,flags in zip(paths,configs):
        result = subprocess.run(common+flags+["-o",str(path)],cwd=ROOT,env=env,capture_output=True,text=True)
        (OUT / (path.name + ".compile.log")).write_text(result.stdout+result.stderr,encoding="utf-8")
        result.check_returncode()
    arm = Arm(paths[0])
    undefined = sorted({s.name for s in arm.elf.symbols if s.name and s["st_shndx"] == "SHN_UNDEF"})
    assert not undefined,undefined
    dll = C.CDLL(str(paths[1]))
    dll.xj_display_bgra.argtypes = [C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32,C.c_int]
    source_address,scratch_address = 0x10000001,0x10800001
    methods = [None,Image.Transpose.FLIP_LEFT_RIGHT,Image.Transpose.ROTATE_180,Image.Transpose.FLIP_TOP_BOTTOM,
               Image.Transpose.TRANSPOSE,Image.Transpose.ROTATE_270,Image.Transpose.TRANSVERSE,Image.Transpose.ROTATE_90]
    geometries = [(1,7),(6,1),(71,63),(256,320),(512,512),(528,528),(576,640)]
    directions = 0
    for w,h in geometries:
        rng = random.Random(w*1250+h)
        raw = rng.randbytes(w*h*4)
        img = Image.frombytes("RGBA",(w,h),raw)
        for o,method in enumerate(methods,1):
            wanted = (img if method is None else img.transpose(method)).tobytes()
            need = arm.call("xj_orient_scratch_bytes",[w,h,o])
            arm.uc.mem_write(source_address-1,b"\xa5"+raw+b"\xa5")
            arm.uc.mem_write(scratch_address-1,b"\x5a"*(need+2))
            status = arm.call("xj_orient_bgra",[source_address,len(raw),w,h,o,scratch_address if need else 0,need])
            assert status == 0,(w,h,o,status)
            assert bytes(arm.uc.mem_read(source_address-1,len(raw)+2)) == b"\xa5"+wanted+b"\xa5",(w,h,o)
            assert bytes(arm.uc.mem_read(scratch_address-1,1)) == b"\x5a"
            assert bytes(arm.uc.mem_read(scratch_address+need,1)) == b"\x5a"
            if need:
                assert arm.call("xj_orient_bgra",[source_address,len(raw),w,h,o,scratch_address,need-1]) == 5
                assert bytes(arm.uc.mem_read(source_address,len(raw))) == wanted
            directions += 1
    rgb = [(v,v,v) for v in range(256)]
    rgb += [(r,g,b) for r in range(0,256,17) for g in range(0,256,17) for b in range(0,256,17)]
    tables = (HERE / "native/display_fast_tables.h").read_text(encoding="utf-8")
    ambiguous = {}
    for name in ("red","green","blue"):
        match = re.search(r"fast_"+name+r"\[\d+\]\s*=\s*\{([^}]+)\}",tables)
        ambiguous[name] = [i for i,v in enumerate(map(int,re.findall(r"\d+",match.group(1)))) if v == 256]
    for i in ambiguous["red"]:
        rgb += [(i >> 8,i & 255,b) for b in (0,127,255)]
    for i in ambiguous["blue"]:
        rgb += [(r,i >> 8,i & 255) for r in (0,127,255)]
    for g in ambiguous["green"]:
        rgb += [(r,g,b) for r in (0,127,255) for b in (0,127,255)]
    assert len(rgb) <= 8192
    bgra = b"".join(bytes((b,g,r,19)) for r,g,b in rgb)
    host = C.create_string_buffer(bgra,len(bgra))
    assert dll.xj_display_bgra(host,len(bgra),len(rgb),1,1) == 0
    arm.uc.mem_write(source_address,bgra)
    assert arm.call("xj_display_bgra",[source_address,len(bgra),len(rgb),1,1]) == 0
    assert bytes(arm.uc.mem_read(source_address,len(bgra))) == host.raw
    full_scratch = arm.call("xj_orient_scratch_bytes",[8176,6128,6])
    assert full_scratch == 547729
    report = {
        "passed":True,"kind":"ARM Cortex-A9 instructions and independent Pillow orientation oracle",
        "orientationCases":directions,"geometries":geometries,"armColorSamples":len(rgb),
        "ambiguousPairsCovered":{k:len(v) for k,v in ambiguous.items()},"colorHostArmByteIdentical":True,
        "unalignedImageAndScratchGuards":True,"insufficientScratchLeavesImageUnchanged":True,
        "fullOrientationScratchBytes":full_scratch,"fullResolutionTransformRunOnArm":False,
        "undefinedArmSymbols":undefined,"cameraRequests":0,"qtGpuIntegration":False,
        "sources":{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in [Path(__file__),HERE / "native/display_pixels.c",HERE / "native/display_pixels.h",HERE / "native/display_tables.h",HERE / "native/display_fast_tables.h"]},
        "outputs":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    }
    (OUT / "arm-validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("sources","outputs")},ensure_ascii=False))


if __name__ == "__main__": run()
