"""本轮8000→12000的固定RAM切换。默认仅报告本地产物；导入不连接设备。"""
import sys,json,hashlib,struct,argparse
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
import probe_loader as L

NEW_DIR=L.HERE/"build/speed12000"
NEW=json.loads((NEW_DIR/"manifest.json").read_text(encoding="utf-8"))
BLOB=(NEW_DIR/"candidate.bin").read_bytes()
FORMER=L.HERE/"recovery/trial-20260910-211546.json"
STATE=L.M["symbols"]["af_state"]
assert NEW["transitionFrom"]==L.M["payload_sha256"]
assert hashlib.sha256(BLOB).hexdigest()==NEW["payload_sha256"]
assert NEW["base"]==L.M["base"] and NEW["end"]==L.M["end"] and NEW["symbols"]["af_state"]==STATE
assert NEW["baseline_sha256"]==L.M["baseline_sha256"]
assert NEW["speed_words"]==[[a,8000,12000] for a,_,_ in L.M["speed_words"]]
assert BLOB[STATE-NEW["base"]:]==L.PAYLOAD[STATE-NEW["base"]:]
CHANGES=[(NEW["base"]+i,struct.unpack_from("<I",L.PAYLOAD,i)[0],struct.unpack_from("<I",BLOB,i)[0])
         for i in range(0,len(BLOB),4) if BLOB[i:i+4]!=L.PAYLOAD[i:i+4]]
assert [[a,struct.pack("<I",old).hex(),struct.pack("<I",new).hex()] for a,old,new in CHANGES]==NEW["changedCodeWords"]
assert all(a<STATE for a,_,_ in CHANGES)

def words(blob):
    return {NEW["base"]+off:struct.unpack_from("<I",blob,off)[0] for off in range(0,len(blob),4)}

