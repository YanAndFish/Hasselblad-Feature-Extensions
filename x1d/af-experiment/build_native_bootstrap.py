"""构建经模块协调预留的 AF 引导布局；仍需装载事务，不能直接安装。"""
import hashlib,json,os,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
CACHE=ROOT/'.research-cache/x1d-1.25.0';BUILD=HERE/'build/native-bootstrap-r1'
sys.path[:0]=[str(ROOT/'x1d/tools'),str(CACHE/'python')]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication
def branch(a,b,link=False):
    d=b-a-8;assert b%4==0 and d%4==0 and -(1<<25)<=d<(1<<25)
    return (0xeb000000 if link else 0xea000000)|((d>>2)&0xffffff)
def main():
    env=dict(os.environ)
    for key,name in {'TEMP':'tmp','TMP':'tmp','ZIG_GLOBAL_CACHE_DIR':'cache/global','ZIG_LOCAL_CACHE_DIR':'cache/local'}.items():
        folder=BUILD/name;folder.mkdir(parents=True,exist_ok=True);env[key]=str(folder)
    layout=BUILD/'bootstrap.ld'
    layout.write_text('ENTRY(nr_idle_gate)\nSECTIONS { . = 0x2b3400; .text : { KEEP(*(.text.bootstrap)) KEEP(*(.text.nr_api)) *(.text*) *(.rodata*) } . = ALIGN(32); .data : { *(.data.bootstrap) *(.data*) } .bss : { *(.bss*) } . = ALIGN(32); __end = .; /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } ASSERT(. <= 0x2b3f40,"overlap reserved helper") }\n',encoding='ascii')
    cmd=[str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','thumb-freestanding-eabi',
         '-mcpu=cortex_a9','-mthumb','-mfloat-abi=soft','-Oz','-g','-fno-lto','-ffreestanding','-fno-builtin',
         '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror',
         '-nostdlib','-Wl,--build-id=none','-Wl,-e,nr_idle_gate','-Wl,-T,'+str(layout),'-o',str(BUILD/'bootstrap.elf'),
         str(HERE/'native_reserve.c'),str(HERE/'native_bootstrap.S')]
    subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
    elf=ArmElf((BUILD/'bootstrap.elf').read_bytes());symbols={s.name:s['st_value'] for s in elf.symbols if s['st_shndx']!='SHN_UNDEF'}
    assert not [s.name for s in elf.symbols if s['st_shndx']=='SHN_UNDEF' and s.name]
    base=0x2b3400;end=symbols['__end'];payload=bytearray(end-base);sections=[]
    for sec in elf.sections:
        if sec['sh_flags']&2:
            a,n=sec['sh_addr'],sec['sh_size'];assert base<=a<=a+n<=end
            sections.append({'name':sec.name,'base':a,'endExclusive':a+n,'bytes':n})
            if sec['sh_type']!='SHT_NOBITS':payload[a-base:a-base+n]=sec.data()
    farm=FarmApplication();assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    assert not any(farm.read(base,end-base))
    hooks=[(0x19b960,0xe51b3094,branch(0x19b960,symbols['nr_idle_gate'])),
           (0x1e2224,branch(0x1e2224,0x1e1768,True),branch(0x1e2224,symbols['nr_wake'],True))]
    for a,old,new in hooks:assert farm.word(a)==old
    assert end<=0x2b3f40 and base>=0x2b3400>0x2b331c
    (BUILD/'bootstrap.bin').write_bytes(payload)
    manifest={'kind':'offline-af-bootstrap-layout','installable':False,'hardwareRequests':0,'base':base,'end':end,
        'baselineSha256':farm.sha256,'symbols':symbols,'bytes':len(payload),'sections':sections,
        'emulatorOnlyHooks':hooks,'payloadSha256':hashlib.sha256(payload).hexdigest(),
        'coexistence':{'flashExcluded':[0x2b2880,0x2b331c],'gapExcluded':[0x2b331c,0x2b3400],
            'afBootstrapReserved':[0x2b3400,0x2b3f40],'scratchSharedExclusiveUse':[0x2b2800,0x2b2840],
            'helperExcluded':[0x2b3f40,0x2b4000]},
        'requestedHeapPayloadBytes':16384,'minimumRemainingHeapBytes':131072,
        'sourceSha256':{p:hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in ('native_reserve.c','native_bootstrap.S','build_native_bootstrap.py')},
        'limitations':['仅模块占用协调与固定镜像核对，未验证当前实机基线','尚无 USB/缓存同步/日志恢复完整装载事务',
            'F4 读取 ACK 地址在临时 hook 期间会产生一次 AF 任务通知','引导代码与堆归属记录不得在 hook 恢复后立即擦除']}
    (BUILD/'bootstrap-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ('base','end','bytes','sections','payloadSha256')},ensure_ascii=False))
if __name__=='__main__':main()
