"""构建固定 1.25.0 早期只读接收器；不访问相机。"""
from pathlib import Path
import os,sys,subprocess,hashlib,json,io,struct
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
out=P/'build/activate-boot';out.mkdir(exist_ok=True)
layout=out/'layout.ld'
layout.write_text('SECTIONS { . = 0x2b3400; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } . = ALIGN(4); /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) } .bss : { *(.bss*) *(COMMON) } }',encoding='utf-8')
env=dict(os.environ)
for k,n in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
 d=out/n;d.mkdir(exist_ok=True);env[k]=str(d)
staged='--staged' in sys.argv
name='seed'
source=P/'native/boot_activate_seed.c';elf=out/(name+'.elf')
cmd=[str(ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-g','-target','thumb-freestanding-eabi','-mcpu=cortex_a9-neon','-mthumb','-Oz','-ffreestanding','-fpie','-fvisibility=hidden','-fno-stack-protector','-nostdlib','-static','-no-pie','-Wl,-T,'+str(layout),'-Wl,-e,hbl_seed_decode',str(source),'-o',str(elf)]
subprocess.run(cmd,check=True,env=env)
e=ELFFile(io.BytesIO(elf.read_bytes()));sections=[x for x in e.iter_sections() if x['sh_flags']&2 and x['sh_size']]
base=min(x['sh_addr'] for x in sections);end=max(x['sh_addr']+x['sh_size'] for x in sections)
assert base==0x2b3400 and end-base<=976
blob=bytearray(end-base)
for x in sections:
 if x['sh_type']!='SHT_NOBITS':blob[x['sh_addr']-base:x['sh_addr']-base+x['sh_size']]=x.data()
(out/(name+'.bin')).write_bytes(blob)
# 此独立无异常回调不使用栈展开；不把链接器 unwind 元数据上传控制器。
symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
delta=(symbols['hbl_seed_decode']&~1)-0x23acac-8
branch=0xfa000000|((delta>>2)&0xffffff)|((delta&2)<<23)
assert len(blob)%4==0
(out/'seed_data.h').write_text('#pragma once\nstatic const uint32_t seedImage[]={'+','.join(hex(v)+'u' for v in struct.unpack('<'+'I'*(len(blob)//4),blob))+'};\nstatic const uint32_t seedContext='+hex(symbols['hbl_seed'])+'u;\nstatic const uint32_t seedBranch='+hex(branch)+'u;\n',encoding='utf-8')
inputs=[source,P/'native/boot_batch_wire.h',P/'native/boot_batch_envelope.h',P/'native/boot_batch_mailbox.h',P/'build/batch-model/adapter_ranges.h',Path(__file__)]
r=dict(bytes=len(blob),base=base,sha256=hashlib.sha256(blob).hexdigest(),sourceHashes={str(x.relative_to(P)):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},hardwareRequests=0,installed=False)
(out/('staged-build.json' if staged else 'build.json')).write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
