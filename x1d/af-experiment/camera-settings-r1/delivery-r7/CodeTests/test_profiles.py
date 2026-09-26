import contextlib,json,struct,unittest
import test_r6_candidate as c
class Profiles(unittest.TestCase):
    def cache(self,m,speed,second=None):
        m.u.mem_write(0x6bcb7d,bytes([0,55,55]))
        m.u.mem_write(0x2ad998+18*36+5,b"77")
        m.u.mem_write(0x2ad998+18*36+12,c.pack(speed,speed if second is None else second))
        m.u.mem_write(0x6bcb7c,b"\x00")
    def test_dynamic_low_uses_reported_cache_not_stage_argument_or_override(self):
        for report,expected in ((5900,4130),(6200,4340),(4500,3150),(5000,3500),(2500,1750),(6000,4200),(6123,4286)):
            m=c.Machine();self.cache(m,report)
            m.u.mem_write(0x6bc9b0,c.pack(19000));m.u.mem_write(0x2adc8c,b"\x01");m.u.mem_write(0x2adc90,c.pack(18000))
            response=m.process(c.request(2,1,c.config(flags=0,start_speed=65533,start_samples=10)))
            self.assertEqual(c.words(response[24:28]),(0,));m.run('na_begin',2)
            for sign in (-1,1):
                m.run('na_stage_speed',0,sign*7123)
                self.assertEqual(m.sends[-1][-2:],struct.pack('<h',sign*expected))
    def test_invalid_or_stale_factory_cache_preserves_factory(self):
        for kind in ('zero','range','unknown','stale'):
            m=c.Machine();self.cache(m,0 if kind=='zero' else (32768 if kind=='range' else 5000))
            m.process(c.request(2,1,c.config(flags=2,start_speed=65533,start_samples=10)));m.run('na_begin',2)
            if kind=='unknown':m.u.mem_write(0x2adc79,b"\x13")
            if kind=='stale':m.u.mem_write(0x2ad998+18*36+5,b"8")
            m.run('na_stage_speed',0,7123)
            self.assertEqual(m.sends[-1][-2:],struct.pack('<h',7123))
    def test_profiles_share_core_but_release_has_no_debug_symbols_or_hooks(self):
        r=json.loads((c.DELIVERY/'build/release/00800000/capture-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(r['profile'],'release');self.assertFalse(r['debugRuntimeIncluded']);self.assertFalse(r['deploymentReady'])
        self.assertEqual(r['sharedSourceSha256'],c.M['sharedSourceSha256'])
        for symbol in ('na_config_bank','na_config_publish','as_process','as_receive','as_direction','na_direction','nc_capture','nc_raw','nc_cv_fifo','nc_position_fifo','na_assess','na_supply','na_before_peak'):
            self.assertNotIn(symbol,r['symbols'])
        addresses={x[0] for x in r['emulatorOnlyHooks']}
        self.assertEqual(len(addresses),12)
        self.assertFalse(addresses.intersection({0x19d1b0,0x1f0d2c,0x1a1b48,0x1a2130,0x1e22b4}))
        for source in ('native_af.c','native_capture.c','native_config.c','settings_receiver.c','rolling_direction.c','test_policy.c'):
            self.assertNotIn(source,r['source_sha256'])
    def test_release_whitelist_uses_reported_70_percent_then_full_maximum(self):
        old,blob=c.M,c.PAYLOAD
        try:
            folder=c.DELIVERY/'build/release/00800000';c.M=json.loads((folder/'capture-manifest.json').read_text(encoding='utf-8'));c.PAYLOAD=(folder/'candidate.bin').read_bytes()
            lenses=(((49,49,1),5900),((62,62,1),6200),((39,39,3),4500),((73,73,1),5000),
                    ((35,35,1),2500),((79,79,2),4500),((47,83,1),6000),((28,47,1),6000))
            for fields,reported in lenses:
                m=c.Machine();lo,hi,version=fields;row=0x2ad998+18*36
                m.u.mem_write(0x6bcb7d,bytes([0,lo,hi]));m.u.mem_write(row+5,bytes([lo,hi]))
                m.u.mem_write(row+12,c.pack(reported));m.u.mem_write(0x6bcb7c,b'\x00')
                m.run('af_identity_publish',lo,hi,version);m.run('na_begin',2)
                self.assertEqual(m.run('af_current_advance'),100)
                m.run('na_stage_speed',0,-7123)
                self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-(reported*7//10)))
                m.u.mem_write(0x6bb46c,b'\x03');m.u.mem_write(0x6bb5a0,struct.pack('<h',-1))
                for n in range(1,11):m.run('na_start_accepted',n)
                m.run('na_after_direction')
                maximum={(49,49,1):23600,(62,62,1):24800,(39,39,3):18000,(73,73,1):20000,
                         (35,35,1):10000,(79,79,2):18000,(47,83,1):24000,(28,47,1):24000}[fields]
                self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-maximum))
                m.run('na_stage_speed',1,6123);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',maximum))
                m.run('na_stage_speed',2,6123);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',6123))
        finally:c.M,c.PAYLOAD=old,blob
    def test_release_unknown_identity_preserves_speed_with_fixed_rules_and_install_probe_is_synchronous(self):
        old,blob=c.M,c.PAYLOAD
        try:
            folder=c.DELIVERY/'build/release/00800000';c.M=json.loads((folder/'capture-manifest.json').read_text(encoding='utf-8'));c.PAYLOAD=(folder/'candidate.bin').read_bytes()
            for fields,reported in (((1,2,3),5900),((49,49,1),5901)):
                m=c.Machine();lo,hi,version=fields;row=0x2ad998+18*36
                m.u.mem_write(0x6bcb7d,bytes([0,lo,hi]));m.u.mem_write(row+5,bytes([lo,hi]));m.u.mem_write(row+12,c.pack(reported))
                m.run('af_identity_publish',lo,hi,version);m.run('na_begin',2)
                m.run('na_stage_speed',0,6123);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-6123))
                self.assertEqual(m.run('af_current_advance'),100)
            m=c.Machine()
            address=c.M['symbols']['af_install_ack'];self.assertEqual(bytes(m.u.mem_read(address,4)),bytes(4))
            m.run('af_install_probe',0x901000);self.assertEqual(bytes(m.u.mem_read(address,4)),bytes(4))
            m.run('af_install_probe',address);self.assertEqual(c.words(m.u.mem_read(address,4)),(0x314b4341,))
            # A lens already recognized before RAM installation is seeded from
            # the successful model-18 cache; no detach/requery is required.
            m=c.Machine();lo,hi,version=73,73,1;row=0x2ad998+18*36
            m.u.mem_write(0x6bcb7d,bytes([0,lo,hi]));m.u.mem_write(row+5,bytes([lo,hi]));m.u.mem_write(row+12,c.pack(5000))
            address=c.M['symbols']['af_install_ack'];m.run('af_install_probe',address);m.run('na_begin',2)
            m.run('na_stage_speed',0,7123);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-3500))
        finally:c.M,c.PAYLOAD=old,blob
    def test_release_far_first_ten_sample_boundary_and_early_direction_use_actual_farm_dispatch(self):
        from test_r6_flow import FlowTests
        def seed(m,values):
            n=len(values);m.u.mem_write(0x6bc954,struct.pack('<H',n))
            m.u.mem_write(0x6bb5bc,c.pack(min(values)));m.u.mem_write(0x6bb5cc,c.pack(*values))
            m.u.mem_write(0x6bbd9c,struct.pack('<'+'h'*n,*[i*20 for i in range(n)]))
        old,blob=c.M,c.PAYLOAD
        try:
            folder=c.DELIVERY/'build/release/00800000';c.M=json.loads((folder/'capture-manifest.json').read_text(encoding='utf-8'));c.PAYLOAD=(folder/'candidate.bin').read_bytes()
            for recognized in (True,False):
                for early in (True,False):
                    m=c.Machine();m.u.mem_write(0x1a4890,bytes.fromhex('1eff2fe1'))
                    m.u.mem_write(0x199b50,bytes.fromhex('0000a0e31eff2fe1'))
                    if recognized:
                        row=0x2ad998+18*36;m.u.mem_write(0x6bcb7d,bytes([0,73,73]))
                        m.u.mem_write(row+5,bytes([73,73]));m.u.mem_write(row+12,c.pack(5000))
                        m.run('af_identity_publish',73,73,1)
                    else:m.u.mem_write(0x2adc79,b'\x13')
                    m.run('na_begin',2)
                    # 发布版不读取测试方向开关和提前量开关。
                    cycle=c.M['symbols']['af_cycle'];m.u.mem_write(cycle+32,c.pack(0,0))
                    self.assertEqual(m.run('af_current_advance'),100)
                    m.run('na_stage_speed',0,6123)
                    self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-3500 if recognized else -6123))
                    m.sends.clear();m.u.mem_write(0x6bb46c,b'\x03')
                    if early:
                        for n in range(1,4):m.run('na_start_accepted',n)
                        seed(m,[1000,1300,1700]);FlowTests.dispatch(self,m,3,0x10)
                        self.assertEqual(m.events,[0x20]);self.assertEqual(len(m.sends),1)
                        if recognized:self.assertEqual(m.sends[-1][-2:],struct.pack('<h',20000))
                    else:
                        for n in range(1,10):m.run('na_start_accepted',n)
                        seed(m,[1000,1000,1000]);FlowTests.dispatch(self,m,3,0x10)
                        self.assertFalse(m.sends)
                        m.run('na_start_accepted',10);FlowTests.dispatch(self,m,3,0x10)
                        self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-20000 if recognized else -6123))
                        before=len(m.sends);FlowTests.dispatch(self,m,3,0x10);self.assertEqual(len(m.sends),before)
        finally:c.M,c.PAYLOAD=old,blob
if __name__=='__main__':unittest.main(verbosity=2)
