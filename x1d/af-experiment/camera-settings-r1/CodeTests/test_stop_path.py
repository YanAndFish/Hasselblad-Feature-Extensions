"""执行原厂越峰事件与最终 CF 定位；不模拟传感器、镜头或任何物理时间。"""
import hashlib, json, struct, sys, unittest
from pathlib import Path
sys.dont_write_bytecode = True
from test_candidate import Machine, FARM, HERE, M, PAYLOAD, pack, config, request

class StopPathTests(unittest.TestCase):
    def test_original_peak_event_requires_four_samples_and_three_declines(self):
        for cvs, expected in (([400, 300, 200], []), ([400, 300, 200, 100], [64]),
                              ([400, 300, 350, 100], []), ([400, 300, 300, 100], [])):
            m = Machine()
            m.u.mem_write(0x1a4890, bytes.fromhex('1eff2fe1'))
            m.u.mem_write(0x6bb46c, b'\x04')
            m.u.mem_write(0x6bb59c, b'\x01\x00')
            m.u.mem_write(0x6bc954, struct.pack('<H', len(cvs)))
            m.u.mem_write(0x6bb5cc, pack(*cvs))
            m.run('na_peak_entry')
            self.assertEqual(m.events, expected)
            self.assertFalse(m.sends)

    def test_native_cf_is_a_position_offset_not_a_millisecond_delay(self):
        for current, expected_peak, expected_target in ((900, 1004, 1009), (1100, 996, 987)):
            m = Machine()
            profile = 0x2ad998 + 36 * m.run(0x198778)
            m.u.mem_write(profile + 22, bytes((7, 254, 4)))
            m.u.mem_write(0x6bb5a8, struct.pack('<h', 1000))
            m.u.mem_write(0x6bb5b0, struct.pack('<h', current))
            m.run(0x19d9cc)
            self.assertEqual(struct.unpack('<h', m.u.mem_read(0x6bb5a8, 2))[0], expected_peak)
            self.assertEqual(struct.unpack('<h', m.u.mem_read(0x6bb5ac, 2))[0], expected_target)
            self.assertEqual(len(m.sends), 1)
            self.assertEqual(m.sends[0][:6], bytes.fromhex('cf000103') + struct.pack('<h', expected_target))

    def test_saved_manual_times_do_not_fake_execution_capability(self):
        m = Machine()
        baseline = m.bank()
        reply = m.process(request(2, 1, config(time=10, fast_time=5)))
        self.assertEqual(struct.unpack_from('<I', reply, 24)[0], 0)
        self.assertEqual(struct.unpack_from('<I', reply, 40)[0], 0)
        self.assertNotEqual(m.bank(), baseline)
        self.assertEqual(struct.unpack_from('<II', reply, 44+32), (5, 10))
        self.assertEqual(struct.unpack_from('<II', reply, 88+32), (65534, 65534))

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StopPathTests))
    report = {'passed': result.wasSuccessful(), 'tests': result.testsRun, 'hardwareRequests': 0,
        'baselineSha256': FARM.sha256, 'candidateSha256': M['payload_sha256'],
        'testSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'physicalTimingVerified': False,
        'scope': '实际 ARM 越峰事件和 CF 封包执行；最终方向相关位置偏移不是毫秒停止补偿',
        'stubs': ['日志开关', '消息发送', 'AF 事件发布（越峰测试）'],
        'limitations': ['未执行物理驱动制动', '没有实际帧时间/传输延迟/制动距离标定']}
    (HERE / 'build/stop-path-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
