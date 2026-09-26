"""重启后优先仅写三处12000速度；不装载算法、不执行AF。默认本地报告。"""
import sys,json,argparse
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
import probe_loader as L
SPEEDS=(0x2adc2c,0x2adc30,0x6bc9b0)

class SpeedOnly(L.Loader):
    def __init__(self,io=None):
        super().__init__(io)
        self.allowed={a:{5000,12000} for a in SPEEDS}

    def preflight(self):
        assert not self.saved
        self.io.exchange("version")
        state=L.M["symbols"]["af_state"]
        guards={a:old for a,old,_ in L.M["hooks"]}
        guards.update({a:5000 for a in SPEEDS})
        guards.update({state:0,state+4:0,state+8:0,state+568:0,L.CB:L.ORIG_CB,L.ARG:L.ORIG_ARG})
        words={}
        for a,expected in guards.items():
            value=self.io.read(a);words[hex(a)]=value
            if value!=expected:raise RuntimeError("speed-only baseline guard "+hex(a))
        self.idle()
        self.path=L.HERE/"recovery"/("speed-only12000-"+datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")+".json")
        if self.path.exists():raise RuntimeError("recovery name exists")
        self.original={str(a):5000 for a in SPEEDS}
        self.record={"stage":"prepared","created":datetime.now().astimezone().isoformat(),"original":self.original,
            "preflightReadback":words,"preflightWrites":self.io.writes,"algorithm":"factory",
            "fullOwnedAlgorithmInstalled":False,"automaticRestore":False,"inFlight":None}
        self.save();self.saved=True

    def idle(self):
        if self.io.read(0x6bb46c)&255:raise RuntimeError("AF not idle")
        if self.io.read(0x2adc78)&0xff00!=18<<8 or self.io.read(0x2adc8c)&255:
            raise RuntimeError("lens profile or override changed")

    def install(self):
        self.idle();self.record["stage"]="writing_speed12000";self.save()
        for a in SPEEDS:self.write(a,12000)
        readback={hex(a):self.io.read(a) for a in SPEEDS}
        if any(v!=12000 for v in readback.values()):raise RuntimeError("final speed readback mismatch")
        hooks={hex(a):self.io.read(a)==old for a,old,_ in L.M["hooks"]}
        if not all(hooks.values()) or self.io.read(L.M["symbols"]["af_state"]+8)!=0:
            raise RuntimeError("algorithm state changed during speed update")
        self.idle()
        self.record.update({"stage":"speed12000_retained_factory_algorithm","activeSpeed":12000,
            "verified":{"at":datetime.now().astimezone().isoformat(),"speedWords":readback,
                        "factoryHooks":hooks,"candidateArmed":0,"afState":0}})
        self.save();return self.record["verified"]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("report","install"),nargs="?",default="report")
    args=parser.parse_args();paths=sorted((L.HERE/"recovery").glob("speed-only12000-*.json"))
    if args.action=="report":
        print(json.dumps(json.loads(paths[-1].read_text(encoding="utf-8")) if paths else
              {"stage":"prepared_offline_only"},indent=2));return
    if paths:raise RuntimeError("speed installation already attempted; inspect record")
    assert Path.cwd().resolve()==L.ROOT.resolve()
    loader=SpeedOnly()
    try:
        loader.preflight();loader.install()
        print(json.dumps({"recovery":loader.path.name,**loader.record},indent=2),flush=True)
    finally:
        if loader.saved:loader.save()

if __name__=="__main__":main()
