"""离线准备12000；不覆盖在机8000产物，不导入任何USB模块。"""
import sys,os,json,hashlib,subprocess
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CACHE=ROOT/".research-cache/x1d-1.25.0"
sys.path[:0]=[str(ROOT/"x1d/tools"),str(CACHE/"python")]
from binary import ArmElf
assert Path.cwd().resolve()==ROOT.resolve()
old=json.loads((HERE/"build/manifest.json").read_text(encoding="utf-8"))
source=(HERE/"candidate.c").read_bytes()
assert hashlib.sha256(source).hexdigest()==old["source_sha256"]
assert source.count(b"8000")==4
out=HERE/"build/speed12000"
for name in ("","tmp","cache/global","cache/local"):(out/name).mkdir(parents=True,exist_ok=True)
changed=source.replace(b"8000",b"12000")
(out/"candidate.c").write_bytes(changed)
env=dict(os.environ)
for key,value in {"TEMP":"tmp","TMP":"tmp","ZIG_GLOBAL_CACHE_DIR":"cache/global","ZIG_LOCAL_CACHE_DIR":"cache/local"}.items():env[key]=str(out/value)
cmd=[str(CACHE/"toolchain/zig-windows-x86_64-0.13.0/zig.exe"),"cc","-target","arm-freestanding-eabi","-mcpu=cortex_a9","-marm","-mfloat-abi=soft","-Oz","-g","-fno-lto","-ffreestanding","-fno-builtin","-fno-stack-protector","-fno-unwind-tables","-fno-asynchronous-unwind-tables","-nostdlib","-Wl,--build-id=none","-Wl,-e,state3_entry","-Wl,-T,"+str(HERE/"candidate.ld"),"-o",str(out/"candidate.elf"),str(out/"candidate.c")]
subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
elf=ArmElf((out/"candidate.elf").read_bytes())
symbols={s.name:s["st_value"] for s in elf.symbols if s["st_shndx"]!="SHN_UNDEF"}
assert not [s.name for s in elf.symbols if s["st_shndx"]=="SHN_UNDEF" and s.name]
assert all(symbols[k]==old["symbols"][k] for k in ("state3_entry","reset_entry","af_state","__payload_end")),"transition requires stable entries, state and arena"
payload=bytearray(old["end"]-old["base"])
for sec in elf.sections:
    if sec["sh_flags"]&2:
        a,n=sec["sh_addr"],sec["sh_size"]
        assert old["base"]<=a and a+n<=old["end"]
        if sec["sh_type"]!="SHT_NOBITS":payload[a-old["base"]:a-old["base"]+n]=sec.data()
before=(HERE/"build/candidate.bin").read_bytes()
assert hashlib.sha256(before).hexdigest()==old["payload_sha256"]
diff=[(old["base"]+i,before[i:i+4].hex(),payload[i:i+4].hex()) for i in range(0,len(payload),4) if before[i:i+4]!=payload[i:i+4]]
assert diff and all(a<old["symbols"]["af_state"] for a,_,_ in diff)
def branch(a,b,link=False):
    delta=b-a-8
    assert delta%4==0 and -(1<<25)<=delta<(1<<25)
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)
hooks=[[a,factory,branch(a,symbols[name],link)] for (a,factory,_),name,link in zip(old["hooks"],("state3_entry","reset_entry","af_send"),(False,False,True))]
manifest=dict(old)
manifest.update({"payload_sha256":hashlib.sha256(payload).hexdigest(),"source_sha256":hashlib.sha256(changed).hexdigest(),
    "speed_words":[[a,8000,12000] for a,_,_ in old["speed_words"]],"transitionFrom":old["payload_sha256"],
    "changedCodeWords":diff,"symbols":{k:symbols[k] for k in old["symbols"]},"hooks":hooks,"stableStateLayout":True})
(out/"candidate.bin").write_bytes(payload)
(out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"staged":str(out),"bytes":len(payload),"sha256":manifest["payload_sha256"],"changedCodeWordCount":len(diff),"changedFunctions":{k:[hex(v),hex(symbols[k])] for k,v in old["symbols"].items() if v!=symbols[k]}}))
