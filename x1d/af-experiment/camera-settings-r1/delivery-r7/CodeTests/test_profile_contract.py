"""Profile 不混装、精确写入入口及离线限定。"""
import copy,unittest
from test_delivery import prepare,FARM,HERE,AfOnlyContract,AfOnlyLoader
from range_contract import validate_manifest,read
class ProfileContract(unittest.TestCase):
    def test_explicit_profile_and_hardware_rejection(self):
        with self.assertRaises(ValueError):AfOnlyContract(FARM)
        c,io,_=prepare();io.is_hardware=True
        before=io.requests
        with self.assertRaises(RuntimeError):AfOnlyLoader(c,io)
        self.assertEqual(io.requests,before)
    def test_profile_write_allowlists_are_exact_and_retired_hook_is_read_only(self):
        for profile,size in (('release',12),('test',16)):
            c,_,_=prepare(profile=profile)
            self.assertEqual(len(c.offline['emulatorOnlyHooks']),size)
            self.assertNotIn(0x19d1b0,c.allowed)
            for a in (0x19890c,0x1990f8):
                self.assertEqual(c.allowed[a],{FARM.word(a)})
                self.assertIn((a&~31,32),c.ranges)
                for q in range(a&~31,(a&~31)+32,4):self.assertEqual(c.expected[q],FARM.word(q))
            if profile=='release':
                for a in (0x1f0d2c,0x1a1b48,0x1a2130,0x1e22b4):self.assertNotIn(a,c.allowed)
    def test_wrong_profile_extra_hook_corrupt_payload_and_wrong_branch_rejected(self):
        folder=HERE/'build/test/00800000';m=read(folder/'capture-manifest.json');blob=(folder/'candidate.bin').read_bytes()
        with self.assertRaises(ValueError):validate_manifest(m,blob,'release',FARM)
        for change in ('extra','branch','payload'):
            bad=copy.deepcopy(m);b=blob
            if change=='extra':bad['emulatorOnlyHooks'].append([0x19d1b0,FARM.word(0x19d1b0),0])
            if change=='branch':bad['emulatorOnlyHooks'][0][2]^=1
            if change=='payload':b=bytes([blob[0]^1])+blob[1:]
            with self.assertRaises(ValueError):validate_manifest(bad,b,'test',FARM)
if __name__=='__main__':unittest.main(verbosity=2)
