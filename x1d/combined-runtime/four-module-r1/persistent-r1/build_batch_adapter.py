"""构建可重定位FARM适配器候选；不操作相机。"""
from pathlib import Path
import sys,os,re,struct,subprocess,io,json,hashlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;ROOT=P.parents[3];assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
import build_fast_baseline
expected,guards,_=build_fast_baseline.build()
addresses=sorted(expected)
ranges=[]
for a in addresses:
 if ranges and a==ranges[-1][0]+ranges[-1][1]:ranges[-1][1]+=4
 else:ranges.append([a,4])
contract=(P/'build/boot-data/boot_contract_data.h').read_text(encoding='utf-8')
af=(P/'build/boot-data/af_relocation_data.h').read_text(encoding='utf-8')
def size(text,name):return 4*len(re.findall(r'0x[0-9a-f]+u',text.split(name+'[] = {')[1].split('};')[0]))
afbytes=size(af,'hbl_af_words');flashbytes=size(contract,'hbl_flash_words');assert afbytes<=16384
out=P/'build/batch-model';out.mkdir(exist_ok=True)
(out/'adapter_ranges.h').write_text('#define HBL_BATCH_AF_BYTES '+str(afbytes)+'u\n#define HBL_BATCH_FLASH_BASE 0x2b2880u\n#define HBL_BATCH_FLASH_BYTES '+str(flashbytes)+'u\nstatic const uint32_t hbl_batch_ranges[][2]={'+','.join('{%du,%du}'%tuple(r) for r in ranges)+'};\n',encoding='utf-8')
env=dict(os.environ)
for k,n in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
 d=out/n;d.mkdir(exist_ok=True);env[k]=str(d)
