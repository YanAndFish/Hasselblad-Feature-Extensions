"""构建控制器内初始化候选；不访问相机。"""
from pathlib import Path
import sys,os,re,subprocess,io,json,hashlib,struct
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
out=P/'build/merged-boot';out.mkdir(exist_ok=True)
contract=(P/'build/boot-data/boot_contract_data.h').read_text(encoding='utf-8')
def rows(name):
 body=contract.split(name+'[] = {',1)[1].split('};',1)[0]
 return [[int(v,16) for v in re.findall(r'0x([0-9a-f]+)u',row)] for row in body.splitlines() if '{' in row]
hooks=rows('hbl_af_hooks');gate=next(x for x in rows('hbl_bootstrap_hooks') if x[0]==0x19b960)
text='#pragma once\nstatic const uint32_t hooks[][3]={\n'+''.join('{'+','.join(hex(x)+'u' for x in row)+'},\n' for row in hooks)+'};\n'
values=dict(HOOK_COUNT=len(hooks),AF_BYTES=2976,GATE_ORIGINAL=gate[1],GATE_BRANCH=gate[2])
for name,key in [('ACK','af_install_ack'),('PROBE','af_install_probe'),('IDENTITY','af_identity')]:
 values[name]=int(re.search('hbl_offset_'+key+r'=0x([0-9a-f]+)u',contract)[1],16)
text+=''.join(f'#define {k} {hex(v)}u\n' for k,v in values.items())
(out/'contract.h').write_text(text,encoding='utf-8',newline='\n')
layout=out/'layout.ld'
layout.write_text('SECTIONS { . = 0x400000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } .ARM.exidx : { *(.ARM.exidx*) } .bss : { *(.bss*) *(COMMON) } }',encoding='utf-8')
env=dict(os.environ)
for key,name in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
 d=out/name;d.mkdir(exist_ok=True);env[key]=str(d)
source=P/'native/af_merged_init.c';elf=out/'initializer.elf'
cmd=[str(ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-g','-target','arm-freestanding-eabi','-mcpu=cortex_a9-neon','-marm','-Oz','-ffreestanding','-fPIC','-fvisibility=hidden','-fno-stack-protector','-nostdlib','-fPIC','-Wl,-T,'+str(layout),'-Wl,-e,hbl_af_resident_init',str(source),'-o',str(elf)]
subprocess.run(cmd,env=env,check=True)
e=ELFFile(io.BytesIO(elf.read_bytes()));sections=[s for s in e.iter_sections() if s['sh_flags']&2 and s['sh_size']]
base=min(s['sh_addr'] for s in sections);end=max(s['sh_addr']+s['sh_size'] for s in sections)
assert base==0x400000 and end-base<=16384
blob=bytearray((end-base+3)&~3)
for s in sections:
 if s['sh_type']!='SHT_NOBITS':blob[s['sh_addr']-base:s['sh_addr']-base+s['sh_size']]=s.data()
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
for other_base in (0x39aea0,0x452000):
    layout.write_text(layout.read_text(encoding='utf-8').replace(hex(base),hex(other_base)),encoding='utf-8')
    alt=out/('adapter-'+hex(other_base)+'.elf');othercmd=list(cmd);othercmd[-1]=str(alt)
    subprocess.run(othercmd,env=env,check=True)
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

entry=e.get_section_by_name('.symtab').get_symbol_by_name('hbl_af_resident_init')[0]['st_value']-base
(out/'initializer.bin').write_bytes(blob)
r=dict(base=base,fixups=fixups,movPairs=pairs,bytes=len(blob),entryOffset=entry,sha256=hashlib.sha256(blob).hexdigest(),sources={str(x.relative_to(P)):hashlib.sha256(x.read_bytes()).hexdigest() for x in (source,out/'contract.h',Path(__file__))},installed=False)
(out/'build.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))



