"""原厂5000且空临时区域时，12000完整装载的离线验证。"""
import sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE/"CodeTests")]
import fresh_speed12000 as S
from test_loader import MemoryIO,ModelLoader,F
L=S.L

class FreshTests(unittest.TestCase):
    def test_fresh_install_and_restore_factory_baseline(self):
        io=MemoryIO();loader=ModelLoader(io)
        loader.preflight(F);self.assertEqual(io.writes,0)
        self.assertEqual(loader.record["manifest"],S.TARGET)
        self.assertTrue(all(loader.probe().values()))
        loader.install();loader.arm(until_restart=True)
        self.assertTrue(all(S.verify(loader)["readback"].values()))
        for a,_,new in S.TARGET["hooks"]:self.assertEqual(io.icache[a],new)
        before=(io.requests,io.writes)
        self.assertTrue(all(loader.restore().values()))
        for a,_,_ in S.TARGET["speed_words"]:self.assertEqual(io.value(a),5000)
        for a,old,_ in S.TARGET["hooks"]:self.assertEqual(io.icache[a],old)
        self.assertLess(io.requests,6000)
        print("model fresh install requests/writes",before,"with restore",io.requests,io.writes)

    def test_nonzero_arena_or_wrong_entry_refused_before_write(self):
        for a in (L.BASE,S.TARGET["base"],S.TARGET["symbols"]["af_state"],S.TARGET["end"]-4,S.TARGET["hooks"][0][0]):
            io=MemoryIO();io.mem[a]=io.value(a)^1;loader=ModelLoader(io)
            with self.assertRaises(RuntimeError):loader.preflight(F)
            self.assertEqual(io.writes,0)

    def test_wrong_speed_or_busy_refused_before_write(self):
        for a,value in ((S.TARGET["speed_words"][0][0],8000),(0x6bb46c,3),(0x2adc8c,1)):
            io=MemoryIO();io.mem[a]=value;loader=ModelLoader(io)
            with self.assertRaises(RuntimeError):loader.preflight(F)
            self.assertEqual(io.writes,0)

    def test_exact_new_payload_and_speed_whitelist(self):
        io=MemoryIO();loader=ModelLoader(io);loader.preflight(F)
        for speed in (8000,10000,16000):
            with self.assertRaises(ValueError):loader.write(S.TARGET["speed_words"][0][0],speed)
        with self.assertRaises(ValueError):loader.write(S.TARGET["base"],0x12345678)
        self.assertEqual(io.writes,0)

if __name__=="__main__":
    def denied(*a,**kw):raise AssertionError("offline hardware construction denied")
    L.FixedUsb=denied
    unittest.main()
