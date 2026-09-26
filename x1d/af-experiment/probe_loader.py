"""固定1.25.0 FARM的可恢复临时RAM探针。导入不访问硬件；无任意读写入口。"""
import sys,os,json,struct,hashlib,time
from pathlib import Path
from datetime import datetime,timezone
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/"x1d/tools"),str(ROOT/".research-cache/x1d-1.25.0/python")]
import read_usb_link_once as usb
M=json.loads((HERE/"build/manifest.json").read_text(encoding="utf-8"))
PAYLOAD=(HERE/"build/candidate.bin").read_bytes()
assert hashlib.sha256(PAYLOAD).hexdigest()==M["payload_sha256"]
BASE=0x2b2800; DESC=0x2b2820; CB=0x2a5074; ARG=0x2a5078
ORIG_CB=0x109304;ORIG_ARG=0x6da728;NOOP=0x1009d4
CLEAN=0x10a2d0;INVALIDATE=0x10a310;CLEAN_RANGE=0x10a270;INVALIDATE_RANGE=0x10a354
SGIR=0xf8f01f00;SELF15=0x0200000f;MAGIC=0xafaf2026
PROBE=bytes.fromhex("261002e3af1f4ae3001080e51eff2fe1")
THUNK=struct.pack("<7I",0xe92d4010,0xe1a04000,0xe8940007,0xe12fff32,0xe3a00001,0xe584000c,0xe8bd8010)
# 原厂回调/优先级/安全组均为固定守卫；从不读IAR，不修改中断启用或优先级。
GUARDS={0x2ad78c:(0xffffffff,0x2a4ffc),0x6da728:(0xffffffff,0x2a4ff0),0x6da72c:(0xffffffff,0x11111111),
 CB:(0xffffffff,ORIG_CB),ARG:(0xffffffff,ORIG_ARG),0x6bb46c:(255,0),
 0xf8f01000:(1,1),0xf8f00100:(9,1),0xf8f01100:(0x8000,0x8000),
 0xf8f01200:(0x8000,0),0xf8f01300:(0x8000,0),0xf8f0140c:(0xff000000,0xa0000000),0xf8f01080:(0x8000,0),
 0x2adc78:(0xff00,18<<8),0x2adc8c:(255,0),0x1009d4:(0xffffffff,0xe12fff1e)}
for a,old,new in M["speed_words"]:GUARDS[a]=(0xffffffff,old)
READ_SET=set(GUARDS)|{0xf8f00104,0x6badd0,0x6bb5a0,0x6bb5a4,0x6bb5b0,0x6bb5b4,0x6bc954}
READ_SET.update(range(BASE,M["end"],4))
for a,old,new in M["hooks"]:READ_SET.update(range(a&~31,(a&~31)+32,4))
READ_SET.update(range(0x10a270,0x10a3ac,4))
READ_SET.update(range(0x10acac,0x10acb8,4))
WRITE_SET={CB,ARG,SGIR}|set(range(BASE,M["end"],4))|{a for a,_,_ in M["hooks"]+M["speed_words"]}
def request(kind,a=None,v=None,size=512):
    if size not in (512,1024):raise ValueError("packet size")
    if kind=="version":body=bytes.fromhex("0d000801")
    elif kind=="read":
        if a not in READ_SET or a%4:raise ValueError("read denied")
        body=bytes.fromhex("f4000801")+struct.pack("<I",a)
    elif kind=="write":
        if a not in WRITE_SET or (a==SGIR and v!=SELF15):raise ValueError("write denied")
        if type(v)!=int or not 0<=v<=0xffffffff or a%4:raise ValueError("write value")
        body=bytes.fromhex("f2000801")+struct.pack("<II",a,v)
    else:raise ValueError("request kind")
    return body+bytes(size-len(body))
def reply(kind,data,size):
    if type(data)!=bytes or len(data)!=size:raise ValueError("reply length")
    if kind=="version":
        if data[:4]!=bytes.fromhex("0e000108"):raise ValueError("version header")
        values=[]
        for offset in (4,68,132):
            field=data[offset:offset+64]
            s=field.split(b"\0",1)[0]
            if len(s)!=7 or any(c not in b"0123456789abcdef" for c in s):raise ValueError("version field")
            values.append(s.decode())
        if values!=["827fa74","c9bb91d","abad48d"]:raise ValueError("version mismatch")
        return values
    header=bytes.fromhex("f5000108" if kind=="read" else "f3000108")
    if data[:4]!=header or data[8 if kind=="read" else 4]!=0:raise ValueError("reply mismatch")
    return struct.unpack_from("<I",data,4)[0] if kind=="read" else 0
