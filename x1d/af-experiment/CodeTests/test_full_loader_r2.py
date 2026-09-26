"""全程AF安装器的零写入守卫、缓存、启用顺序及中断恢复模型。无USB。"""
import sys,unittest,struct,json
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE/"CodeTests")]
import full_loader_r2 as F
from test_loader import MemoryIO
FARM=F.FarmApplication();L=F.L

class ModelIO(MemoryIO):
    def __init__(self):super().__init__();self.operations=[];self.armed=False
    def exchange(self,kind,a=None,v=None):
        self.operations.append((kind,a,v))
        if kind=="write" and a==F.STATE+8 and v==2:
            assert self.value(0x6bb46c)&255==0
            assert self.value(L.CB)==L.ORIG_CB and self.value(L.ARG)==L.ORIG_ARG
            assert all(self.value(x)==0 for x in range(L.BASE,F.M["base"],4))
            for x,_,new in F.M["hooks"]:
                assert self.value(x)==new and self.icache[x]==new
            for x,_,new in F.M["speed_words"]:assert self.value(x)==new
            for offset in range(0,len(F.PAYLOAD),4):
                x=F.M["base"]+offset;word=struct.unpack_from("<I",F.PAYLOAD,offset)[0]
                assert self.value(x)==word
                if not F.STATE<=x<F.STATE+F.M["stateBytes"]:assert self.icache[x]==word
            self.armed=True
        result=super().exchange(kind,a,v)
        if self.requests>11000:raise RuntimeError("model operation budget")
        return result

class ModelLoader(F.FullLoader):
    def save(self):
        self.record.update({"requests":self.io.requests,"writes":self.io.writes,"allHandlesClosed":self.io.closed})

class FullLoaderTests(unittest.TestCase):
    def test_power_cycle_is_not_mistaken_for_an_installed_record(self):
        io,loader=self.installed();loader.io=ModelIO()
        with self.assertRaisesRegex(RuntimeError,'installation disappeared'):
            loader.recovery_preflight(FARM)
        self.assertEqual(loader.io.writes,0)

    def prepared(self):
        io=ModelIO();loader=ModelLoader(io);loader.preflight(FARM)
        self.assertEqual(io.writes,0);return io,loader
    def installed(self,arm=True):
        io,loader=self.prepared();loader.probe();loader.install()
        if arm:loader.arm()
        return io,loader

    def test_install_and_explicit_algorithm_only_restore(self):
        io,loader=self.installed();self.assertTrue(io.armed)
        self.assertEqual(loader.record["stage"],"full_owned_armed_until_restart")
        installed_requests=io.requests
        loader.recovery_preflight(FARM);loader.restore_algorithm(keep_speed=True)
        self.assertEqual(io.value(F.STATE+8),0)
        for a,old,_ in F.M["hooks"]:self.assertEqual(io.icache[a],old)
        for a,_,new in F.M["speed_words"]:self.assertEqual(io.value(a),new)
        print("full install model requests",installed_requests,"including explicit restore",io.requests)

    def test_rollback_preserves_recorded_original5000(self):
        io,loader=self.installed();loader.recovery_preflight(FARM);loader.restore_algorithm()
        for a,old,_ in F.M["speed_words"]:self.assertEqual(io.value(a),old)
        self.assertEqual(io.value(L.CB),L.ORIG_CB);self.assertEqual(io.value(L.ARG),L.ORIG_ARG)

    def test_all_preflight_addresses_fail_closed(self):
        io,loader=self.prepared()
        addresses={a for kind,a,_ in io.operations if kind=="read"}
        for address in addresses:
            io=ModelIO();io.mem[address]=io.value(address)^0xffffffff;loader=ModelLoader(io)
            with self.assertRaises(RuntimeError,msg=hex(address)):loader.preflight(FARM)
            self.assertEqual(io.writes,0)

    def test_unrelated_writes_and_wrong_signed_speed_denied(self):
        io,loader=self.prepared()
        for a,v in ((0x442c0060,1),(0x2adc2c,12000),(F.M["end"],0),(L.SGIR,0x0100000f)):
            with self.assertRaises(ValueError):loader.write(a,v)
        self.assertEqual(io.writes,0)

    def test_af_activity_blocks_install_and_arm(self):
        io,loader=self.prepared();loader.probe();writes=io.writes;io.mem[0x6bb46c]=3
        with self.assertRaises(RuntimeError):loader.install()
        self.assertEqual(io.writes,writes)
        io,loader=self.installed(arm=False);writes=io.writes;io.mem[0x6bb46c]=3
        with self.assertRaises(RuntimeError):loader.arm()
        self.assertEqual(io.writes,writes)

    def test_static_payload_corruption_blocks_arm_verification(self):
        io,loader=self.installed(arm=False);io.mem[F.M["base"]]^=1
        with self.assertRaises(RuntimeError):loader.verify(0)
        self.assertEqual(io.value(F.STATE+8),0)

    def test_failures_at_mutation_boundaries_recover_only_when_explicit(self):
        io,loader=self.prepared();loader.probe();before=io.requests
        loader.install();loader.arm();after=io.requests
        # 每个入口/速度/启用/SGI操作及相邻读回，再覆盖上传的头中尾。
        special={L.CB,L.ARG,L.SGIR,F.STATE+8}|{a for a,_,_ in F.M["hooks"]+F.M["speed_words"]}
        points={i+1 for i,(kind,a,v) in enumerate(io.operations) if before<=i<after and kind=="write" and a in special}
        points|={i+1 for i in list(points) if i+1<=after}
        upload=[i+1 for i,(kind,a,v) in enumerate(io.operations) if before<=i<after and kind=="write" and F.M["base"]<=a<F.M["end"]]
        points.update(upload[::128]);points.add(upload[-1])
        for point in sorted(points):
            for side in ("before","after"):
                io,loader=self.prepared();loader.probe();io.fail_at=point;io.side=side
                with self.assertRaises(IOError,msg=(point,side)):
                    loader.install();loader.arm()
                self.assertTrue(io.failed)
                # 异常本身没有自动回退；恢复仅由此处明确调用。
                failed_requests=io.requests
                self.assertIsNotNone(loader.record.get("stage"))
                loader.recovery_preflight(FARM);loader.restore_algorithm()
                self.assertGreater(io.requests,failed_requests)
                for a,old,_ in F.M["hooks"]:self.assertEqual(io.icache[a],old)
                for a,old,_ in F.M["speed_words"]:self.assertEqual(io.value(a),old)
                self.assertEqual(io.value(L.CB),L.ORIG_CB);self.assertEqual(io.value(L.ARG),L.ORIG_ARG)
        print("full install mutation failure cases",2*len(points))

if __name__=="__main__":unittest.main()
