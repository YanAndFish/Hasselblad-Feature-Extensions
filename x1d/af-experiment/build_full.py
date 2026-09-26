"""离线构建全程自有AF，保留此前8000及12000前段候选产物。"""
import sys,os,json,hashlib,subprocess,struct
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];CACHE=ROOT/".research-cache/x1d-1.25.0"
sys.path[:0]=[str(ROOT/"x1d/tools"),str(CACHE/"python")]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication
assert Path.cwd().resolve()==ROOT.resolve()
if list((HERE/"recovery").glob("full-owned-*.json")):
    raise RuntimeError("full-owned recovery record exists; preserve its exact build and create a separately versioned candidate")
farm=FarmApplication();out=HERE/"build/full-owned"
for name in ("","tmp","cache/global","cache/local"):(out/name).mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
for key,value in {"TEMP":"tmp","TMP":"tmp","ZIG_GLOBAL_CACHE_DIR":"cache/global","ZIG_LOCAL_CACHE_DIR":"cache/local"}.items():env[key]=str(out/value)
cmd=[str(CACHE/"toolchain/zig-windows-x86_64-0.13.0/zig.exe"),"cc","-target","thumb-freestanding-eabi","-mcpu=cortex_a9","-mfloat-abi=soft","-Oz","-g","-fno-lto","-ffreestanding","-fno-builtin","-fno-stack-protector","-fno-unwind-tables","-fno-asynchronous-unwind-tables","-nostdlib","-Wl,--build-id=none","-Wl,-e,dispatch_entry","-Wl,-T,"+str(HERE/"full_candidate.ld"),"-o",str(out/"candidate.elf"),str(HERE/"full_candidate.c")]
subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=90)
elf=ArmElf((out/"candidate.elf").read_bytes())
symbols={s.name:s["st_value"] for s in elf.symbols if s["st_shndx"]!="SHN_UNDEF"}
assert not [s.name for s in elf.symbols if s["st_shndx"]=="SHN_UNDEF" and s.name]
base=0x2b2880;end=symbols["__payload_end"];payload=bytearray(end-base)
for sec in elf.sections:
    if sec["sh_flags"]&2:
        a,n=sec["sh_addr"],sec["sh_size"];assert base<=a and a+n<=end
        if sec["sh_type"]!="SHT_NOBITS":payload[a-base:a-base+n]=sec.data()
def branch(a,b,link=False):
    delta=b-a-8;assert delta%4==0 and -(1<<25)<=delta<(1<<25)
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)
sites=[(0x19bb94,"dispatch_entry",False),(0x19b770,"af_wait",True),(0x1a4950,"reset_entry",False),
       (0x1a0240,"speed_entry",False),(0x1a0378,"position_entry",False),(0x1a1cd8,"position_observer_entry",False),
       (0x1a1a98,"cv_observer_entry",False),(0x1a0ebc,"position_reply_entry",False),
       (0x1a0498,"near_entry",False),(0x1a06e4,"far_entry",False)]
assert farm.word(0x19bb94)==0xe30b346c and farm.word(0x19b770)==branch(0x19b770,0x189e4c,True)
for a,name,_ in sites:
    assert symbols[name]%4==0,"all installed branch targets are ARM entries"
    if a not in (0x19bb94,0x19b770):
        expected=0xe92d4810 if name=="position_observer_entry" else 0xe92d4830 if name=="position_reply_entry" else 0xe92d4800
        assert farm.word(a)==expected,(hex(a),hex(farm.word(a)))
state_size=next(s["st_size"] for s in elf.symbols if s.name=="af_state")
manifest={"baseline_sha256":farm.sha256,"payload_sha256":hashlib.sha256(payload).hexdigest(),
    "source_sha256":hashlib.sha256((HERE/"full_candidate.c").read_bytes()).hexdigest(),"base":base,"end":end,
    "symbols":symbols,"hooks":[[a,farm.word(a),branch(a,symbols[name],link)] for a,name,link in sites],
    "speed_words":[[a,12000,20000] for a in (0x2adc2c,0x2adc30,0x6bc9b0)],
    "stateBytes":state_size,"stateMagic":0x41464f57,"stateAbi":2,"canaryOffset":state_size-4,"canary":0x574f4641,
    "installationFrom":"factory_af_speed12000_zero_arena","fullAfDecisionOwnership":True,"searchSpeed":20000,"fineSpeed":3000}
(out/"candidate.bin").write_bytes(payload)
(out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"bytes":len(payload),"end":hex(end),"stateBytes":state_size,"sha256":manifest["payload_sha256"]}))