class FixedUsb(usb.NativeWinUsb):
    def __init__(self,kind,a=None,v=None):self.kind,self.address,self.value=kind,a,v;super().__init__()
    def write_query(self,size):
        if not self.prepared or self.sent or size!=self.packet_size:raise usb.UsbFailure("USB_REQUEST_DENIED")
        packet=request(self.kind,self.address,self.value,size)
        buf=usb.c.create_string_buffer(packet,size);count=usb.U32();self.sent=True
        self.check(self.winusb.WinUsb_WritePipe(self.usb,2,buf,size,usb.c.byref(count),None),"USB_WRITE")
        return count.value
class FixedIO:
    def __init__(self,limit=6000):self.requests=0;self.writes=0;self.closed=True;self.limit=limit
    def exchange(self,kind,a=None,v=None):
        request(kind,a,v)
        if self.requests>=self.limit:raise RuntimeError("operation budget")
        t=FixedUsb(kind,a,v)
        try:
            size=usb.validate_interface(t.open());t.prepare();self.requests+=1
            if kind=="write":self.writes+=1
            if t.write_query(size)!=size:raise RuntimeError("short write")
            return reply(kind,t.read_reply(size),size)
        finally:
            self.closed=all(t.close().values())
            if not self.closed:raise RuntimeError("handle close failed")
    def read(self,a):return self.exchange("read",a)
