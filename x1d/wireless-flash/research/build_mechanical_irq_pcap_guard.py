"""构建固定原厂调用点的有界复位替身，供离线 PCAP 指令回放。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'

def build():
    assert Path.cwd().resolve()==ROOT
    env=dict(os.environ)
    for key,folder in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]: env[key]=str(OUT/folder)
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    sources=[HERE/'native/mechanical_irq_pcap_guard.c',HERE/'native/mechanical_irq_pcap_guard.S']
    layout=OUT/'irq-pcap-guard.ld'
    layout.write_text('ENTRY(mechanical_irq_reset_call_guard)\nSECTIONS { . = 0x2b2880; .text : { KEEP(*(.text*)) KEEP(*(.rodata*)) } /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) } }\n',encoding='ascii')
    output=OUT/'irq-pcap-guard.elf'
    command=[str(zig),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9','-mfloat-abi=soft','-marm',
        '-Os','-g','-fno-lto','-ffreestanding','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
        '-nostdlib','-Wall','-Wextra','-Werror','-Wl,--no-undefined','-Wl,--build-id=none','-Wl,-T,'+str(layout),*map(str,sources),'-o',str(output)]
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode: raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from binary import ArmElf
    elf=ArmElf(output.read_bytes());sections=[s for s in elf.sections if s['sh_flags']&2 and s['sh_size']]
    assert not any(s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size'] for s in elf.sections)
    base=min(s['sh_addr'] for s in sections);end=max(s['sh_addr']+s['sh_size'] for s in sections)
    assert base==0x2b2880 and end<=0x2b4000
    payload=bytearray(end-base)
    for s in sections:payload[s['sh_addr']-base:s['sh_addr']-base+s['sh_size']]=s.data()
    (OUT/'irq-pcap-guard.bin').write_bytes(payload)
    symbols={s.name:s['st_value'] for section in elf.sections if section['sh_type']=='SHT_SYMTAB' for s in section.iter_symbols()}
    report={'built':True,'hardwareRequests':0,'installed':False,'base':base,'bytes':len(payload),
        'sha256':hashlib.sha256(payload).hexdigest(),'entries':{k:v for k,v in symbols.items() if k.startswith('mechanical_irq_') and v},
        'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[Path(__file__)]},
        'fullResourceRecoveryImplemented':False,'liveLoaderEnabled':False}
    (OUT/'irq-pcap-guard-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
