"""12000固定切换的离线模型；USB类禁止构造，全部失败点覆盖前后两侧。"""
import sys,json,struct,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE/"CodeTests")]
import update_speed12000 as U
from test_loader import MemoryIO,F
L=U.L
FORMER=json.loads(U.FORMER.read_text(encoding="utf-8"))

class ModelUpdate(U.SpeedUpdate):
    def save(self):
        self.record.update({"requests":self.io.requests,"writes":self.io.writes,"allHandlesClosed":True})

class UpdateTests(unittest.TestCase):
    def fixture(self,preflight=True):
        io=MemoryIO()
        io.mem.update(U.words(L.PAYLOAD))
        for a,_,new in L.M["hooks"]+L.M["speed_words"]:io.mem[a]=new
        io.mem[U.STATE+8]=2
        io.sync(L.M["base"],len(L.PAYLOAD),True);io.sync(L.M["base"],len(L.PAYLOAD),False)
        for a,_,new in L.M["hooks"]:io.icache[a]=new
        loader=ModelUpdate(io)
        if preflight:loader.preflight(F,FORMER)
        return io,loader

    def check_target(self,io,target,blob):
        for a,_,new in target["hooks"]+target["speed_words"]:self.assertEqual(io.value(a),new)
        for a,_,new in target["hooks"]:self.assertEqual(io.icache[a],new)
        for a,v in U.words(blob).items():
            if U.STATE<=a<U.STATE+572:continue
            self.assertEqual(io.value(a),v)
            if a<U.STATE:self.assertEqual(io.icache[a],v)
        self.assertEqual(io.value(U.STATE+8),2)
        self.assertEqual(io.value(L.CB),L.ORIG_CB);self.assertEqual(io.value(L.ARG),L.ORIG_ARG)
        self.assertTrue(all(io.value(a)==0 for a in range(L.BASE,L.M["base"],4)))

    def test_complete_update_and_explicit_rollback(self):
        io,loader=self.fixture();self.assertEqual(io.writes,0)
        loader.switch(True);self.check_target(io,U.NEW,U.BLOB)
        update_requests,update_writes=io.requests,io.writes
        loader.validate_recovery(F);loader.switch(False);self.check_target(io,L.M,L.PAYLOAD)
        self.assertLess(io.requests,6000)
        print("model totals: install",update_requests,update_writes,"including rollback",io.requests,io.writes)

    def test_order_no_payload_write_with_candidate_entries_active(self):
        io,loader=self.fixture();original=io.exchange
        def observed(kind,a=None,v=None):
            if kind=="write" and any(a==p for p,_,_ in U.CHANGES):
                self.assertEqual(io.value(U.STATE+8),0)
                for p,factory,_ in L.M["hooks"]:self.assertEqual(io.icache[p],factory)
            return original(kind,a,v)
        io.exchange=observed;loader.switch(True)

    def test_preflight_mismatch_never_writes(self):
        for a in (L.M["base"],L.M["hooks"][0][0],L.M["speed_words"][0][0],U.STATE,U.STATE+8,L.CB,0x6bb46c,0x2adc78):
            io,loader=self.fixture(False);io.mem[a]=io.value(a)^1
            if a==0x2adc78:io.mem[a]^=0x100
            with self.assertRaises(RuntimeError):loader.preflight(F,FORMER)
            self.assertEqual(io.writes,0);self.assertFalse(loader.saved)

    def test_unknown_recovery_data_is_not_overwritten(self):
        for a in (L.M["base"],L.CB,L.M["speed_words"][0][0]):
            io,loader=self.fixture();io.mem[a]=0x12345678
            with self.assertRaises(RuntimeError):loader.validate_recovery(F)
            self.assertEqual(io.writes,0)
        io,loader=self.fixture();io.mem[L.M["base"]]=0
        with self.assertRaises(RuntimeError):loader.validate_recovery(F)
        self.assertEqual(io.writes,0)

    def test_fixed_speed_and_source_values_only(self):
        io,loader=self.fixture()
        for speed in (5000,10000,16000):
            with self.assertRaises(ValueError):loader.write(U.NEW["speed_words"][0][0],speed)
        with self.assertRaises(ValueError):loader.write(U.CHANGES[0][0],0x12345678)
        self.assertEqual(io.writes,0)

    def test_every_switch_failure_then_explicit_recovery(self):
        io,loader=self.fixture();start=io.requests;loader.switch(True);count=io.requests-start
        # 一次故障后链路恢复是此模型的明确前提；生产入口不会自动重试或回退。
        for offset in range(1,count+1):
            for side in ("before","after"):
                io,loader=self.fixture();io.fail_at=io.requests+offset;io.side=side
                with self.assertRaises(IOError):loader.switch(True)
                self.assertTrue(io.failed)
                loader.validate_recovery(F);loader.switch(False)
                self.check_target(io,L.M,L.PAYLOAD)
        print("modeled switch failure points:",count*2)

if __name__=="__main__":
    def denied(*a,**kw):raise AssertionError("offline tests must not construct a hardware transport")
    L.FixedUsb=denied
    unittest.main()
