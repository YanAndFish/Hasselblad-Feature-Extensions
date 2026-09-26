"""本轮RAM补丁失效后，从原厂空区域完整安装12000；默认仅看本地记录。"""
import sys,json,hashlib,argparse
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
import probe_loader as L

# 此独立进程使用已经验证的通用装载顺序，配置为新二进制和真实原厂5000基线。
# 固定读写地址集合与原装载器完全相同，仅允许的代码字和速度值随固定产物变化。
OLD=L.M
TARGET=json.loads((L.HERE/"build/speed12000/manifest.json").read_text(encoding="utf-8"))
PAYLOAD=(L.HERE/"build/speed12000/candidate.bin").read_bytes()
assert hashlib.sha256(PAYLOAD).hexdigest()==TARGET["payload_sha256"]
assert TARGET["transitionFrom"]==OLD["payload_sha256"]
assert TARGET["base"]==OLD["base"] and TARGET["end"]==OLD["end"]
assert TARGET["symbols"]["af_state"]==OLD["symbols"]["af_state"]
assert [a for a,_,_ in TARGET["hooks"]]==[a for a,_,_ in OLD["hooks"]]
assert TARGET["speed_words"]==[[a,8000,12000] for a,_,_ in OLD["speed_words"]]
TARGET["speed_words"]=[[a,5000,12000] for a,_,_ in TARGET["speed_words"]]
TARGET["installationFrom"]="factory_hooks_5000_zero_arena"
L.M=TARGET;L.PAYLOAD=PAYLOAD
assert all(L.GUARDS[a]==(0xffffffff,5000) for a,_,_ in TARGET["speed_words"])

def report(record):
    return {k:record[k] for k in ("stage","created","activeSpeed","installed","armed","outerTimeoutDisabled",
        "verifiedAfterInstall","requests","writes","allHandlesClosed","inFlight") if k in record}

def verify(loader):
    state=TARGET["symbols"]["af_state"]
    checks={hex(a):loader.io.read(a)==new for a,_,new in TARGET["hooks"]+TARGET["speed_words"]}
    for a,value in ((state,0x41463552),(state+4,1),(state+8,2),(state+568,0x52463541),
                    (L.CB,L.ORIG_CB),(L.ARG,L.ORIG_ARG)):
        checks[hex(a)]=loader.io.read(a)==value
    checks["scratchZero"]=all(loader.io.read(a)==0 for a in range(L.BASE,TARGET["base"],4))
    afstate=loader.io.read(0x6bb46c)&255
    if not all(checks.values()) or afstate:raise RuntimeError("final installation verification mismatch")
    return {"at":datetime.now().astimezone().isoformat(),"readback":checks,"afState":afstate,"armed":2,
            "speedWords":{hex(a):new for a,_,new in TARGET["speed_words"]}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("report","install"),nargs="?",default="report")
    args=parser.parse_args()
    records=[]
    for path in sorted((L.HERE/"recovery").glob("trial-*.json")):
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("manifest",{}).get("installationFrom")==TARGET["installationFrom"]:records.append((path,data))
    if args.action=="report":
        print(json.dumps(report(records[-1][1]) if records else {"stage":"prepared_offline_only","targetSpeed":12000},indent=2));return
    if records:raise RuntimeError("full installation already attempted; inspect recovery before further device access")
    assert Path.cwd().resolve()==L.ROOT.resolve()
    from farm_diagnostic_binary import FarmApplication
    loader=L.Loader()
    try:
        print(json.dumps(loader.preflight(FarmApplication())),flush=True)
        loader.record.update({"activeSpeed":5000,"requestedSpeed":12000,"previousTemporaryPatchAbsent":True,
            "automaticSpeedRestore":False,"priorKnownRecord":"trial-20260910-211546.json"})
        loader.save()
        print(json.dumps(loader.probe()),flush=True)
        loader.install();loader.arm(until_restart=True)
        loader.record["verifiedAfterInstall"]=verify(loader)
        loader.record["activeSpeed"]=12000;loader.save()
        print(json.dumps({"recovery":loader.path.name,**report(loader.record)},indent=2),flush=True)
    finally:
        if loader.saved:loader.save()

if __name__=="__main__":main()