class Loader:
    def __init__(self,io=None):
        self.io=io or FixedIO();self.original={};self.saved=False;self.path=None;self.record={}
        self.allowed={CB:{ORIG_CB,NOOP,CLEAN,INVALIDATE,BASE},ARG:{ORIG_ARG,BASE,DESC},SGIR:{SELF15}}
        for a in range(BASE,M["end"],4):self.allowed[a]={0}
        for blob,start in ((PROBE,BASE),(THUNK,BASE),(PAYLOAD,M["base"])):
            for off in range(0,len(blob),4):self.allowed[start+off].add(struct.unpack_from("<I",blob,off)[0])
        for a,old,new in M["hooks"]+M["speed_words"]:self.allowed[a]={old,new}
        self.allowed[DESC].update({M["base"]}|{a&~31 for a,_,_ in M["hooks"]})
        self.allowed[DESC+4].update({32,M["end"]-M["base"]})
        self.allowed[DESC+8].update({CLEAN_RANGE,INVALIDATE_RANGE})
        self.allowed[DESC+12].add(1)
        self.allowed[M["symbols"]["af_state"]+8].update({1,2})
    def save(self):
        assert self.path and self.path.parent.resolve()==(HERE/"recovery").resolve()
        self.record.update({"requests":self.io.requests,"writes":self.io.writes,"allHandlesClosed":self.io.closed})
        temp=self.path.with_suffix(".tmp")
        with temp.open("w",encoding="utf-8") as f:
            json.dump(self.record,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,self.path)
    def preflight(self,farm):
        assert not self.saved and farm.sha256==M["baseline_sha256"]
        self.io.exchange("version")
        for a,(mask,expected) in GUARDS.items():
            if self.io.read(a)&mask!=expected:raise RuntimeError("preflight guard "+hex(a))
        code=set(range(0x10a270,0x10a3ac,4))|set(range(0x10acac,0x10acb8,4))
        for a,_,_ in M["hooks"]:code.update(range(a&~31,(a&~31)+32,4))
        for a in sorted(code):
            if self.io.read(a)!=farm.word(a):raise RuntimeError("code baseline "+hex(a))
        for a in range(BASE,M["end"],4):
            if self.io.read(a)!=0:raise RuntimeError("arena occupied "+hex(a))
        self.original={str(a):old for a,old,new in M["hooks"]+M["speed_words"]}
        self.original.update({str(CB):ORIG_CB,str(ARG):ORIG_ARG})
        stamp=datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        self.path=HERE/"recovery"/("trial-"+stamp+".json")
        if self.path.exists():raise RuntimeError("recovery name exists")
        self.record={"stage":"prepared","created":datetime.now().astimezone().isoformat(),"manifest":M,"original":self.original,
            "originalArena":{"start":BASE,"end":M["end"],"allZero":True},"probeExecuted":False,"installed":False,"armed":False}
        self.save();self.saved=True
        return {"stage":"prepared","requests":self.io.requests,"writes":self.io.writes,"recovery":self.path.name}
    def write(self,a,v):
        if not self.saved:raise RuntimeError("recovery record required")
        if a not in self.allowed or v not in self.allowed[a]:raise ValueError("fixed write denied")
        self.record["inFlight"]={"address":a,"value":v};self.save()
        self.io.exchange("write",a,v)
        if a!=SGIR and self.io.read(a)!=v:raise RuntimeError("write readback mismatch")
        self.record["inFlight"]=None
    def preflight_retained(self,farm,former):
        """仅复用本轮已恢复入口、保留8000的已知v1临时区域。"""
        assert not self.saved and farm.sha256==M["baseline_sha256"]
        old=former["manifest"]
        archive=HERE/"build/trial-v1-20260910-2100"
        old_payload=(archive/"candidate.bin").read_bytes()
        assert old==json.loads((archive/"manifest.json").read_text(encoding="utf-8"))
        assert hashlib.sha256(old_payload).hexdigest()==old["payload_sha256"]
        assert old["baseline_sha256"]==M["baseline_sha256"] and old["base"]==M["base"]
        assert former["stage"]=="speed_only_8000_retained" and former["probeExecuted"]
        assert not former["installed"] and not former["armed"]
        self.io.exchange("version")
        speeds={a:new for a,_,new in M["speed_words"]}
        for a,(mask,expected) in GUARDS.items():
            if self.io.read(a)&mask!=speeds.get(a,expected):raise RuntimeError("retained guard "+hex(a))
        code=set(range(0x10a270,0x10a3ac,4))|set(range(0x10acac,0x10acb8,4))
        for a,_,_ in M["hooks"]:code.update(range(a&~31,(a&~31)+32,4))
        for a in sorted(code):
            if self.io.read(a)!=farm.word(a):raise RuntimeError("retained code baseline "+hex(a))
        state=old["symbols"]["af_state"]
        for a in range(BASE,M["end"],4):
            if state<=a<state+572:continue
            expected=struct.unpack_from("<I",old_payload,a-old["base"])[0] if old["base"]<=a<old["end"] else 0
            if self.io.read(a)!=expected:raise RuntimeError("retained arena changed "+hex(a))
        for a,expected in ((state,0x41463552),(state+4,1),(state+8,0),(state+568,0x52463541)):
            if self.io.read(a)!=expected:raise RuntimeError("retained state guard "+hex(a))
        self.original={str(a):old for a,old,new in M["hooks"]}
        self.original.update({str(a):new for a,old,new in M["speed_words"]})
        self.original.update({str(CB):ORIG_CB,str(ARG):ORIG_ARG})
        self.path=HERE/"recovery"/("trial-"+datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")+".json")
        if self.path.exists():raise RuntimeError("recovery name exists")
        self.record={"stage":"prepared_from_inactive_v1","created":datetime.now().astimezone().isoformat(),
            "manifest":M,"original":self.original,"probeExecuted":False,"installed":False,"armed":False,
            "reusedInactivePayload":old["payload_sha256"],"priorSpeed":8000,"automaticSpeedRestore":False,
            "priorTrialRequests":former["requests"],"priorTrialWrites":former["writes"]}
        self.save();self.saved=True
        return {"stage":self.record["stage"],"requests":self.io.requests,"writes":self.io.writes,"recovery":self.path.name}
    def quiet(self):
        self.write(CB,NOOP)
        for a in (0xf8f01200,0xf8f01300):
            if self.io.read(a)&0x8000:raise RuntimeError("SGI not quiescent")
    def line_cache(self,fn):
        assert fn in (CLEAN,INVALIDATE)
        self.quiet();self.write(ARG,BASE);self.write(CB,fn);self.write(SGIR,SELF15);self.quiet()
    def restore_slot(self):
        self.quiet();self.write(ARG,ORIG_ARG);self.write(CB,ORIG_CB)
    def probe(self):
        self.record["stage"]="probe";self.save()
        try:
            self.quiet()
            for off in range(0,16,4):self.write(BASE+off,struct.unpack_from("<I",PROBE,off)[0])
            self.write(DESC,0);self.line_cache(CLEAN);self.line_cache(INVALIDATE)
            self.write(ARG,DESC);self.write(CB,BASE);self.write(SGIR,SELF15);self.quiet()
            if self.io.read(DESC)!=MAGIC:raise RuntimeError("probe did not execute")
            self.record["probeExecuted"]=True;self.save()
        finally:
            self.quiet()
            for a in range(BASE,BASE+64,4):self.write(a,0)
            self.line_cache(CLEAN);self.line_cache(INVALIDATE);self.restore_slot()
            self.record["stage"]="probe_restored";self.save()
        return {"probeExecuted":self.record["probeExecuted"],"slotRestored":self.io.read(CB)==ORIG_CB and self.io.read(ARG)==ORIG_ARG,
            "scratchRestored":all(self.io.read(a)==0 for a in range(BASE,BASE+64,4))}
    def upload_thunk(self):
        self.quiet()
        for off in range(0,len(THUNK),4):self.write(BASE+off,struct.unpack_from("<I",THUNK,off)[0])
        self.line_cache(CLEAN);self.line_cache(INVALIDATE)
    def range_cache(self,start,size,fn):
        if fn not in (CLEAN_RANGE,INVALIDATE_RANGE):raise ValueError("cache function")
        self.quiet()
        for a,v in ((DESC,start),(DESC+4,size),(DESC+8,fn),(DESC+12,0)):self.write(a,v)
        self.write(ARG,DESC);self.write(CB,BASE);self.write(SGIR,SELF15);self.quiet()
        if self.io.read(DESC+12)!=1:raise RuntimeError("cache range execution missing")
    def sync_code(self,start,size):
        self.range_cache(start,size,CLEAN_RANGE);self.range_cache(start,size,INVALIDATE_RANGE)
    def clean_scratch(self):
        self.quiet()
        for a in range(BASE,BASE+64,4):self.write(a,0)
        self.line_cache(CLEAN);self.line_cache(INVALIDATE);self.restore_slot()
    def install(self):
        if not self.record.get("probeExecuted") or self.io.read(0x6bb46c)&255:raise RuntimeError("installation precondition")
        if self.io.read(CB)!=ORIG_CB or self.io.read(ARG)!=ORIG_ARG or any(self.io.read(a) for a in range(BASE,BASE+64,4)):
            raise RuntimeError("probe restoration must complete before installation")
        self.record["stage"]="installing";self.save()
        for off in range(0,len(PAYLOAD),4):self.write(M["base"]+off,struct.unpack_from("<I",PAYLOAD,off)[0])
        self.upload_thunk();self.sync_code(M["base"],len(PAYLOAD))
        for a,old,new in M["hooks"]:
            if self.io.read(a)!=old:raise RuntimeError("hook changed")
            self.write(a,new);self.sync_code(a&~31,32)
        for a,old,new in M["speed_words"]:
            expected=self.original.get(str(a),old)
            if self.io.read(a)!=expected:raise RuntimeError("speed changed")
            if expected!=new:self.write(a,new)
        self.clean_scratch()
        self.record["stage"]="installed_disarmed";self.record["installed"]=True;self.save()
    def arm(self,until_restart=False):
        if not self.record.get("installed") or self.io.read(0x6bb46c)&255:raise RuntimeError("arm precondition")
        a=M["symbols"]["af_state"];until=(self.io.read(0x6badd0)+30000)&0xffffffff
        self.allowed[a+12].add(until);self.write(a+12,until);self.write(a+8,2 if until_restart else 1)
        self.record["stage"]="armed_until_restart" if until_restart else "armed"
        self.record["armed"]=True;self.record["outerTimeoutDisabled"]=until_restart;self.save()
    def restore(self):
        a=M["symbols"]["af_state"]
        self.write(a+8,0);self.record["armed"]=False
        if self.io.read(0x6bb46c)&255:raise RuntimeError("wait for AF idle before restoring hooks")
        self.record["stage"]="restoring";self.save();self.upload_thunk()
        for addr,old,new in M["speed_words"]:self.write(addr,self.original.get(str(addr),old))
        for addr,old,new in M["hooks"]:self.write(addr,old);self.sync_code(addr&~31,32)
        self.clean_scratch()
        # 留下不再引用的候选区域供取证；不在可能存在任务返回地址时擦除代码。
        self.record["installed"]=False;self.record["stage"]="factory_hooks_and_prior_speed_restored"
        self.record["unreferencedPayloadRetained"]=True;self.save()
        checks={hex(addr):self.io.read(addr)==self.original.get(str(addr),old) for addr,old,new in M["hooks"]+M["speed_words"]}
        self.record["restorationReadback"]=checks;self.save()
        return checks
