"""绑定官方参考镜头参数及 20–35E 静态取值链；不访问网络或相机。"""
import hashlib,json,struct,unittest
from pathlib import Path
from lens_reference_inspect import ihex,View
HERE=Path(__file__).resolve().parent
class LensMaximum(unittest.TestCase):
    def test_seven_specific_parameters_and_source_hashes(self):
        expected={(164,'LensSpecifics_XCD38.hex'):(0x6c,23600),
                  (164,'LensSpecifics_XCD55.hex'):(0x6c,24800),
                  (164,'LensSpecifics_XCD28P.hex'):(0x6c,18000),
                  (164,'LensSpecifics_XCD75P.hex'):(0x6c,20000),
                  (165,'LensSpecifics_XCD25.hex'):(0x54,10000),
                  (165,'LensSpecifics_XCD90.hex'):(0x54,18000),
                  (174,'LensSpecifics_XCD35-100.hex'):(0x6c4,24000)}
        rows=json.loads((HERE/'output/lens-max-reference/parameters.json').read_text())
        seen=set()
        for row in rows:
            for entry in row['entries']:
                file=HERE/f"output/lens-max-reference/{row['product']}/{entry['name']}"
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),entry['sha256'])
                key=row['product'],entry['name']
                if key not in expected:continue
                offset,value=expected[key];mem=ihex(file)
                self.assertEqual(struct.unpack('<I',bytes(mem[a] for a in range(offset,offset+4)))[0],value)
                seen.add(key)
        self.assertEqual(seen,set(expected))
    def test_20_35e_fixed_speed_object_and_getter(self):
        v=View(169);d=0x60015bf8
        self.assertEqual(hashlib.sha256((HERE/'output/lens-max-reference/169/artifact.hex').read_bytes()).hexdigest(),
                         'ea913730834e0c5e5937fc5039d4bea5e6dbdbe05414a0a08da552c1619c32e4')
        # Boot 确认代码/只读数据地址换算，再核对静态参数对象。
        self.assertEqual([v.word(a) for a in (0x60015970,0x60015974,0x6001597c,0x60015980)],
                         [0x60016008,0x410,0x6005f708,0x49b10])
        self.assertEqual(v.word(0x53564+4+d),0x534ec)
        self.assertEqual(v.word(0x534ec+0x10+d),24000)
        self.assertIn('ldr      r3, [r3, #4]',v.dis(0x6003d944,10))
        self.assertIn('#0x600431f4',v.dis(0x6003d94a,4))
        self.assertIn('str      r3, [r2]',v.dis(0x600431fc,6))
        self.assertEqual(v.word(0x60043270),0x20204e7c)
        self.assertEqual(v.word(0x6004080c),0x20204e7c)
        self.assertIn('ldr      r2, [r3, #0x10]',v.dis(0x6004079e,10))
        self.assertIn('str      r2, [r3]',v.dis(0x600407a4,4))
if __name__=='__main__':unittest.main()
