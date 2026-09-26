"""执行实际 ARM 候选校验器；内存读取是离线替身，不是实机速度测试。"""
from pathlib import Path
import io
import json
import os
import struct
import subprocess
import sys
sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0, str(ROOT/'.research-cache/x1d-1.25.0/python'))
sys.path.insert(0, str(BASE))
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
import build_fast_baseline
expected, guards, _ = build_fast_baseline.build()
memory = dict(expected)
for a, mask, value in guards:
    memory[a] = (memory.get(a, 0) & ~mask) | value
out = BASE/'build/fast-start-research'
env = dict(os.environ)
for key, folder in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
    env[key] = str(out/folder)
zig = str(ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe')
elf_path = out/'fast_baseline_arm.elf'
layout = out/'fast_baseline_arm.ld'
layout.write_text('SECTIONS { . = 0x20000; .text : { *(.text*) } .rodata : { *(.rodata*) } .ARM.exidx : { *(.ARM.exidx*) } }\n',encoding='utf-8')
subprocess.run([zig,'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9','-marm','-nostdlib',
                '-Wl,-T,'+str(layout),'-Wl,-e,hbl_fast_check_memory',str(out/'fast_baseline_arm.o'),'-o',str(elf_path)],env=env,check=True)
elf = ELFFile(io.BytesIO(elf_path.read_bytes()))


def run(label, mutation=None, fail_at=0):
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    u.mem_map(0x10000, 0x100000)
    u.mem_map(0x8000, 0x2000)
    u.mem_map(0x700000, 0x10000)
    for segment in elf.iter_segments():
        if segment['p_type']=='PT_LOAD':
            address=segment['p_vaddr']
            assert 0x10000 <= address and address+segment['p_memsz'] <= 0x110000
            u.mem_write(address,segment.data())
    seen=[]
    def read_hook(machine,address,size,context):
        target=machine.reg_read(UC_ARM_REG_R1)
        pointer=machine.reg_read(UC_ARM_REG_R2)
        assert 0x700000<=pointer<=0x70fffc and target in memory
        seen.append(target)
        value=memory[target]
        if mutation and target==mutation[0]:value^=mutation[1]
        machine.mem_write(pointer,struct.pack('<I',value))
        machine.reg_write(UC_ARM_REG_R0,0 if len(seen)==fail_at else 1)
        machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,read_hook,begin=0x8000,end=0x8000)
    u.reg_write(UC_ARM_REG_SP,0x70fff0)
    u.reg_write(UC_ARM_REG_LR,0x9000)
    u.reg_write(UC_ARM_REG_R0,0x8000)
    u.reg_write(UC_ARM_REG_R1,0)
    u.emu_start(elf['e_entry'],0x9000,count=1000000)
    assert u.reg_read(UC_ARM_REG_PC)==0x9000, '指令预算耗尽'
    result=u.reg_read(UC_ARM_REG_R0)
    assert result==(0 if mutation or fail_at else 1)
    if not mutation and not fail_at:assert set(expected)<=set(seen)
    if fail_at:assert len(seen)==fail_at
    return {'case':label,'result':result,'reads':len(seen)}


cases=[run('exact-baseline'),run('first-word-mismatch',(min(expected),1)),
       run('last-word-mismatch',(max(expected),1)),run('read-failure',fail_at=3000),
       run('busy-guard',(0x6bb46c,1))]
report={'passed':True,'cases':cases,'hardwareRequests':0,'timingProven':False}
(out/'fast-baseline-arm-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
