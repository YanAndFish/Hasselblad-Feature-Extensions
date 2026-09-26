"""R3开发中候选，仅离线构建；未完成160行联动，不可安装。"""
import sys,os,json,hashlib,subprocess,struct
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];CACHE=ROOT/".research-cache/x1d-1.25.0"
sys.path[:0]=[str(ROOT/"x1d/tools"),str(CACHE/"python")]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication
assert Path.cwd().resolve()==ROOT.resolve()
if list((HERE/"recovery").glob("full-r3-*.json")):
    raise RuntimeError("full-r3 recovery record exists; preserve its exact build")
farm=FarmApplication();out=HERE/"build/full-r3"
for name in ("","tmp","cache/global","cache/local"):(out/name).mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
for key,value in {"TEMP":"tmp","TMP":"tmp","ZIG_GLOBAL_CACHE_DIR":"cache/global","ZIG_LOCAL_CACHE_DIR":"cache/local"}.items():env[key]=str(out/value)
cmd=[str(CACHE/"toolchain/zig-windows-x86_64-0.13.0/zig.exe"),"cc","-target","thumb-freestanding-eabi","-mcpu=cortex_a9","-mfloat-abi=soft","-Oz","-g","-fno-lto","-ffreestanding","-fno-builtin","-fno-stack-protector","-fno-unwind-tables","-fno-asynchronous-unwind-tables","-nostdlib","-Wl,--build-id=none","-Wl,-e,dispatch_entry","-Wl,-T,"+str(HERE/"full_candidate.ld"),"-o",str(out/"candidate.elf"),str(HERE/"full_candidate_r3.c")]
cmd[cmd.index('-Wl,-T,'+str(HERE/'full_candidate.ld'))]='-Wl,-T,'+str(HERE/'full_candidate_r3.ld')
cmd.append(str(HERE/'fast_video_r3.c'))
subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=90)
elf=ArmElf((out/"candidate.elf").read_bytes())
symbols={s.name:s["st_value"] for s in elf.symbols if s["st_shndx"]!="SHN_UNDEF"}
assert not [s.name for s in elf.symbols if s["st_shndx"]=="SHN_UNDEF" and s.name]
base=0x2b2880;end=symbols["__payload_end"];payload=bytearray(end-base);segments=[]
for sec in elf.sections:
    if sec["sh_flags"]&2:
        a,n=sec["sh_addr"],sec["sh_size"]
        if sec.name.startswith('.extra') and n:
            allowed={'.extra1':(0x19d1a0,0x19d5c8),'.extra2':(0x19d5cc,0x19d87c),
                '.extra3':(0x19d880,0x19d9cc),'.extra4':(0x19d9d0,0x19dd70),
                '.extra5':(0x19bfb8,0x19c310),'.extra6':(0x19c314,0x19c8ec),
                '.extra7':(0x19c8f0,0x19cc20),'.extra8':(0x19cc24,0x19cf5c)}
            lo,hi=allowed[sec.name];assert lo<=a<a+n<=hi
            name=sec.name[1:]+'.bin';blob=sec.data();(out/name).write_bytes(blob)
            segments.append({'name':sec.name,'file':name,'base':a,'end':a+n,'bytes':n,
                'sha256':hashlib.sha256(blob).hexdigest(),'originalSha256':hashlib.sha256(farm.read(a,n)).hexdigest()})
            continue
        if not n:continue
        assert base<=a and a+n<=end
        if sec["sh_type"]!="SHT_NOBITS":payload[a-base:a-base+n]=sec.data()
def branch(a,b,link=False):
    delta=b-a-8;assert delta%4==0 and -(1<<25)<=delta<(1<<25)
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)
sites=[(0x19bb94,"dispatch_entry",False),(0x19b770,"af_wait",True),(0x1a4950,"reset_entry",False),
       (0x1a0240,"speed_entry",False),(0x1a0378,"position_entry",False),(0x1a1cd8,"position_observer_entry",False),
       (0x1a1a98,"cv_observer_entry",False),(0x1a0ebc,"position_reply_entry",False),
       (0x1a0498,"near_entry",False),(0x1a06e4,"far_entry",False)]
