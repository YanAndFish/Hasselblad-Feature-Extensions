"""仅用自造文本测试离线资源工具，不读取厂商文件。"""
from pathlib import Path
import struct
import sys
import unittest
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reader import read_rcc
from writer import rcc

class Resources(unittest.TestCase):
    def test_text_roundtrip(self):
        files = {'/demo.qml': 'import QtQuick 2.0\nItem {}', '/nested/说明.txt': '中文 ☆', '/empty.txt': ''}
        self.assertEqual(read_rcc(rcc(files)), files)

    def test_invalid_header(self):
        with self.assertRaises(ValueError):
            read_rcc(b'not a resource')

    def test_truncation(self):
        with self.assertRaises(ValueError):
            read_rcc(rcc({'/demo.txt': 'example'})[:-1])

    def test_tree_cycle(self):
        blob = bytearray(rcc({'/demo.txt': 'example'}))
        tree = struct.unpack_from('>I', blob, 8)[0]
        struct.pack_into('>II', blob, tree + 6, 1, 0)
        with self.assertRaises(ValueError):
            read_rcc(blob)

if __name__ == '__main__':
    unittest.main()
