"""仅在获授权的 af-experiment 内构建；不接触相机。"""
import os, sys, json, hashlib, subprocess
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CACHE=ROOT/".research-cache/x1d-1.25.0"
sys.path[:0]=[str(ROOT/"x1d/tools"),str(CACHE/"python")]
from binary import ArmElf
assert Path.cwd().resolve().is_relative_to(ROOT.resolve())
for p in ("build","build/tmp","build/cache/global","build/cache/local","recovery"):
    (HERE/p).mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
for k,v in {"TEMP":"build/tmp","TMP":"build/tmp","ZIG_GLOBAL_CACHE_DIR":"build/cache/global","ZIG_LOCAL_CACHE_DIR":"build/cache/local"}.items():env[k]=str(HERE/v)
cmd=[str(CACHE/"toolchain/zig-windows-x86_64-0.13.0/zig.exe"),"cc","-target","arm-freestanding-eabi","-mcpu=cortex_a9","-marm","-mfloat-abi=soft","-Oz","-g","-fno-lto","-ffreestanding","-fno-builtin","-fno-stack-protector","-fno-unwind-tables","-fno-asynchronous-unwind-tables","-nostdlib","-Wl,--build-id=none","-Wl,-e,state3_entry","-Wl,-T,"+str(HERE/"candidate.ld"),"-o",str(HERE/"build/candidate.elf"),str(HERE/"candidate.c")]
subprocess.run(cmd,cwd=HERE,env=env,check=True,timeout=60)
elf=ArmElf((HERE/"build/candidate.elf").read_bytes())
symbols={s.name:s["st_value"] for s in elf.symbols if s["st_shndx"]!="SHN_UNDEF"}
required=("state3_entry","reset_entry","af_decide","af_reset","af_state","af_send","__payload_end")
assert all(k in symbols for k in required)
assert not [s.name for s in elf.symbols if s["st_shndx"]=="SHN_UNDEF" and s.name]
start=0x2b2880; end=symbols["__payload_end"]
assert start<end<=0x2b4000
payload=bytearray(end-start)
for sec in elf.sections:
    if sec["sh_flags"]&2:
        a,n=sec["sh_addr"],sec["sh_size"]
        assert start<=a and a+n<=end
        if sec["sh_type"]!="SHT_NOBITS":payload[a-start:a-start+n]=sec.data()
def branch(a,b,link=False):
    delta=b-a-8
    assert delta%4==0 and -(1<<25)<=delta<(1<<25)
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)
hooks=[(0x19d19c,0xe92d4810,branch(0x19d19c,symbols["state3_entry"])),
       (0x1a4950,0xe92d4800,branch(0x1a4950,symbols["reset_entry"])),
       (0x1a02d8,0xeb011f7c,branch(0x1a02d8,symbols["af_send"],True))]
manifest={"baseline_sha256":"317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca",
 "base":start,"end":end,"payload_sha256":hashlib.sha256(payload).hexdigest(),
 "symbols":{k:symbols[k] for k in required},"hooks":hooks,
 "speed_words":[[0x2adc2c,5000,8000],[0x2adc30,5000,8000],[0x6bc9b0,5000,8000]],
 "source_sha256":hashlib.sha256((HERE/"candidate.c").read_bytes()).hexdigest()}
(HERE/"build/candidate.bin").write_bytes(payload)
(HERE/"build/manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"bytes":len(payload),"base":hex(start),"end":hex(end),"sha256":manifest["payload_sha256"]}))

