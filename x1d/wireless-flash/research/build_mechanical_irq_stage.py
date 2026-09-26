"""组合临时任务入口、完整缓存核对及有界握手；不连接设备。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'

def build():
    assert Path.cwd().resolve()==ROOT
    cached=json.loads((OUT/'irq-cache-build.json').read_text(encoding='utf-8'))
    for name,digest in cached['sourceHashes'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest
    env=dict(os.environ)
    for key,folder in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:env[key]=str(OUT/folder)
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    sources=[HERE/'native'/name for name in ('mechanical_irq_cache.c','mechanical_irq_pcap_guard.c','mechanical_irq_pcap_guard.S','mechanical_irq_stage.c','mechanical_irq_retire.c')]
    layout=OUT/'irq-stage.ld'
    layout.write_text('ENTRY(mechanical_irq_stage_message)\nSECTIONS { . = 0x2b26a0; .retire : { KEEP(*(.text.stage_retire)) KEEP(*(.rodata.stage_retire)) KEEP(*(.text.stage_idle)) } ASSERT(. <= 0x2b2800,"retire and idle overlap scratch") . = 0x2b2840; .text : { KEEP(*(.text*)) KEEP(*(.rodata*)) } .data : ALIGN(4) { *(.data*) } ASSERT(. <= 0x2b4000,"stage arena overflow") /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) } }\n',encoding='ascii')
    output=OUT/'irq-stage.elf'
    command=[str(zig),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9','-mfloat-abi=soft','-mfpu=none','-marm',
        '-Oz','-g','-fno-lto','-fno-vectorize','-fno-slp-vectorize','-ffreestanding','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
        '-nostdlib','-Wall','-Wextra','-Werror','-I',str(OUT),'-Wl,--no-undefined','-Wl,--build-id=none','-Wl,-T,'+str(layout),*map(str,sources),'-o',str(output)]
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode:raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from binary import ArmElf
    elf=ArmElf(output.read_bytes());sections=[s for s in elf.sections if s['sh_flags']&2 and s['sh_size']]
    assert not any(s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size'] for s in elf.sections)
    base=min(s['sh_addr'] for s in sections);end=max(s['sh_addr']+s['sh_size'] for s in sections)
    assert base==0x2b26a0 and end<=0x2b4000
    payload=bytearray(end-base)
    for s in sections:payload[s['sh_addr']-base:s['sh_addr']-base+s['sh_size']]=s.data()
    (OUT/'irq-stage.bin').write_bytes(payload)
    symbols={}
    for section in elf.sections:
        if section['sh_type']!='SHT_SYMTAB':continue
        for symbol in section.iter_symbols():
            if symbol['st_info']['type']=='STT_FUNC' and symbol['st_size']:
                assert not any(i.mnemonic.startswith('v') for i in elf.instructions(symbol['st_value'],symbol['st_size'])),symbol.name
            if symbol.name.startswith('mechanical_irq_') and symbol['st_value']:symbols[symbol.name]=symbol['st_value']
    report={'built':True,'hardwareRequests':0,'installed':False,'base':base,'end':end,'bytes':len(payload),
        'sha256':hashlib.sha256(payload).hexdigest(),'entries':symbols,'floatingPointOrNeonInstructions':False,
        'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[Path(__file__),OUT/'irq_cache_plan.h']},
        'taskEntryImplemented':True,'hostStageInstallerImplemented':False,'liveLoaderEnabled':False,
        'successfulCandidateCacheRetainedForStandby':True,'failedLoadCacheRestored':True,
        'requiresResourcesPoweredDownBeforePcap':True,'normalPowerDownAttemptAfterQuietTicks':600,
        'resourceStateOrPowerFlagForced':False,'failedLoadAutomaticallyRetried':False,'fullResourceRecoveryValidated':False}
    (OUT/'irq-stage-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
