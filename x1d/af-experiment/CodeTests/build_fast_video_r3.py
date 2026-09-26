"""160行视频任务构件的隔离模拟器链接，绝不输出可安装清单或导入设备模块。"""
import sys,os,json,hashlib,subprocess
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;MODULE=HERE.parent;ROOT=MODULE.parents[1]
CACHE=ROOT/'.research-cache/x1d-1.25.0'
sys.path[:0]=[str(ROOT/'x1d/tools'),str(CACHE/'python')]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication
assert Path.cwd().resolve()==ROOT.resolve()
out=MODULE/'build/fast-video-r3'
for name in ('','tmp','cache/global','cache/local'):(out/name).mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
for key,value in {'TEMP':'tmp','TMP':'tmp','ZIG_GLOBAL_CACHE_DIR':'cache/global','ZIG_LOCAL_CACHE_DIR':'cache/local'}.items():env[key]=str(out/value)
cmd=[str(CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','thumb-freestanding-eabi',
 '-mcpu=cortex_a9','-mfloat-abi=soft','-Oz','-g','-ffreestanding','-fno-builtin','-fno-stack-protector',
 '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-Wl,--build-id=none',
 '-Wl,--no-gc-sections','-Wl,-e,fast_video_wait','-Wl,-T,'+str(HERE/'fast_video_r3.ld'),'-o',str(out/'candidate.elf'),str(MODULE/'fast_video_r3.c')]
subprocess.run(cmd,cwd=MODULE,env=env,check=True,timeout=90)
elf=ArmElf((out/'candidate.elf').read_bytes());farm=FarmApplication()
symbols={s.name:s['st_value'] for s in elf.symbols if s['st_shndx']!='SHN_UNDEF'}
assert not [s.name for s in elf.symbols if s['st_shndx']=='SHN_UNDEF' and s.name]
base=0x300000;end=symbols['__payload_end'];payload=bytearray(end-base)
for sec in elf.sections:
 if sec['sh_flags']&2 and sec['sh_size']:
  a,n=sec['sh_addr'],sec['sh_size'];assert base<=a<a+n<=end
  if sec['sh_type']!='SHT_NOBITS':payload[a-base:a-base+n]=sec.data()
def branch(a,b,link=False):
 d=b-a-8;assert d%4==0 and -(1<<25)<=d<(1<<25)
 return (0xeb000000 if link else 0xea000000)|((d>>2)&0xffffff)
sites=[(0x1cdbac,'fast_video_wait',0x186b70),(0x1c9f08,'fast_video_pipeline',0x201e44),
 (0x21e67c,'fast_video_exposure',0x21d8b8),
 (0x230958,'fast_video_spi',0x234c64),(0x1c9614,'fast_videooff',None),
 (0x1c9934,'fast_videoon',None),(0x1f0e6c,'fast_video_roi',None)]
hooks=[]
for a,name,old_target in sites:
 assert symbols[name]%4==0
 assert farm.word(a)==(branch(a,old_target,True) if old_target else 0xe92d4800)
 hooks.append([a,farm.word(a),branch(a,symbols[name],old_target is not None)])
manifest={'farmSha256':farm.sha256,'base':base,'end':end,'symbols':symbols,'hooks':hooks,
 'stateBytes':next(s['st_size'] for s in elf.symbols if s.name=='fast_video_state'),
 'sha256':hashlib.sha256(payload).hexdigest(),'releaseReady':False,'simulatorOnly':True,'hardwareRequests':0}
(out/'candidate.bin').write_bytes(payload)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if k not in ('symbols','hooks')}))
