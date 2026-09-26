"""三字段速度更新的离线白名单与原值保存检查。"""
import sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE/"CodeTests")]
import speed_only12000 as S
from test_loader import MemoryIO

class Model(S.SpeedOnly):
    def save(self):
        self.record.update({"requests":self.io.requests,"writes":self.io.writes,"allHandlesClosed":True})

class Tests(unittest.TestCase):
    def test_only_three_writes_and_factory_algorithm_remains(self):
        io=MemoryIO();loader=Model(io);loader.preflight()
        self.assertEqual(io.writes,0);self.assertTrue(loader.saved)
        self.assertEqual(loader.original,{str(a):5000 for a in S.SPEEDS})
        loader.install();self.assertEqual(io.writes,3)
        self.assertTrue(all(io.value(a)==12000 for a in S.SPEEDS))
        self.assertEqual(loader.record["algorithm"],"factory")
        with self.assertRaises(ValueError):loader.write(S.L.CB,S.L.NOOP)
    def test_changed_speed_busy_or_active_candidate_refuses(self):
        for a,v in ((S.SPEEDS[0],8000),(0x6bb46c,3),(S.L.M["symbols"]["af_state"]+8,2)):
            io=MemoryIO();io.mem[a]=v;loader=Model(io)
            with self.assertRaises(RuntimeError):loader.preflight()
            self.assertEqual(io.writes,0)

if __name__=="__main__":unittest.main()