class SpeedUpdate(L.Loader):
    def __init__(self,io=None):
        super().__init__(io)
        for a,old,new in CHANGES:self.allowed[a].update((old,new))
        for a,old,new in NEW["hooks"]:self.allowed[a].update((old,new))
        for a,old,new in NEW["speed_words"]:self.allowed[a]={old,new}

    def idle(self):
        if self.io.read(0x6bb46c)&255:raise RuntimeError("AF must be idle")
        if self.io.read(0x2adc78)&0xff00!=18<<8 or self.io.read(0x2adc8c)&255:
            raise RuntimeError("lens profile or speed override changed")

    def preflight(self,farm,former):
        assert not self.saved and farm.sha256==L.M["baseline_sha256"]
        assert former["manifest"]==L.M and former["installed"] and former["armed"]
        assert former["stage"]=="armed_until_restart" and former.get("inFlight") is None
        assert former["allHandlesClosed"] and former["verifiedAfterInstall"]["status"]["armed"]==2
        self.io.exchange("version")
        overrides={a:new for a,_,new in L.M["hooks"]+L.M["speed_words"]}
        for a,(mask,expected) in L.GUARDS.items():
            if self.io.read(a)&mask!=overrides.get(a,expected):raise RuntimeError("update guard "+hex(a))
        code=set(range(0x10a270,0x10a3ac,4))|set(range(0x10acac,0x10acb8,4))
        for a,_,_ in L.M["hooks"]:code.update(range(a&~31,(a&~31)+32,4))
        for a in sorted(code):
            if self.io.read(a)!=overrides.get(a,farm.word(a)):raise RuntimeError("update code guard "+hex(a))
        expected=words(L.PAYLOAD)
        for a in range(L.BASE,L.M["end"],4):
            if STATE<=a<STATE+572:continue
            if self.io.read(a)!=expected.get(a,0):raise RuntimeError("8000 payload changed "+hex(a))
        for a,v in ((STATE,0x41463552),(STATE+4,1),(STATE+8,2),(STATE+568,0x52463541)):
            if self.io.read(a)!=v:raise RuntimeError("8000 state guard "+hex(a))
        self.idle()
        self.path=L.HERE/"recovery"/("speed12000-"+datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")+".json")
        if self.path.exists():raise RuntimeError("recovery name exists")
        self.original={str(a):old for a,old,_ in NEW["hooks"]+NEW["speed_words"]}
        self.original.update({str(L.CB):L.ORIG_CB,str(L.ARG):L.ORIG_ARG})
        self.record={"stage":"prepared_from_armed_8000","created":datetime.now().astimezone().isoformat(),
            "manifest":NEW,"previousManifest":L.M,"previousRecord":FORMER.name,
            "original":self.original,"previousArmed":2,"installed":True,"armed":True,
            "outerTimeoutDisabled":True,"automaticSpeedRestore":False,"directionAlgorithmChanged":False,
            "priorRequests":former["requests"],"priorWrites":former["writes"],"inFlight":None}
        self.save();self.saved=True
        return {"stage":self.record["stage"],"requests":self.io.requests,"writes":self.io.writes,"recovery":self.path.name}

    def stage(self,name):
        self.record["stage"]=name;self.save()

    def unhook(self):
        self.idle();self.write(STATE+8,0);self.record["armed"]=False;self.idle()
        self.upload_thunk()
        for a,factory,_ in L.M["hooks"]:
            self.write(a,factory);self.sync_code(a&~31,32)
        self.record["installed"]=False;self.stage("factory_entries_active")

    def verify(self,manifest):
        checks={hex(a):self.io.read(a)==new for a,_,new in manifest["hooks"]+manifest["speed_words"]}
        for a,v in ((STATE,0x41463552),(STATE+4,1),(STATE+8,2),(STATE+568,0x52463541),
                    (L.CB,L.ORIG_CB),(L.ARG,L.ORIG_ARG)):
            checks[hex(a)]=self.io.read(a)==v
        checks["scratchZero"]=all(self.io.read(a)==0 for a in range(L.BASE,L.BASE+128,4))
        self.idle()
        if not all(checks.values()):raise RuntimeError("completed update readback mismatch")
        return {"at":datetime.now().astimezone().isoformat(),"readback":checks,"afState":0,"armed":2}

    def switch(self,target_new):
        """由预检后的更新或已核对的显式回退调用。通信异常后立即退出，不自动重试。"""
        self.stage("switching_to_12000" if target_new else "rolling_back_to_8000")
        self.unhook();self.idle()
        for a,old,new in CHANGES:self.write(a,new if target_new else old)
        self.sync_code(NEW["base"],len(BLOB));self.stage("code_12000" if target_new else "code_8000")
        target=NEW if target_new else L.M
        for a,_,new in target["speed_words"]:self.write(a,new)
        self.idle()
        for a,factory,new in target["hooks"]:
            if self.io.read(a)!=factory:raise RuntimeError("factory hook changed during switch")
            self.write(a,new);self.sync_code(a&~31,32)
        self.clean_scratch();self.idle();self.write(STATE+8,2)
        self.record.update({"installed":True,"armed":True,"activeManifest":target,
                            "activeSpeed":12000 if target_new else 8000})
        self.record["verification"]=self.verify(target)
        self.stage("speed12000_armed_until_restart" if target_new else "prior8000_armed_until_restart")
        return self.record["verification"]

    def validate_recovery(self,farm):
        """固定新旧代码/值的集合核对；不将未知修改覆盖成已知版本。"""
        assert self.saved and self.record["manifest"]==NEW and self.record["previousManifest"]==L.M
        assert farm.sha256==L.M["baseline_sha256"]
        self.io.exchange("version");self.idle()
        flexible={L.CB,L.ARG}|{a for a,_,_ in NEW["hooks"]+NEW["speed_words"]}
        for a,(mask,expected) in L.GUARDS.items():
            value=self.io.read(a)
            if a in flexible:
                if value not in self.allowed[a]:raise RuntimeError("unknown recovery value "+hex(a))
            elif value&mask!=expected:raise RuntimeError("recovery guard "+hex(a))
        code=set(range(0x10a270,0x10a3ac,4))|set(range(0x10acac,0x10acb8,4))
        for a,_,_ in NEW["hooks"]:code.update(range(a&~31,(a&~31)+32,4))
        for a in sorted(code):
            value=self.io.read(a)
            if value not in (self.allowed[a] if a in flexible else {farm.word(a)}):
                raise RuntimeError("recovery code guard "+hex(a))
        old_words,new_words=words(L.PAYLOAD),words(BLOB)
        for a in range(L.BASE,NEW["end"],4):
            if STATE<=a<STATE+572:continue
            permitted={old_words[a],new_words[a]} if a in old_words else self.allowed[a]
            if self.io.read(a) not in permitted:raise RuntimeError("unknown recovery RAM "+hex(a))
        for a,v in ((STATE,0x41463552),(STATE+4,1),(STATE+568,0x52463541)):
            if self.io.read(a)!=v:raise RuntimeError("recovery state guard")
        if self.io.read(STATE+8) not in (0,2):raise RuntimeError("unknown enable state")

def summary(record):
    return {k:record[k] for k in ("stage","created","activeSpeed","installed","armed","verification",
            "requests","writes","allHandlesClosed","inFlight") if k in record}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("report","install","rollback8000"),default="report",nargs="?")
    parser.add_argument("--record")
    args=parser.parse_args()
    if args.action=="report":
        paths=sorted((L.HERE/"recovery").glob("speed12000-*.json"))
        print(json.dumps(summary(json.loads(paths[-1].read_text(encoding="utf-8"))) if paths else
              {"stage":"prepared_offline_only","targetSpeed":12000,"changedCodeWords":len(CHANGES),"sha256":NEW["payload_sha256"]},indent=2));return
    assert Path.cwd().resolve()==L.ROOT.resolve()
    from farm_diagnostic_binary import FarmApplication
    loader=SpeedUpdate()
    try:
        if args.action=="install":
            if args.record or any((L.HERE/"recovery").glob("speed12000-*.json")):
                raise RuntimeError("update already attempted; inspect saved record before further device operations")
            former=json.loads(FORMER.read_text(encoding="utf-8"))
            print(json.dumps(loader.preflight(FarmApplication(),former)),flush=True)
            loader.switch(True)
        else:
            if not args.record:raise RuntimeError("explicit recovery filename required")
            path=(L.HERE/"recovery"/args.record).resolve()
            if path.parent!=(L.HERE/"recovery").resolve() or not path.name.startswith("speed12000-") or path.suffix!=".json":
                raise RuntimeError("fixed recovery path required")
            loader.path=path;loader.record=json.loads(path.read_text(encoding="utf-8"))
            loader.original=loader.record["original"];loader.saved=True
            loader.io.requests=loader.record["requests"];loader.io.writes=loader.record["writes"]
            loader.validate_recovery(FarmApplication());loader.switch(False)
        print(json.dumps({"recovery":loader.path.name,**summary(loader.record)},indent=2),flush=True)
    finally:
        if loader.saved:loader.save()

if __name__=="__main__":main()
