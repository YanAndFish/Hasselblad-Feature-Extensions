"""本次具体实验入口。默认只读本地记录；硬件操作必须显式指定子命令。"""
import sys,json,argparse
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
import probe_loader as L

FORMER=L.HERE/"recovery/trial-20260910-205905.json"

def latest_record_name():
    names=sorted(p.name for p in (L.HERE/"recovery").glob("trial-*.json"))
    if not names:raise RuntimeError("no recovery record")
    return names[-1]

def report(record):
    keys=("stage","created","installed","armed","outerTimeoutDisabled","priorSpeed",
          "automaticSpeedRestore","requests","writes","allHandlesClosed","speedOnly","verifiedAfterInstall")
    return {k:record[k] for k in keys if k in record}

def load_record(name):
    path=(L.HERE/"recovery"/name).resolve()
    if path.parent!=(L.HERE/"recovery").resolve() or path.suffix!=".json":raise ValueError("fixed recovery directory required")
    return path,json.loads(path.read_text(encoding="utf-8"))

def attach(name):
    path,record=load_record(name)
    if record["manifest"]!=L.M:raise ValueError("record must match current build")
    loader=L.Loader();loader.path=path;loader.record=record;loader.original=record["original"]
    loader.io.requests=record["requests"];loader.io.writes=record["writes"]
    loader.saved=True
    return loader

def status(loader):
    a=L.M["symbols"]["af_state"]
    fields={n:i*4 for i,n in enumerate("magic abi armed until generation phase reason calls reversals confirmations".split())}
    fields.update({"acceptedSeen":48,"points":92,"returnPoints":96,"traceCount":176,"traceOverflow":180,"canary":568})
    result={n:loader.io.read(a+off) for n,off in fields.items()}
    result.update({"afState":loader.io.read(0x6bb46c)&255,"tick":loader.io.read(0x6badd0),
                   "speedWords":{hex(p):loader.io.read(p) for p,_,_ in L.M["speed_words"]},
                   "at":datetime.now().astimezone().isoformat()})
    return result

def install_retained():
    from farm_diagnostic_binary import FarmApplication
    if latest_record_name()!=FORMER.name:raise RuntimeError("retained installation was already attempted; inspect its record")
    former=json.loads(FORMER.read_text(encoding="utf-8"))
    loader=L.Loader()
    try:
        print(json.dumps(loader.preflight_retained(FarmApplication(),former)),flush=True)
        print(json.dumps(loader.probe()),flush=True)
        loader.install();loader.arm(until_restart=True)
        checks={hex(a):loader.io.read(a)==new for a,old,new in L.M["hooks"]+L.M["speed_words"]}
        observation=status(loader)
        if not all(checks.values()) or observation["armed"]!=2 or observation["magic"]!=0x41463552 or observation["canary"]!=0x52463541:
            raise RuntimeError("installation verification mismatch")
        loader.record["verifiedAfterInstall"]={"readback":checks,"status":observation}
        loader.record["automaticSpeedRestore"]=False
        loader.save()
        print(json.dumps({"recovery":loader.path.name,**report(loader.record)},ensure_ascii=False),flush=True)
    finally:
        if loader.saved:loader.save()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("report","install-retained","status","restore-algorithm"),nargs="?",default="report")
    parser.add_argument("--record",default=None)
    args=parser.parse_args()
    if args.record is None:args.record=latest_record_name()
    if args.action=="report":
        _,record=load_record(args.record);print(json.dumps(report(record),ensure_ascii=False,indent=2));return
    if args.action=="install-retained":install_retained();return
    loader=attach(args.record)
    try:
        loader.io.exchange("version")
        if args.action=="status":
            result=status(loader);loader.record.setdefault("observations",[]).append(result)
        else:
            # 此入口仅处理完整安装，未知/中断状态须根据 inFlight 作专门核对。
            if not loader.record.get("installed"):raise RuntimeError("algorithm is not recorded as installed")
            if loader.io.read(L.CB)!=L.ORIG_CB or loader.io.read(L.ARG)!=L.ORIG_ARG:raise RuntimeError("callback guard")
            for a,old,new in L.M["hooks"]+L.M["speed_words"]:
                if loader.io.read(a)!=new:raise RuntimeError("installed word guard")
            result=loader.restore()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:loader.save()

if __name__=="__main__":main()
