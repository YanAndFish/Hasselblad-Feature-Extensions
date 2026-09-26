"""全程自有AF的固定RAM安装与显式恢复。默认report只读电脑文件，无USB。"""
import sys,json,struct,hashlib,argparse
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
import probe_loader as L
from farm_diagnostic_binary import FarmApplication

BUILD=L.HERE/"build/full-r2"
M=json.loads((BUILD/"manifest.json").read_text(encoding="utf-8"))
PAYLOAD=(BUILD/"candidate.bin").read_bytes()
assert hashlib.sha256(PAYLOAD).hexdigest()==M["payload_sha256"]
assert M["fullAfDecisionOwnership"] and M["searchSpeed"]==20000
assert M["base"]==0x2b2880 and M["end"]<=0x2b4000 and len(PAYLOAD)==M["end"]-M["base"]
assert M["stateAbi"]==3 and len(M["hooks"])==10
assert M["speed_words"]==[[a,5000,20000] for a in (0x2adc2c,0x2adc30,0x6bc9b0)]
STATE=M["symbols"]["af_state"]
# 专用进程内固定替换清单；不同时导入旧版切换器，不增加任意地址入口。
L.M=M;L.PAYLOAD=PAYLOAD
for a,old,new in M["speed_words"]:L.GUARDS[a]=(0xffffffff,old)
CODE=set(range(0x10a270,0x10a3ac,4))|set(range(0x10acac,0x10acb8,4))
for a in [x[0] for x in M["hooks"]]+[0x19d19c,0x1a02d8,0x19bbec,0x1a1f64,0x19dd70,0x199ccc,0x1a502c,0x1a5318]:
    CODE.update(range(a&~31,(a&~31)+32,4))
L.READ_SET=set(L.GUARDS)|CODE|set(range(L.BASE,M["end"],4))|{0x6badd0}
L.WRITE_SET={L.CB,L.ARG,L.SGIR}|set(range(L.BASE,M["end"],4))|{a for a,_,_ in M["hooks"]+M["speed_words"]}

def readiness():
    path=BUILD/"validation.json"
    if not path.exists():return False
    record=json.loads(path.read_text(encoding="utf-8"))
    if record.get("payloadSha256")!=M["payload_sha256"] or not record.get("passed"):return False
    files=("full_candidate_r2.c","full_candidate.ld","full_loader_r2.py","probe_loader.py","build_full_r2.py",
           "CodeTests/test_full_r2.py","CodeTests/test_full_loader_r2.py","CodeTests/validate_full_r2.py",
           "CodeTests/test_user_images.py","CodeTests/Fixtures/SyntheticAfCurves.json",
           "CodeTests/test_full_candidate.py","CodeTests/test_loader.py")
    return all(record.get("files",{}).get(name)==hashlib.sha256((L.HERE/name).read_bytes()).hexdigest() for name in files)

