"""只构建独立申请原型，链接到仿真地址；不带设备访问或实机地址分配。"""
import hashlib,json,os,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
CACHE=ROOT/'.research-cache/x1d-1.25.0';BUILD=HERE/'build/native-memory-study'
sys.path[:0]=[str(ROOT/'x1d/tools'),str(CACHE/'python')]
from binary import ArmElf
def main():
    env=dict(os.environ)
    for key,name in {'TEMP':'tmp','TMP':'tmp','ZIG_GLOBAL_CACHE_DIR':'cache/global','ZIG_LOCAL_CACHE_DIR':'cache/local'}.items():
        folder=BUILD/name;folder.mkdir(parents=True,exist_ok=True);env[key]=str(folder)
    layout=BUILD/'reserve.ld'
    layout.write_text('ENTRY(nr_reserve)\nSECTIONS { . = 0x900000; .text : { KEEP(*(.text.nr_api)) *(.text*) *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) } . = ALIGN(4); __end = .; /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n',encoding='ascii')
    cmd=[str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','thumb-freestanding-eabi',
         '-mcpu=cortex_a9','-mthumb','-mfloat-abi=soft','-Oz','-g','-fno-lto','-ffreestanding','-fno-builtin',
         '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror',
         '-nostdlib','-Wl,--build-id=none','-Wl,-e,nr_reserve','-Wl,-T,'+str(layout),'-o',str(BUILD/'reserve.elf'),str(HERE/'native_reserve.c')]
    subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
    elf=ArmElf((BUILD/'reserve.elf').read_bytes());symbols={s.name:s['st_value'] for s in elf.symbols if s['st_shndx']!='SHN_UNDEF'}
    assert not [s.name for s in elf.symbols if s['st_shndx']=='SHN_UNDEF' and s.name]
    base=0x900000;end=symbols['__end'];payload=bytearray(end-base)
    for sec in elf.sections:
        if sec['sh_flags']&2:
            a,n=sec['sh_addr'],sec['sh_size'];assert base<=a<=a+n<=end
            if sec['sh_type']!='SHT_NOBITS':payload[a-base:a-base+n]=sec.data()
    (BUILD/'reserve.bin').write_bytes(payload)
    manifest={'kind':'offline-task-heap-reservation','installable':False,'hardwareRequests':0,'base':base,'end':end,
        'symbols':symbols,'bytes':len(payload),'payloadSha256':hashlib.sha256(payload).hexdigest(),
        'sourceSha256':{p:hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in ('native_reserve.c','build_native_reserve.py')}}
    (BUILD/'reserve-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))
if __name__=='__main__':main()
