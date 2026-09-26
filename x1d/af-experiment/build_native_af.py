"""仅构建原厂局部 AF 辅助离线镜像；无硬件、装载器或自动安装入口。"""
import hashlib,json,os,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
CACHE=ROOT/'.research-cache/x1d-1.25.0';BUILD=HERE/'build/native-af-r1'
sys.path[:0]=[str(ROOT/'x1d/tools'),str(CACHE/'python')]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication

def main():
    env=dict(os.environ)
    for k,v in {'TEMP':'tmp','TMP':'tmp','ZIG_GLOBAL_CACHE_DIR':'cache/global','ZIG_LOCAL_CACHE_DIR':'cache/local'}.items():
        p=BUILD/v;p.mkdir(parents=True,exist_ok=True);env[k]=str(p)
    sources=['native_af.c','native_adapter.c','native_config.c']
    cmd=[str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','arm-freestanding-eabi',
         '-mcpu=cortex_a9','-marm','-mfloat-abi=softfp','-mfpu=vfpv3-d16','-Oz','-g','-fno-lto',
         '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
         '-Wall','-Wextra','-Werror','-nostdlib','-Wl,--build-id=none','-Wl,-e,na_direction','-Wl,-T,'+str(HERE/'native_af.ld'),
         '-o',str(BUILD/'offline.elf'),*[str(HERE/p) for p in sources]]
    subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
    elf=ArmElf((BUILD/'offline.elf').read_bytes())
    symbols={s.name:s['st_value'] for s in elf.symbols if s['st_shndx']!='SHN_UNDEF'}
    assert not [s.name for s in elf.symbols if s['st_shndx']=='SHN_UNDEF' and s.name]
    base=0x800000;end=symbols['__payload_end'];payload=bytearray(end-base)
    for sec in elf.sections:
        if sec['sh_flags']&2:
            a,n=sec['sh_addr'],sec['sh_size'];assert base<=a<=a+n<=end
            if sec['sh_type']!='SHT_NOBITS':payload[a-base:a-base+n]=sec.data()
    farm=FarmApplication();assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    def branch(a,b,link=False):
        d=b-a-8;assert d%4==0 and -(1<<25)<=d<(1<<25)
        return (0xeb000000 if link else 0xea000000)|((d>>2)&0xffffff)
    # 只有两个局部拦截点；硬件采集 hook 未实现，不能由此生成装机清单。
    hooks=[(0x19d1b0,0xeb0004b1,branch(0x19d1b0,symbols['na_direction'],True)),
           (0x19d5c8,0xe92d4800,branch(0x19d5c8,symbols['na_peak_entry']))]
    for a,entry in [(0x1a1f64,'na_probe_speed'),(0x19d41c,'na_fast_speed'),(0x19d524,'na_fast_speed'),
                    (0x19d944,'na_fine_speed'),(0x19d9b4,'na_fine_speed')]:
        hooks.append((a,branch(a,0x1a0240,True),branch(a,symbols[entry],True)))
    hooks.append((0x19bbec,branch(0x19bbec,0x1a4950,True),branch(0x19bbec,symbols['na_cycle_reset'],True)))
    for a,old,_ in hooks:assert farm.word(a)==old,(hex(a),hex(farm.word(a)),hex(old))
    manifest={'kind':'offline-native-af-study','experimentalInstallReady':False,'hardwareRequests':0,
              'notInstallableReasons':['采样/位置/时间关联入口未接入','时延与减速能力未实测','链接地址仅供Unicorn'],
              'baseline_sha256':farm.sha256,'base':base,'end':end,'symbols':symbols,'emulatorOnlyHooks':hooks,
              'speed_words':[],'sensorModeWrites':[],'payload_sha256':hashlib.sha256(payload).hexdigest(),
              'source_sha256':{p:hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in sources+['native_af.h','native_config.h','native_af.ld','build_native_af.py']}}
    (BUILD/'offline.bin').write_bytes(payload)
    (BUILD/'offline-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'bytes':len(payload),'sha256':manifest['payload_sha256'],'experimentalInstallReady':False}))

if __name__=='__main__':main()
