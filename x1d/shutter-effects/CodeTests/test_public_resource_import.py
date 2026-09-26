"""验证公开资源准备入口；仅使用内存中的自造数据，不读取厂商输入。"""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

MODULE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(MODULE))
spec = importlib.util.spec_from_file_location('public_resource_prepare', MODULE / 'prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ResourceContract(unittest.TestCase):
    def test_text_roundtrip(self):
        values = {'/demo.qml': 'import QtQuick 2.0\nItem {}',
                  '/nested/说明.txt': '中文与 Unicode ☆', '/empty.txt': ''}
        self.assertEqual(prepare.read_rcc(prepare.rcc(values)), values)

    def test_invalid_header_rejected(self):
        with self.assertRaises(ValueError):
            prepare.read_rcc(b'not a resource')

    def test_truncated_payload_rejected(self):
        blob = prepare.rcc({'/demo.txt': 'example'})
        with self.assertRaises(ValueError):
            prepare.read_rcc(blob[:-1])

    def test_tree_cycle_rejected(self):
        blob = bytearray(prepare.rcc({'/demo.txt': 'example'}))
        tree = struct.unpack_from('>I', blob, 8)[0]
        struct.pack_into('>II', blob, tree + 6, 1, 0)
        with self.assertRaises(ValueError):
            prepare.read_rcc(blob)


if __name__ == '__main__':
    unittest.main()