layout=out/'adapter.ld';layout.write_text('SECTIONS { . = 0x20000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } .ARM.exidx : { *(.ARM.exidx*) } .bss : { *(.bss*) *(COMMON) } }',encoding='utf-8')
elfpath=out/'adapter.elf'
command=[str(ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9-neon','-marm','-mfpu=none','-fno-vectorize','-fno-slp-vectorize','-g','-Oz','-ffreestanding','-fpie','-fvisibility=hidden','-fno-stack-protector','-nostdlib','-static','-no-pie','-Wl,-T,'+str(layout),'-Wl,-e,hbl_batch_decode','-Wl,-u,hbl_batch_read_dispatch',str(P/'native/boot_batch_adapter.c'),'-o',str(elfpath)]
subprocess.run(command,env=env,check=True)
e=ELFFile(io.BytesIO(elfpath.read_bytes()));sections=[s for s in e.iter_sections() if s['sh_flags']&2 and s['sh_size']]
base=min(s['sh_addr'] for s in sections);end=max(s['sh_addr']+s['sh_size'] for s in sections);assert base==0x20000 and end-base<=8192
blob=bytearray(end-base)
for sec in sections:
 if sec['sh_type']!='SHT_NOBITS':blob[sec['sh_addr']-base:sec['sh_addr']-base+sec['sh_size']]=sec.data()
def immediate(w):return (w&4095)|((w>>4)&61440)
def putimm(w,v):return (w&~0x000f0fff)|((v&61440)<<4)|(v&4095)
fixups=[off for off in range(0,len(blob)-3,4) if base<=struct.unpack_from('<I',blob,off)[0]<base+len(blob)]
pairs=[]
textsec=e.get_section_by_name('.text');textend=textsec['sh_addr']-base+textsec['sh_size']
for hi in range(0,textend,4):
    w=struct.unpack_from('<I',blob,hi)[0]
    if w&0x0ff00000!=0x03400000:continue
    for lo in range(hi-4,max(-1,hi-44),-4):
        v=struct.unpack_from('<I',blob,lo)[0]
        if v&0x0ff0f000==0x03000000|(w&0xf000):
            pointer=immediate(v)|(immediate(w)<<16)
            if base<=pointer<base+len(blob):pairs.append([lo,hi])
            break
for other_base in (0x61240,0x39ffc0):
    layout.write_text(layout.read_text(encoding='utf-8').replace(hex(base),hex(other_base)),encoding='utf-8')
    alt=out/('adapter-'+hex(other_base)+'.elf');cmd=list(command);cmd[-1]=str(alt)
    subprocess.run(cmd,env=env,check=True)
    ae=ELFFile(io.BytesIO(alt.read_bytes()));other=bytearray(len(blob))
    for sec in ae.iter_sections():
        if sec['sh_flags']&2 and sec['sh_size']:
            offset=sec['sh_addr']-other_base;assert 0<=offset and offset+sec['sh_size']<=len(other)
            if sec['sh_type']!='SHT_NOBITS':other[offset:offset+sec['sh_size']]=sec.data()
    patched=bytearray(blob);delta=other_base-base
    for off in fixups:struct.pack_into('<I',patched,off,struct.unpack_from('<I',blob,off)[0]+delta)
    for lo,hi in pairs:
        a,b=struct.unpack_from('<I',blob,lo)[0],struct.unpack_from('<I',blob,hi)[0]
        pointer=(immediate(a)|(immediate(b)<<16))+delta
        struct.pack_into('<I',patched,lo,putimm(a,pointer&65535));struct.pack_into('<I',patched,hi,putimm(b,pointer>>16))
    assert patched==other,'relocation differs from independent linker'
    layout.write_text(layout.read_text(encoding='utf-8').replace(hex(other_base),hex(base)),encoding='utf-8')
syms={s.name:s['st_value']-base for s in e.get_section_by_name('.symtab').iter_symbols() if s.name in ('hbl_batch_decode','hbl_batch_read_dispatch','hbl_batch_adapter')}
assert len(syms)==3
(out/'adapter.bin').write_bytes(blob)
source_hashes={str(x.relative_to(P)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [Path(__file__),P/'native/boot_batch_adapter.c',P/'native/boot_batch_mailbox.h',P/'native/boot_batch_envelope.h',P/'native/boot_batch_wire.h',out/'adapter_ranges.h']}
r=dict(sourceHashes=source_hashes,base=base,bytes=len(blob),afBytes=afbytes,flashBytes=flashbytes,fixups=fixups,movPairs=pairs,symbols=syms,independentLinkBases=[0x20000,0x61240,0x39ffc0],sha256=hashlib.sha256(blob).hexdigest(),installed=False)
(out/'adapter-build.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))

# 供机内装载器逐字验证并重定位；保留原厂版本绑定的入口指令。
firmware=(P/'build/fast-start-research/farm-1.25.0.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest()=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
header=['#pragma once','#include <stdint.h>','static const uint32_t hbl_batch_image[]={']
assert len(blob)%4==0
header+=['0x%08xu,'%w for w in struct.unpack('<'+'I'*(len(blob)//4),blob)];header+=['};','static const uint32_t hbl_batch_abs_fixups[]={'+','.join(str(x)+'u' for x in fixups)+'};','static const uint32_t hbl_batch_mov_fixups[][2]={'+','.join('{%du,%du}'%tuple(x) for x in pairs)+'};']
for name,offset in syms.items():header.append('static const uint32_t '+name+'_offset='+str(offset)+'u;')
header+=['static const uint32_t hbl_batch_link_base=0x20000u;','static const uint32_t hbl_batch_heap_offset=16384u;','static const uint32_t hbl_batch_entry_expected[][2]={']
addresses=set(range(0x23ac64,0x23ae20,4))|set(range(0x23cfa4,0x23cfc4,4))|set(range(0x1e1768,0x1e1788,4))|set(range(0x1e80d0,0x1e80f0,4))|{0x1e2224}
for a in sorted(addresses):header.append('{0x%08xu,0x%08xu},'%(a,struct.unpack_from('<I',firmware,a-0x100000)[0]))
header+=['};']
(out/'adapter_data.h').write_text('\n'.join(header)+'\n',encoding='utf-8')
