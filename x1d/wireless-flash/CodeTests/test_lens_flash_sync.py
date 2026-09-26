"""原厂镜头同步队列边界与固件映射拒绝行为；仅桌面内存。"""
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research'))
from lens_flash_sync import SharedLensImage
from lens_flash_sync_model import Replay, EXPOSURE, static_checks


class LensFlashSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = SharedLensImage()

    def test_copy_boundaries_and_bss_are_not_guessed(self):
        self.assertEqual(len(self.img.read(0x33830, 4)), 4)
        for address, length in ((0x33830, 8), (0x408, 4), (0x400000, 4), (0x20202c6c, 4)):
            with self.subTest(address=hex(address)), self.assertRaises(ValueError):
                self.img.read(address, length)
        with self.assertRaises(ValueError):
            self.img.initial_read(0x202020b0, 8)

    def test_binding_keeps_afsync_separate(self):
        binding = static_checks(self.img)
        self.assertEqual(binding['output_selector'], 0x56)
        self.assertEqual(binding['afsync_input_selector'], 0x55)
        self.assertEqual(binding['active_level'], 0)

    def test_factory_adjust_is_signed_in_queue(self):
        model = Replay(self.img)
        queue = model.schedule(10000, 0, -500)
        self.assertEqual([e['time'] for e in queue], [-500, -490])
        self.assertEqual(model.word(EXPOSURE + 0xd8) & 0xffff, 0xfe0c)
        self.assertEqual([w['logical_level'] for w in model.fire_scheduled()], [0, 1])

    def test_second_pulse_transition_and_clamp_boundaries(self):
        # A+35 == E-4100 时走曝光参数分支；相邻值及 -55 钳制单独验证。
        for exposure, adjust, sync, second in ((4134, 0, 2, 35), (4135, 0, 2, 35),
                                              (4136, 0, 2, 36), (10000, -91, 1, -55),
                                              (10000, -90, 1, -55), (10000, -89, 1, -54)):
            with self.subTest(exposure=exposure, adjust=adjust, sync=sync):
                model = Replay(self.img)
                queue = model.schedule(exposure, sync, adjust)
                on_times = [e['time'] for e in queue if e['callback'] == '0x286d2']
                self.assertEqual(on_times, [adjust, second])
                self.assertEqual(queue[-1]['time'], second + 10000)
                self.assertEqual([w['logical_level'] for w in model.fire_scheduled()], [0, 1, 0, 1])


if __name__ == '__main__':
    unittest.main()
