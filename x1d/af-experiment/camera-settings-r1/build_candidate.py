"""构建共享 AF 核心和原厂采样记录；地址重定位不证明相机内存归属。"""
import argparse,hashlib,json,os,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
assert Path.cwd().resolve()==ROOT.resolve()
CACHE=ROOT/'.research-cache/x1d-1.25.0'
sys.path[:0]=[str(ROOT/'x1d/tools'),str(CACHE/'python')]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication

def branch(a,b,link=False):
    d=b-a-8;assert b%4==0 and d%4==0 and -(1<<25)<=d<(1<<25)
    return (0xeb000000 if link else 0xea000000)|((d>>2)&0xffffff)

def build(base=0x800000):
    if base%32 or not (base==0x800000 or 0x2bacb0<=base<=0x6baca0-32768):
        raise ValueError('not a candidate heap payload base')
    out=HERE/'build'/f'{base:08x}'
    env=dict(os.environ)
    for key,name in {'TEMP':'tmp','TMP':'tmp','ZIG_GLOBAL_CACHE_DIR':'cache/global','ZIG_LOCAL_CACHE_DIR':'cache/local'}.items():
        folder=out/name;folder.mkdir(parents=True,exist_ok=True);env[key]=str(folder)
    sources=['native_af.c','native_adapter.c','native_config.c','native_camera_bridges.S','native_capture.c','native_capture_bridges.S','settings_receiver.c','rolling_direction.c']
    layout=out/'capture.ld'
    layout.write_text('ENTRY(na_direction_bridge)\nSECTIONS { . = '+hex(base)+'; .text : { KEEP(*(.text.camera_bridges)) KEEP(*(.text.capture_bridges)) KEEP(*(.text.na_api)) *(.text*) } .rodata : { *(.rodata*) } . = ALIGN(32); __state_start = .; .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } . = ALIGN(32); __payload_end = .; /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } ASSERT(. <= '+hex(base+32768)+',"AF allocation capacity exceeded") }\n',encoding='ascii')
    cmd=[str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','thumb-freestanding-eabi',
         '-mcpu=cortex_a9','-mthumb','-mfloat-abi=softfp','-mfpu=vfpv3-d16','-Oz','-g','-fno-lto',
         '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
         '-Wall','-Wextra','-Werror','-nostdlib','-Wl,--build-id=none','-Wl,-e,na_direction_bridge','-Wl,-T,'+str(layout),
         '-o',str(out/'candidate.elf'),*[str(HERE/s) for s in sources]]
    subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
    elf=ArmElf((out/'candidate.elf').read_bytes());symbols={s.name:s['st_value'] for s in elf.symbols if s['st_shndx']!='SHN_UNDEF'}
    assert not [s.name for s in elf.symbols if s['st_shndx']=='SHN_UNDEF' and s.name]
    end=symbols['__payload_end'];payload=bytearray(end-base);sections=[]
    for sec in elf.sections:
        if sec['sh_flags']&2:
            a,n=sec['sh_addr'],sec['sh_size'];assert base<=a<=a+n<=end
            sections.append({'name':sec.name,'address':a,'bytes':n,'type':sec['sh_type']})
            if sec['sh_type']!='SHT_NOBITS':payload[a-base:a-base+n]=sec.data()
    farm=FarmApplication();assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    hooks=[(0x19d1b0,0xeb0004b1,branch(0x19d1b0,symbols['na_direction_bridge'],True)),
           (0x19d5c8,0xe92d4800,branch(0x19d5c8,symbols['na_peak_entry']))]
    for a,name in [(0x1a1f64,'nc_probe_bridge'),(0x19d41c,'nc_fast_bridge'),(0x19d524,'nc_fast_bridge'),
                   (0x19d944,'nc_fine_bridge'),(0x19d9b4,'nc_fine_bridge')]:
        hooks.append((a,branch(a,0x1a0240,True),branch(a,symbols[name],True)))
    hooks.append((0x19bbec,branch(0x19bbec,0x1a4950,True),branch(0x19bbec,symbols['nc_reset_bridge'],True)))
    for a,old,name in [(0x1f0d2c,0xe55b3019,'nc_raw_entry'),(0x1a1b48,0xe7831102,'nc_cv_entry'),
                       (0x1a2130,0xe1c320b0,'nc_position_entry'),(0x1a3068,0xe1c320b0,'nc_accepted_entry')]:
        hooks.append((a,old,branch(a,symbols[name])))
    hooks.append((0x1e22b4,branch(0x1e22b4,0x1e1e1c,True),branch(0x1e22b4,symbols['as_receive_bridge'],True)))
    hooks.append((0x1a0498,0xe92d4800,branch(0x1a0498,symbols['as_near_limit_bridge'])))
    for a,old,_ in hooks:assert farm.word(a)==old,(hex(a),hex(farm.word(a)),hex(old))
    for name,target in [('na_direction_bridge','na_direction'),('nc_probe_bridge','nc_probe_speed'),
                        ('nc_fast_bridge','nc_fast_speed'),('nc_fine_bridge','nc_fine_speed'),('nc_reset_bridge','nc_cycle_reset')]:
        assert symbols[target]&1
        assert struct.unpack_from('<3I',payload,symbols[name]-base)==(0xe59fc000,0xe12fff1c,symbols[target])
    # 默认三个阶段均跟随原厂命令；新判向默认关闭，保留远端优先。控制字段不靠主机写入任意状态来绕过采样/标定门槛。
    config=struct.pack('<10I',0x33435441,3,75,1,0,0,0,2,65534,65534);checksum=2166136261
    for value in config:checksum=((checksum^value)*16777619)&0xffffffff
    config+=struct.pack('<I',checksum)
    bank=struct.pack('<III',2,0,2)+config+config
    offset=symbols['na_config_bank']-base;payload[offset:offset+len(bank)]=bank
    manifest={'kind':'native-af-camera-settings-candidate','experimentalInstallReady':False,'hardwareRequests':0,
        'notInstallableReasons':['没有当前相机分配证明、缓存证明及完整装载事务',
            '真实同帧/采样时间与制动标定仍待采样核对；新算法没有获实机效果验证'],
        'baseline_sha256':farm.sha256,'base':base,'end':end,'state_start':symbols['__state_start'],
        'sections':sections,'symbols':symbols,'emulatorOnlyHooks':hooks,'speed_words':[],'sensorModeWrites':[],
        'requestedHeapCapacity':32768,'initialSpeedOverrides':True,'initialPredictionActuation':False,
        'capture':{'abi':2,'recordWords':9,'headerWords':12,'rawCapacity':64,'afCapacity':128,'controlCapacity':32,
            'tickMeaning':'本机入口观察 tick，不是曝光/镜头采样时刻','rawSingleWriter':'CV 读取 IRQ 路径',
            'afSingleWriter':'AF_SERVICE (0x19b284)','controlSingleWriter':'AF_SERVICE_SM (0x19b708)'},
        'payload_sha256':hashlib.sha256(payload).hexdigest(),
        'source_sha256':{p:hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in sources+['native_af.h','native_config.h','native_capture.h','settings_wire.h','rolling_direction.h','build_candidate.py']}}
    (out/'candidate.bin').write_bytes(payload)
    (out/'capture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'bytes':len(payload),'sections':sections,'payloadSha256':manifest['payload_sha256'],'experimentalInstallReady':False}))
    return manifest,out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=lambda x:int(x,0),default=0x800000)
    build(p.parse_args().base)
