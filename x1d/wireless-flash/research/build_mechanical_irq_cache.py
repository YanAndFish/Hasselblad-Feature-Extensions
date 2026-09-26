"""固定缓存校验/恢复核心的 ARM 与主机构建；无实机调用入口。"""
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
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('工作区不匹配')
    plan=json.loads((OUT/'irq-pl-word-plan.json').read_text(encoding='utf-8'))
    sys.path.insert(0,str(HERE/'research'))
    from mechanical_irq_loading import apply_image,BASE_SHA
    candidate=(OUT/'irq-pl-candidate.bin').read_bytes()
    original=apply_image(candidate,plan,True)
    assert plan['baselineSha256']==BASE_SHA and len(original)==5979936
    rows=plan['words']
    assert len(rows)==253 and [r['offset'] for r in rows]==sorted({r['offset'] for r in rows})
    header='#define IRQ_CACHE_BYTES 5979936u\n#define IRQ_CACHE_ROWS 253u\n'
    assert all(0<=r['offset']<1<<24 for r in rows)
    header+='static const uint8_t irq_cache_offsets[253][3]={\n'
    header+=''.join('{%su,%su,%su},\n'%tuple(r['offset'].to_bytes(3,'little')) for r in rows)+'};\n'
    header+='static const uint32_t irq_cache_values[253][2]={\n'
    header+=''.join('{%su,%su},\n'%(r['before'],r['after']) for r in rows)+'};\n'
    header+='static const uint32_t irq_cache_baseline_sha[8]={'+','.join('0x'+BASE_SHA[i:i+8]+'u' for i in range(0,64,8))+'};\n'
    (OUT/'irq_cache_plan.h').write_text(header,encoding='ascii')
    env=dict(os.environ)
    for key,folder in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        env[key]=str(OUT/folder)
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    source=HERE/'native/mechanical_irq_cache.c'
    common=[str(zig),'cc','-Os','-g','-fno-lto','-fno-vectorize','-fno-slp-vectorize','-Wall','-Wextra','-Werror','-I',str(OUT),str(source)]
    layout=OUT/'irq-cache.ld'
    layout.write_text('ENTRY(mechanical_irq_cache_classify)\nSECTIONS { . = 0x2b2880; .text : { KEEP(*(.text*)) KEEP(*(.rodata*)) } ASSERT(. <= 0x2b4000,"cache stage too large") /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) } }\n',encoding='ascii')
    commands=[common+['-target','arm-freestanding-eabi','-mcpu=cortex_a9','-mfloat-abi=soft','-mfpu=none','-marm','-ffreestanding','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-Wl,--no-undefined','-Wl,--build-id=none','-Wl,-T,'+str(layout),'-o',str(OUT/'irq-cache.elf')],
              common+['-shared','-o',str(OUT/'irq-cache.dll')]]
    for command in commands:
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
        if result.returncode: raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from binary import ArmElf
    elf=ArmElf((OUT/'irq-cache.elf').read_bytes())
    sections=[s for s in elf.sections if s['sh_flags']&2 and s['sh_size']]
    assert not any(s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size'] for s in elf.sections)
    base=min(s['sh_addr'] for s in sections); end=max(s['sh_addr']+s['sh_size'] for s in sections)
    payload=bytearray(end-base)
    for s in sections: payload[s['sh_addr']-base:s['sh_addr']-base+s['sh_size']]=s.data()
    (OUT/'irq-cache.bin').write_bytes(payload)
    symbols={s.name:s['st_value'] for section in elf.sections if section['sh_type']=='SHT_SYMTAB' for s in section.iter_symbols()}
    report={'built':True,'installed':False,'hardwareRequests':0,'base':base,'end':end,'bytes':len(payload),
        'sha256':hashlib.sha256(payload).hexdigest(),'baselineSha256':BASE_SHA,'candidateSha256':plan['candidateSha256'],
        'entries':{k:v for k,v in symbols.items() if k.startswith('mechanical_irq_cache_')},
        'requiresTaskContextAndExclusiveCacheOwnership':True,'deviceEntryImplemented':False,'pcapImplemented':False,
        'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__),OUT/'irq_cache_plan.h',OUT/'irq-pl-word-plan.json')},
        'dllSha256':hashlib.sha256((OUT/'irq-cache.dll').read_bytes()).hexdigest()}
    (OUT/'irq-cache-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__': print(json.dumps(build(),ensure_ascii=False))
