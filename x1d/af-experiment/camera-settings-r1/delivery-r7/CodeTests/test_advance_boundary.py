"""Original fast-to-fine direction contract. This does not implement a 100ms advance."""
import struct,unittest
import test_r6_candidate as c
class AdvanceBoundary(unittest.TestCase):
    def test_factory_handoff_success_reverses_but_wait_or_failure_does_not_send(self):
        for status in (0,9,1):
            for direction in (-1,1):
                m=c.Machine()
                m.u.mem_write(0x19e7f0,c.pack(0xe3a00000|status,0xe12fff1e))
                m.u.mem_write(0x1a3e08,c.pack(0xe3010388,0xe12fff1e))
                m.u.mem_write(0x1a3ef4,c.pack(0xe3a00000,0xe12fff1e))
                m.u.mem_write(0x6bb5a0,struct.pack('<h',direction*20000));m.u.mem_write(0x6bb46c,b"\x04")
                result=m.run(0x19d87c)
                self.assertEqual(result,status)
                if status==0:self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-direction*5000))
                else:self.assertEqual(m.sends,[])
if __name__=='__main__':unittest.main(verbosity=2)