assert farm.word(0x19bb94)==0xe30b346c and farm.word(0x19b770)==branch(0x19b770,0x189e4c,True)
assert farm.word(0x19871c)==0xe3a030cc and farm.word(0x198720)==0xe14b31b8
assert farm.word(0x1a1fdc)==0xe30c3b86
for a,name,_ in sites:
    assert symbols[name]%4==0,"all installed branch targets are ARM entries"
    if a not in (0x19bb94,0x19b770):
        expected=0xe92d4810 if name=="position_observer_entry" else 0xe92d4830 if name=="position_reply_entry" else 0xe92d4800
        assert farm.word(a)==expected,(hex(a),hex(farm.word(a)))
overlay_guards=[[a,farm.word(a),branch(a,symbols['unexpected_entry'])] for a in
    (0x19bfb4,0x19c310,0x19c8ec,0x19cc20,0x19d19c,0x19d5c8,0x19d87c,0x19d9cc)]
extra_hooks=[]
assert farm.word(0x19b960)==0xe51b3094
extra_hooks.append([0x19b960,farm.word(0x19b960),branch(0x19b960,symbols['early_entry'])])
for a,name,old_target in [(0x1cdbac,'fast_video_wait',0x186b70),(0x1c9f08,'fast_video_pipeline',0x201e44),
        (0x21e67c,'fast_video_exposure',0x21d8b8),
        (0x230958,'fast_video_spi',0x234c64),(0x1c9614,'fast_videooff',None),
        (0x1c9934,'fast_videoon',None),(0x1f0e6c,'fast_video_roi',None)]:
    assert symbols[name]%4==0
    assert farm.word(a)==(branch(a,old_target,True) if old_target else 0xe92d4800)
    extra_hooks.append([a,farm.word(a),branch(a,symbols[name],old_target is not None)])
state_size=next(s["st_size"] for s in elf.symbols if s.name=="af_state")
manifest={"baseline_sha256":farm.sha256,"payload_sha256":hashlib.sha256(payload).hexdigest(),
    "source_sha256":hashlib.sha256((HERE/"full_candidate_r3.c").read_bytes()).hexdigest(),"base":base,"end":end,
    "sources":{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in
        ('full_candidate_r3.c','fast_video_r3.c','fast_video_r3.h','full_candidate_r3.ld')},
    "symbols":symbols,"hooks":[[a,farm.word(a),branch(a,symbols[name],link)] for a,name,link in sites]+overlay_guards+extra_hooks+
        [[0x19871c,farm.word(0x19871c),branch(0x19871c,symbols['frame_tag_entry'])],
         [0x1a1fdc,farm.word(0x1a1fdc),branch(0x1a1fdc,symbols['position_pairer_entry'])]],
    "segments":segments,"overlayGuards":overlay_guards,"overlayLayoutReviewed":False,
    "speed_words":[[a,5000,20000] for a in (0x2adc2c,0x2adc30,0x6bc9b0)],
    "stateBytes":state_size,"stateMagic":0x41464f57,"stateAbi":6,"canaryOffset":state_size-4,"canary":0x574f4641,
    "fastStateBytes":next(s['st_size'] for s in elf.symbols if s.name=='fast_video_state'),"videoIntegration":"development",
    "installationFrom":"NOT_INSTALLABLE_DEVELOPMENT","releaseReady":False,"fast160Implemented":False,"fullAfDecisionOwnership":True,"searchSpeed":20000,"fineSpeed":8000}
digest=hashlib.sha256()
for address,blob in [(base,bytes(payload))]+[(s['base'],(out/s['file']).read_bytes()) for s in segments]:
    digest.update(struct.pack('<II',address,len(blob)));digest.update(blob)
digest.update(json.dumps({'hooks':manifest['hooks'],'speed_words':manifest['speed_words']},sort_keys=True,separators=(',',':')).encode())
manifest['artifact_sha256']=digest.hexdigest()
(out/"candidate.bin").write_bytes(payload)
(out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"bytes":len(payload),"extraBytes":sum(s['bytes'] for s in segments),"end":hex(end),"stateBytes":state_size,"sha256":manifest["payload_sha256"]}))