class FullLoader(L.Loader):
    def __init__(self,io=None):super().__init__(io or L.FixedIO(limit=11000))

    def idle(self):
        if self.io.read(0x6bb46c)&255:raise RuntimeError("AF not idle")
        if self.io.read(0x2adc78)&0xff00!=18<<8 or self.io.read(0x2adc8c)&255:
            raise RuntimeError("profile or override changed")

    def preflight(self,farm):
        assert not self.saved and farm.sha256==M["baseline_sha256"]
        self.io.exchange("version")
        for a,(mask,expected) in L.GUARDS.items():
            if self.io.read(a)&mask!=expected:raise RuntimeError("full preflight guard "+hex(a))
        for a in sorted(CODE):
            if self.io.read(a)!=farm.word(a):raise RuntimeError("full code baseline "+hex(a))
        for a in range(L.BASE,M["end"],4):
            if self.io.read(a)!=0:raise RuntimeError("full arena occupied "+hex(a))
        self.original={str(a):old for a,old,_ in M["hooks"]+M["speed_words"]}
        self.original.update({str(L.CB):L.ORIG_CB,str(L.ARG):L.ORIG_ARG})
        self.path=L.HERE/"recovery"/("full-r2-"+datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")+".json")
        if self.path.exists():raise RuntimeError("recovery name exists")
        self.record={"stage":"prepared","created":datetime.now().astimezone().isoformat(),"manifest":M,
            "original":self.original,"originalArena":{"start":L.BASE,"end":M["end"],"allZero":True},
            "probeExecuted":False,"installed":False,"armed":False,"inFlight":None,
            "algorithm":"full_owned","searchSpeed":20000,"fineSpeed":8000,"priorSpeed":5000,
            "automaticRestore":False,"automaticAf":False,"powerCycleClears":True,"preflightWrites":self.io.writes}
        self.save();self.saved=True
        return {"stage":"prepared","requests":self.io.requests,"writes":self.io.writes,"recovery":self.path.name}

    def install(self):
        self.idle()
        if not self.record.get("probeExecuted"):raise RuntimeError("probe required")
        if self.io.read(L.CB)!=L.ORIG_CB or self.io.read(L.ARG)!=L.ORIG_ARG or any(self.io.read(a) for a in range(L.BASE,L.BASE+64,4)):
            raise RuntimeError("probe restoration incomplete")
        self.record["stage"]="installing";self.save()
        for offset in range(0,len(PAYLOAD),4):self.write(M["base"]+offset,struct.unpack_from("<I",PAYLOAD,offset)[0])
        self.upload_thunk();self.sync_code(M["base"],len(PAYLOAD))
        for a,old,new in M["hooks"]:
            self.idle()
            if self.io.read(a)!=old:raise RuntimeError("hook changed")
            self.write(a,new);self.sync_code(a&~31,32)
        self.idle()
        for a,old,new in M["speed_words"]:
            if self.io.read(a)!=old:raise RuntimeError("speed changed")
            self.write(a,new)
        self.clean_scratch()
        self.record["stage"]="installed_disarmed";self.record["installed"]=True;self.save()
        self.verify(0)

    def verify(self,armed):
        checks={hex(a):self.io.read(a)==new for a,_,new in M["hooks"]+M["speed_words"]}
        checks.update({"callback":self.io.read(L.CB)==L.ORIG_CB,"argument":self.io.read(L.ARG)==L.ORIG_ARG,
            "scratchZero":all(self.io.read(a)==0 for a in range(L.BASE,M["base"],4)),
            "stateMagic":self.io.read(STATE)==M["stateMagic"],"stateAbi":self.io.read(STATE+4)==3,
            "armed":self.io.read(STATE+8)==armed,"canary":self.io.read(STATE+M["canaryOffset"])==M["canary"]})
        for offset in range(0,len(PAYLOAD),4):
            a=M["base"]+offset
            if STATE<=a<STATE+M["stateBytes"]:continue
            if self.io.read(a)!=struct.unpack_from("<I",PAYLOAD,offset)[0]:raise RuntimeError("payload verification mismatch")
        self.idle()
        if not all(checks.values()):raise RuntimeError("final verification mismatch")
        result={"at":datetime.now().astimezone().isoformat(),"checks":checks,"armedValue":armed,
                "searchSpeed":20000,"fineSpeed":8000,"afState":0,"staticPayloadVerified":True}
        self.record["verification"]=result;self.save();return result

    def arm(self):
        if not self.record.get("installed"):raise RuntimeError("installation required")
        self.idle();self.write(STATE+8,2)
        self.record.update({"stage":"full_owned_armed_until_restart","armed":True,"outerTimeoutDisabled":True})
        self.save()
        # 启用前已完整核验代码；启用后做固定入口/状态核验，仍不触发AF。
        for a,_,new in M["hooks"]+M["speed_words"]:
            if self.io.read(a)!=new:raise RuntimeError("armed hook/speed mismatch")
        if self.io.read(STATE+8)!=2 or self.io.read(STATE+M["canaryOffset"])!=M["canary"]:
            raise RuntimeError("armed state mismatch")
        self.idle();self.record["verification"]["armedValue"]=2
        self.record["verification"]["at"]=datetime.now().astimezone().isoformat();self.save()

    def hydrate(self,record_path):
        assert record_path.parent.resolve()==(L.HERE/"recovery").resolve()
        record=json.loads(record_path.read_text(encoding="utf-8"))
        if record["manifest"]!=M or record["algorithm"]!="full_owned":raise RuntimeError("record/build mismatch")
        expected={str(a):old for a,old,_ in M["hooks"]+M["speed_words"]}
        expected.update({str(L.CB):L.ORIG_CB,str(L.ARG):L.ORIG_ARG})
        if record["original"]!=expected or record["originalArena"]!={"start":L.BASE,"end":M["end"],"allZero":True}:
            raise RuntimeError("original recovery values mismatch")
        self.path=record_path;self.record=record;self.original=record["original"];self.saved=True

    def recovery_preflight(self,farm):
        """允许本记录的完整或中断安装；未知代码/状态与已消失的装载均拒绝。"""
        self.io.exchange("version");self.idle()
        for a,(mask,expected) in L.GUARDS.items():
            if a in (L.CB,L.ARG) or a in {x[0] for x in M["speed_words"]}:continue
            if self.io.read(a)&mask!=expected:raise RuntimeError("recovery guard "+hex(a))
        hooks={a:{old,new} for a,old,new in M["hooks"]}
        for a in sorted(CODE):
            if self.io.read(a) not in hooks.get(a,{farm.word(a)}):raise RuntimeError("unknown recovery code "+hex(a))
        for a in (L.CB,L.ARG)+tuple(x[0] for x in M["speed_words"]):
            if self.io.read(a) not in self.allowed[a]:raise RuntimeError("unknown recovery value "+hex(a))
        header=(self.io.read(STATE),self.io.read(STATE+4),self.io.read(STATE+M["canaryOffset"]))
        initialized=header==(M["stateMagic"],3,M["canary"])
        arena_nonzero=False
        for a in range(L.BASE,M["end"],4):
            if initialized and STATE<=a<STATE+M["stateBytes"]:continue
            v=self.io.read(a)
            arena_nonzero|=v!=0
            if a==L.DESC and v==L.MAGIC:continue
            if v not in self.allowed[a]:raise RuntimeError("unknown recovery arena "+hex(a))
        if initialized and self.io.read(STATE+8) not in (0,2):raise RuntimeError("unknown armed state")
        if self.record.get("installed") and not initialized and not arena_nonzero:
            raise RuntimeError("recorded installation disappeared; power cycle already clears RAM")

    def restore_algorithm(self,keep_speed=False):
        result=super().restore()
        if keep_speed:
            for a,_,new in M["speed_words"]:self.write(a,new)
            self.record["stage"]="factory_algorithm_speed20000_retained"
        else:self.record["stage"]="factory_algorithm_prior_speed5000_restored"
        for a,old,new in M["speed_words"]:
            if self.io.read(a)!=(new if keep_speed else old):raise RuntimeError("restored speed mismatch")
        self.record["restoredSearchSpeed"]=20000 if keep_speed else 5000
        self.record["finalRestorationReadback"]={hex(a):self.io.read(a) for a,_,_ in M["hooks"]+M["speed_words"]}
        self.save();return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("report","install","status","restore-algorithm","rollback"),nargs="?",default="report")
    parser.add_argument("--record")
    args=parser.parse_args();records=sorted((L.HERE/"recovery").glob("full-r2-*.json"))
    if args.record:
        if Path(args.record).name!=args.record or not args.record.startswith("full-r2-"):raise ValueError("record filename")
        path=L.HERE/"recovery"/args.record
    else:path=records[-1] if records else None
    if args.action=="report":
        print(json.dumps(json.loads(path.read_text(encoding="utf-8")) if path else
            {"stage":"ready_for_device_window" if readiness() else "offline_candidate_only","searchSpeed":20000,"fineSpeed":8000,"payloadBytes":len(PAYLOAD),
             "payloadSha256":M["payload_sha256"],"hardwareRequests":0},indent=2));return
    assert Path.cwd().resolve()==L.ROOT.resolve()
    loader=FullLoader();farm=FarmApplication()
    try:
        if args.action=="install":
            if records:raise RuntimeError("full installation already attempted; inspect recovery record")
            if not readiness():raise RuntimeError("exact build validation required before hardware")
            loader.preflight(farm);print("PREFLIGHT_COMPLETE",flush=True)
            loader.probe();print("PROBE_RESTORED",flush=True)
            loader.install();print("INSTALLED_DISARMED_VERIFIED",flush=True)
            loader.arm();print(json.dumps(loader.record["verification"]),flush=True)
        else:
            if path is None:raise RuntimeError("recovery record required")
            loader.hydrate(path)
            if args.action=="status":print(json.dumps(loader.verify(2 if loader.record["armed"] else 0)),flush=True)
            else:
                loader.recovery_preflight(farm)
                print(json.dumps(loader.restore_algorithm(keep_speed=args.action=="restore-algorithm")),flush=True)
    finally:
        if loader.saved:loader.save()
        print(json.dumps({"requests":loader.io.requests,"writes":loader.io.writes,"allHandlesClosed":loader.io.closed,
            "recovery":loader.path.name if loader.path else None}),flush=True)

if __name__=="__main__":main()
