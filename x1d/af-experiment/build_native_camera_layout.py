"""只在仿真地址测量 ARM/Thumb 体积；不分配相机 RAM，没有硬件入口。"""
import hashlib,json,os,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
CACHE=ROOT/'.research-cache/x1d-1.25.0';BUILD=HERE/'build/native-camera-r1'
sys.path[:0]=[str(ROOT/'x1d/tools'),str(CACHE/'python')]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication

def main():
    env=dict(os.environ)
    for key,name in {'TEMP':'tmp','TMP':'tmp','ZIG_GLOBAL_CACHE_DIR':'cache/global','ZIG_LOCAL_CACHE_DIR':'cache/local'}.items():
        folder=BUILD/name;folder.mkdir(parents=True,exist_ok=True);env[key]=str(folder)
    sources=['native_af.c','native_adapter.c','native_config.c','native_camera_bridges.S']
    cmd=[str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','thumb-freestanding-eabi',
         '-mcpu=cortex_a9','-mthumb','-mfloat-abi=softfp','-mfpu=vfpv3-d16','-Oz','-g','-fno-lto',
         '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
         '-Wall','-Wextra','-Werror','-nostdlib','-Wl,--build-id=none','-Wl,-e,na_direction_bridge','-Wl,-T,'+str(HERE/'native_camera_layout.ld'),
         '-o',str(BUILD/'candidate.elf'),*[str(HERE/s) for s in sources]]
    subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
    elf=ArmElf((BUILD/'candidate.elf').read_bytes());symbols={s.name:s['st_value'] for s in elf.symbols if s['st_shndx']!='SHN_UNDEF'}
    assert not [s.name for s in elf.symbols if s['st_shndx']=='SHN_UNDEF' and s.name]
    base=0x800000;end=symbols['__payload_end'];payload=bytearray(end-base);sections=[]
    for sec in elf.sections:
        if sec['sh_flags']&2:
            a,n=sec['sh_addr'],sec['sh_size'];assert base<=a<=a+n<=end
            sections.append({'name':sec.name,'address':a,'bytes':n,'type':sec['sh_type']})
            if sec['sh_type']!='SHT_NOBITS':payload[a-base:a-base+n]=sec.data()
    farm=FarmApplication();assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    def branch(a,b,link=False):
        assert b%4==0;d=b-a-8;assert d%4==0 and -(1<<25)<=d<(1<<25)
        return (0xeb000000 if link else 0xea000000)|((d>>2)&0xffffff)
    hooks=[(0x19d1b0,0xeb0004b1,branch(0x19d1b0,symbols['na_direction_bridge'],True)),
           (0x19d5c8,0xe92d4800,branch(0x19d5c8,symbols['na_peak_entry']))]
    for a,name in [(0x1a1f64,'na_probe_bridge'),(0x19d41c,'na_fast_bridge'),(0x19d524,'na_fast_bridge'),
                   (0x19d944,'na_fine_bridge'),(0x19d9b4,'na_fine_bridge')]:
        hooks.append((a,branch(a,0x1a0240,True),branch(a,symbols[name],True)))
    hooks.append((0x19bbec,branch(0x19bbec,0x1a4950,True),branch(0x19bbec,symbols['na_reset_bridge'],True)))
    for a,old,_ in hooks:assert farm.word(a)==old
    for name,target in [('na_direction_bridge','na_direction'),('na_probe_bridge','na_probe_speed'),
                        ('na_fast_bridge','na_fast_speed'),('na_fine_bridge','na_fine_speed'),('na_reset_bridge','na_cycle_reset')]:
        assert symbols[target]&1
        assert struct.unpack_from('<3I',payload,symbols[name]-base)==(0xe59fc000,0xe12fff1c,symbols[target])
    manifest={'kind':'offline-thumb-size-study','experimentalInstallReady':False,'hardwareRequests':0,
              'notInstallableReasons':['链接地址仅供仿真，未分配共存 RAM','真实采样/位置/时刻关联入口未接入',
                  '当前镜头时延与减速能力未实测','本版装载事务、生命周期与恢复验证尚未完成'],
              'baseline_sha256':farm.sha256,'base':base,'end':end,'state_start':symbols['__state_start'],
              'sections':sections,'historicalArenaBytes':0x2b3f40-0x2b2880,
              'historicalArenaConflict':'该范围与机械引闪采集重叠，不可据此安装',
              'symbols':symbols,'emulatorOnlyHooks':hooks,'speed_words':[],'sensorModeWrites':[],
              'payload_sha256':hashlib.sha256(payload).hexdigest(),
              'source_sha256':{p:hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in sources+['native_af.h','native_config.h','native_camera_layout.ld','build_native_camera_layout.py']}}
    (BUILD/'candidate.bin').write_bytes(payload)
    (BUILD/'layout-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'bytes':len(payload),'sections':sections,'payloadSha256':manifest['payload_sha256'],'experimentalInstallReady':False}))

if __name__=='__main__':main()
