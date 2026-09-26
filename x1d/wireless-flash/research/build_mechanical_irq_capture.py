"""编译实际 ARM 双中断处理器与原厂调用点包装，独立输出，禁止自动装机。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'


def build(target=False):
    if Path.cwd().resolve()!=ROOT:
        raise RuntimeError('工作区不匹配')
    OUT.mkdir(exist_ok=True)
    hooks=(HERE/'native/mechanical_sync_hooks.S').read_text(encoding='utf-8')
    if hooks.count('.word 0x31534d47')!=1 or hooks.count('.zero 360')!=1:
        raise ValueError('原调用点包装基线不符')
    hooks=hooks.replace('.word 0x31534d47','.word 0x32494d47').replace('.zero 360','.zero 104')
    old='''    mrs r12,APSR
    push {r12,lr}
.endm
.macro RESTORE
    pop {r12,lr}'''
    new='''    mrs r12,APSR
    push {r12,lr}
    vmrs r12,FPSCR
    push {r12,lr}
    vpush {d0-d15}
    vpush {d16-d31}
.endm
.macro RESTORE
    vpop {d16-d31}
    vpop {d0-d15}
    pop {r12,lr}
    vmsr FPSCR,r12
    pop {r12,lr}'''
    if hooks.count(old)!=1 or hooks.count('str r0,[sp,#12]')!=1:
        raise ValueError('寄存器保护模板不符')
    hooks=hooks.replace(old,new).replace('str r0,[sp,#12]','str r0,[sp,#276]')
    hooks=hooks.replace('.arm\n','.fpu neon\n.arm\n',1)
    (OUT/'irq_hooks.S').write_text(hooks,encoding='utf-8')
    base=0x2b2880 if target else 0x01000000
    name='irq-target' if target else 'irq-simulation'
    layout=OUT/(name+'.ld')
    layout.write_text('''ENTRY(mechanical_sync_clear_hook)
SECTIONS {
 . = %s;
 .text : { KEEP(*(.text.mechanical_sync_clear_hook)) KEEP(*(.text.mechanical_sync_start_hook)) KEEP(*(.text.mechanical_sync_status_hook)) KEEP(*(.text.mechanical_sync_finish_hook)) KEEP(*(.text.mechanical_irq_setup)) KEEP(*(.text.mechanical_irq_restore)) *(.text*) }
 .data : ALIGN(4) { *(.data.mechanical_sync_record) }
 ASSERT(SIZEOF(.data) == 108, "wrong IRQ record size")
 %s
 /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
'''%(hex(base),'ASSERT(ADDR(.data)+SIZEOF(.data)<=0x2b4000,"arena overlap")' if target else ''),encoding='ascii')
    env=dict(os.environ)
    for key,name_ in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name_; folder.mkdir(exist_ok=True); env[key]=str(folder)
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    sources=[HERE/'native/mechanical_irq_capture.c',OUT/'irq_hooks.S']
    output=OUT/(name+'.elf')
    command=[str(compiler),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9','-mfloat-abi=soft','-marm',
        '-Os','-g','-fno-lto','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-stack-protector',
        '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fPIC','-Wl,--no-undefined','-nostdlib',
        '-Wl,--build-id=none','-Wall','-Wextra','-Werror','-I',str(HERE/'native'),'-Wl,-T,'+str(layout),
        *map(str,sources),'-o',str(output)]
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from binary import ArmElf
    elf=ArmElf(output.read_bytes())
    sections=[s for s in elf.sections if s['sh_flags']&2 and s['sh_size']]
    if any(s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size'] for s in elf.sections):
        raise ValueError('存在运行时重定位')
    if min(s['sh_addr'] for s in sections)!=base:
        raise ValueError('基址不符')
    end=max(s['sh_addr']+s['sh_size'] for s in sections)
    if target and end>0x2b4000:
        raise ValueError('临时执行区越界')
    payload=bytearray(end-base)
    for section in sections:
        payload[section['sh_addr']-base:section['sh_addr']-base+section['sh_size']]=section.data()
    (OUT/(name+'.bin')).write_bytes(payload)
    symbols={s.name:s['st_value'] for section in elf.sections if section['sh_type']=='SHT_SYMTAB' for s in section.iter_symbols()}
    for entry in ('mechanical_irq_setup','mechanical_irq_restore','mechanical_irq_hold','mechanical_irq_idle'):
        if entry not in symbols:
            raise ValueError('中断必需入口被链接器移除: '+entry)
    report={'built':True,'installed':False,'hardwareRequests':0,'base':base,'end':end,'payloadBytes':len(payload),
        'recordBytes':108,'elfSha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'payloadSha256':hashlib.sha256(payload).hexdigest(),
        'entries':{k:v for k,v in symbols.items() if k.startswith('mechanical_')},
        'command':command,'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources+[HERE/'native/mechanical_irq_capture.h',HERE/'native/mechanical_irq_wire.h',Path(__file__)]},
        'instructionReplayPassed':False,'loaderImplemented':False}
    (OUT/(name+'-build.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    for target in (False,True):
        report=build(target)
        print(json.dumps({k:report[k] for k in ('built','installed','payloadBytes','payloadSha256')}))
