"""固定R4状态ABI、资格理由与只读采样契约，使用装载器的内存包替身。"""
import sys,struct,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import read_full_diagnostic_r5 as D
import read_r5_transition_timing as TIME
from test_full_loader_r5 import PacketModel,FakePacket
L=D.L

class DiagnosticModelIO(D.ReadOnlyIO):
    is_hardware=False
    def __init__(self,contract,model):super().__init__(contract);self.model=model
    def transport(self,kind,a,v):return FakePacket(self,kind,a,v)

class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.contract=L.FixedContract(L.FarmApplication())
    def test_full_snapshot_decodes_limit_and_generation_bound_gate_reason(self):
        m=PacketModel(self.contract,1)
        m.memory.update(self.contract.plan.code)
        m.memory.update({a:new for a,old,new in L.M['hooks']+L.M['speed_words']})
        m.memory.update({D.AF+8:2,D.AF+16:21,D.AF+20:9,D.AF+24:8,D.AF+152:1,
                         D.GATE_STATUS:256|512,D.GATE_GENERATION:21,D.GATE_GAIN:0x40000000,
                         D.ERROR_EVENTS:0x100,D.ERROR_GENERATION:21})
        io=DiagnosticModelIO(self.contract,m);r={};D.snapshot(io,r)
        self.assertTrue(r['completed']);self.assertTrue(r['stableAnchors'])
        self.assertEqual(r['state']['reasonName'],'ENDPOINT')
        self.assertEqual(r['state']['reply_status'],1)
        self.assertEqual(r['eligibility']['reasons'],['数字增益大于1','对焦框超出160有效区域'])
        self.assertTrue(r['eligibility']['matchesAfGeneration']);self.assertFalse(r['eligibility']['qualified'])
        self.assertEqual(r['eligibility']['digitalGain'],2.0)
        self.assertEqual(r['nativeErrorEvent'],dict(generation=21,mask='0x100',matchesAfGeneration=True))
        self.assertEqual(io.writes,0);self.assertTrue(io.closed);self.assertLess(io.requests,D.LIMIT)
    def test_readers_deny_writes_and_wake_counter(self):
        for io in (DiagnosticModelIO(self.contract,PacketModel(self.contract,1)),TIME.TimingIO(self.contract)):
            for kind,a,v in (('write',L.COUNT,0),('read',L.COUNT,None),('read',L.SENT,None),('read',L.SGIR,None)):
                with self.assertRaises(ValueError):io.exchange(kind,a,v)
            self.assertEqual(io.requests,0)
    def test_timing_only_pairs_same_generation_and_fresh_start(self):
        row=dict(stableBinding=True,request=3,target=7,generation=21,session=21,video_started=1000,
            hostEndSeconds=1,ack=3,result=0,ready_tick=1137,video_state=0,phase=2,now=1140)
        self.assertEqual(TIME.summarize([row])['transitions'][0]['successfulReadyTicks'],137)
        for change in ({'session':20},{'video_started':0},{'stableBinding':False}):
            self.assertEqual(TIME.summarize([dict(row,**change)])['transitions'],[])
        old=TIME.summarize([dict(row,ready_tick=900)])['transitions'][0]
        self.assertIsNone(old['successfulReadyTicks'])

if __name__=='__main__':unittest.main(verbosity=2)
