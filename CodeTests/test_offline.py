"""离线容器验证的边界检查，不下载、不打开设备。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_firmware import reference_constants
from extract_system import ranges


class OfflineBoundaryTests(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(ranges("4,0,1,10,12"), [(0, 1), (10, 12)])
        for value in ("3,0,1,2", "2,4,3", "2,-1,2", "2,0,131073", "2,1,1"):
            with self.assertRaises(ValueError):
                ranges(value)

    def test_reference_is_literal_only(self):
        # 使用人工零值样例；没有实际密钥材料。
        source = "\n".join(name + " = bytes(" + repr([0] * 16) + ")" for name in ("STATIC_KEY", "IV_SALT", "MAGIC_HASH_SALT"))
        self.assertEqual(len(reference_constants(source)), 3)
        with self.assertRaises(ValueError):
            reference_constants(source.replace("bytes(", "dangerous_function("))
        with self.assertRaises(ValueError):
            reference_constants("STATIC_KEY = arbitrary_call()")


if __name__ == "__main__":
    unittest.main()
