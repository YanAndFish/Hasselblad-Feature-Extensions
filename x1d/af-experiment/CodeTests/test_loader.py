"""装载顺序、指令缓存、故障后恢复和报文白名单的离线模型。"""
import sys,struct,unittest,json
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import probe_loader as L
from farm_diagnostic_binary import FarmApplication
F=FarmApplication()
class MemoryIO:
    def __init__(self):
        self.mem={a:expected for a,(mask,expected) in L.GUARDS.items()}
        self.mem.update({a:0 for a in range(L.BASE,L.M["end"],4)})
        for a,old,new in L.M["hooks"]+L.M["speed_words"]:self.mem[a]=old
        self.mem[0x6badd0]=1000;self.requests=0;self.writes=0;self.closed=True
        self.back={};self.icache={};self.fail_at=None;self.side=None;self.failed=False
        self.probe_runs=0;self.thunk_runs=0
    def read(self,a):return self.exchange("read",a)
    def value(self,a):
        if a in self.mem:return self.mem[a]
        if F.base<=a<a+4<=F.base+len(F.data):return F.word(a)
        return 0
    def sync(self,start,size,clean):
        for a in range(start&~31,(start+size+31)&~31,4):
            if clean:self.back[a]=self.value(a)
            else:self.icache[a]=self.back.get(a,self.value(a))
    def dispatch(self):
        fn,arg=self.value(L.CB),self.value(L.ARG)
        if fn==L.NOOP:return
        if fn==L.ORIG_CB:assert arg==L.ORIG_ARG;return
        if fn in (L.CLEAN,L.INVALIDATE):
            assert arg==L.BASE;self.sync(arg,32,fn==L.CLEAN);return
        assert fn==L.BASE and arg==L.DESC
        code=b"".join(struct.pack("<I",self.icache.get(a,0)) for a in range(L.BASE,L.BASE+28,4))
        if code[:16]==L.PROBE:
            self.mem[L.DESC]=L.MAGIC;self.probe_runs+=1
        else:
            assert code==L.THUNK,"stale instruction cache"
            start,size,operation=[self.value(L.DESC+4*i) for i in range(3)]
            assert operation in (L.CLEAN_RANGE,L.INVALIDATE_RANGE)
            self.sync(start,size,operation==L.CLEAN_RANGE)
            self.mem[L.DESC+12]=1;self.thunk_runs+=1
    def failure(self,side):
        if self.requests==self.fail_at and side==self.side and not self.failed:
            self.failed=True;raise IOError("modeled link failure")
    def exchange(self,kind,a=None,v=None):
        L.request(kind,a,v);self.requests+=1;self.failure("before")
        if kind=="version":result=["827fa74","c9bb91d","abad48d"]
        elif kind=="read":result=self.value(a)
        else:
            self.writes+=1
            if a==L.SGIR:self.dispatch()
            else:self.mem[a]=v
            result=0
        self.failure("after");return result
class ModelLoader(L.Loader):
    def save(self):
        self.record.update({"requests":self.io.requests,"writes":self.io.writes,"allHandlesClosed":True})
class LoaderTests(unittest.TestCase):
    def prepared(self):
        io=MemoryIO();loader=ModelLoader(io);loader.preflight(F);self.assertEqual(io.writes,0);return io,loader
    def test_full_sequence_and_restoration(self):
        io,loader=self.prepared();r=loader.probe();self.assertTrue(all(r.values()));self.assertEqual(io.probe_runs,1)
        loader.install()
        for a,old,new in L.M["hooks"]:self.assertEqual(io.icache[a],new)
        loader.arm();self.assertEqual(io.value(L.M["symbols"]["af_state"]+8),1)
        self.assertTrue(all(loader.restore().values()))
        for a,old,new in L.M["hooks"]:self.assertEqual(io.icache[a],old)
        self.assertEqual(io.value(L.CB),L.ORIG_CB);self.assertEqual(io.value(L.ARG),L.ORIG_ARG)
    def retained(self):
        io=MemoryIO();loader=ModelLoader(io)
        former=json.loads((HERE/"recovery/trial-20260910-205905.json").read_text(encoding="utf-8"))
        old=former["manifest"];blob=(HERE/"build/trial-v1-20260910-2100/candidate.bin").read_bytes()
        for off in range(0,len(blob),4):io.mem[old["base"]+off]=struct.unpack_from("<I",blob,off)[0]
        for a,_,new in L.M["speed_words"]:io.mem[a]=new
        return io,loader,former
    def test_retained_speed_with_continuous_algorithm_and_restore(self):
        io,loader,former=self.retained();loader.preflight_retained(F,former)
        self.assertEqual(io.writes,0);loader.probe();loader.install();loader.arm(until_restart=True)
        self.assertEqual(io.value(L.M["symbols"]["af_state"]+8),2)
        for a,old,new in L.M["hooks"]:self.assertEqual(io.icache[a],new)
        self.assertTrue(all(loader.restore().values()))
        for a,_,new in L.M["speed_words"]:self.assertEqual(io.value(a),8000)
    def test_retained_preflight_refuses_changed_code_without_write(self):
        io,loader,former=self.retained();io.mem[L.M["base"]]^=1
        with self.assertRaises(RuntimeError):loader.preflight_retained(F,former)
        self.assertEqual(io.writes,0)
    def test_unknown_access_and_sgi_targets_denied(self):
        for a in (0xf8f0010c,0,0x442c0060):
            with self.assertRaises(ValueError):L.request("read",a)
            with self.assertRaises(ValueError):L.request("write",a,0)
        with self.assertRaises(ValueError):L.request("write",L.SGIR,0x0100000f)
        loader=ModelLoader(MemoryIO())
        with self.assertRaises(RuntimeError):loader.write(L.CB,L.NOOP)
    def test_occupied_arena_prevents_every_write(self):
        io=MemoryIO();io.mem[L.BASE]=1;loader=ModelLoader(io)
        with self.assertRaises(RuntimeError):loader.preflight(F)
        self.assertEqual(io.writes,0);self.assertFalse(loader.saved)
    def test_response_contracts(self):
        for kind in ("read","write"):
            packet=bytearray(512);packet[:4]=bytes.fromhex("f5000108" if kind=="read" else "f3000108")
            self.assertEqual(L.reply(kind,bytes(packet),512),0)
            for mode in ("short","header","status"):
                altered=bytearray(packet)
                if mode=="short":altered=altered[:-1]
                elif mode=="header":altered[2]=8
                else:altered[8 if kind=="read" else 4]=1
                with self.assertRaises(ValueError):L.reply(kind,bytes(altered),512)
    def test_probe_failures_with_link_return(self):
        io,base=self.prepared();start=io.requests;base.probe();count=io.requests-start
        for offset in range(1,count+1):
            for side in ("before","after"):
                io,loader=self.prepared();io.fail_at=io.requests+offset;io.side=side
                try:loader.probe()
                except IOError:pass
                self.assertTrue(io.failed)
                loader.clean_scratch()
                self.assertEqual(io.value(L.CB),L.ORIG_CB)
                self.assertEqual(io.value(L.ARG),L.ORIG_ARG)
                self.assertTrue(all(io.value(a)==0 for a in range(L.BASE,L.BASE+64,4)))
if __name__=="__main__":unittest.main()
