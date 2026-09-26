"""待机授权入口：模拟完整装载和未知写入立即停止，零实机请求。"""
import unittest
from test_delivery import prepare,Journal,read_json,old
from temporary_install import TemporaryLoader
from candidate import build

class StandbyTests(unittest.TestCase):
    def test_complete_without_gui_hold(self):
        c,io,_=prepare(profile='release');l=TemporaryLoader(c,io)
        io.hold_transport=lambda *a:(_ for _ in ()).throw(AssertionError('GUI hold queried'))
        l.preflight();self.assertEqual(io.writes,0)
        l.attach(Journal());l.probe();result,header=l.stage()
        manifest,out=build(result[9],profile='release')
        l.install(result,header,manifest,(out/'candidate.bin').read_bytes())
        self.assertEqual(l.phase,'installed_settings_until_restart')
        self.assertEqual(io.hold_requests,0);self.assertTrue(io.closed)
        self.assertEqual(io.cpu.word(old.CB),old.ORIG_CB)
        self.assertEqual(io.cpu.word(old.ARG),old.ORIG_ARG)

    def test_unknown_write_stops(self):
        c,io,_=prepare(profile='release');l=TemporaryLoader(c,io)
        l.preflight();j=Journal();l.attach(j)
        io.fault=lambda phase,kind,a,v:'after' if kind=='write' else None
        with self.assertRaises(OSError):l.probe()
        count=io.requests
        with self.assertRaises(RuntimeError):l.hold_boundary('after-error')
        self.assertEqual(io.requests,count);self.assertTrue(io.closed)
        self.assertIsNotNone(j.record['inFlight'])
