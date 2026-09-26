"""仅 AF 的首次/回滚事务；执行原厂 ARM 分配器，USB/缓存/调度均为模型。"""
import hashlib, json, sys, unittest
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from test_upgrade import Model, Journal, FARM, OUT
from af_only_install import *
from af_only_rollback import AfOnlyRollbackContract, AfOnlyRollbackLoader

def prepare():
    c = AfOnlyContract(FARM, nonce=41)
    io = Model(c)
    return c, io, AfOnlyLoader(c, io)

def install():
    c, io, l = prepare()
    l.preflight()
    j = Journal()
    l.attach(j)
    l.probe()
    r, h = l.stage()
    l.install(r, h, read_json(OUT / 'capture-manifest.json'), (OUT / 'candidate.bin').read_bytes())
    return c, io, l, j

def rollback_setup():
    c, io, l, j = install()
    rc = AfOnlyRollbackContract(j.record, FARM)
    rio = Model.__new__(Model)
    UpgradeIO.__init__(rio, rc)
    rio.cpu = io.cpu
    rio.cpu.block_af()
    rio.clean, rio.visible = io.clean, io.visible
    rio.effects = []
    rio.opens = rio.closes = 0
    rio.fault = None
    rio.suppress_probe = rio.suppress_wake = False
    return rc, rio, AfOnlyRollbackLoader(rc, rio)

class AfOnlyTests(unittest.TestCase):
    def assert_flash_preserved(self, c, io):
        for a, value in c.factory_flash_expected.items():
            self.assertEqual(io.cpu.word(a), value)
        self.assertFalse(any(kind == 'write' and a in c.factory_flash_expected
                             for _, kind, a, _ in io.effects))

    def test_full_first_install_without_hfs1(self):
        c, io, l, j = install()
        self.assertEqual(l.phase, 'installed_settings_until_restart')
        self.assertEqual(j.record['installationMode'], MODE)
        self.assertFalse(j.record['flashInstalled'])
        self.assertEqual(io.cpu.malloc_calls, 1)
        self.assertEqual(j.record['allocated']['payloadBytes'], 32768)
        self.assertEqual(len(c.candidate['emulatorOnlyHooks']), 14)
        self.assertEqual(io.cpu.word(old.CB), old.ORIG_CB)
        self.assertEqual(io.cpu.word(old.ARG), old.ORIG_ARG)
        self.assertEqual(io.cpu.word(c.exec_ack), old.EXEC_MAGIC)
        self.assertTrue(j.record['speedOverrides'])
        self.assertFalse(j.record['predictionActuation'])
        self.assertIsNone(j.record['inFlight'])
        self.assertIsNone(j.record['cacheInFlight'])
        self.assertLess(io.requests, REQUEST_LIMIT)
        self.assertTrue(io.closed)
        self.assertEqual(io.opens, io.closes)
        self.assert_flash_preserved(c, io)
        print(json.dumps({'mode': MODE, 'requests': io.requests, 'writes': io.writes,
                          'holds': io.hold_requests, 'hardwareRequests': 0}))

    def test_existing_af_hfs1_or_nonempty_region_rejected_before_writes(self):
        for a in (0x19d1b0, 0x2b3400, 0x2b2880, 0x2b31b0, 0x2b33fc, 0x21409c):
            c, io, l = prepare()
            io.cpu.put(a, io.cpu.word(a) ^ 1)
            with self.assertRaises(RuntimeError):
                l.preflight()
            self.assertEqual(io.writes, 0)

    def test_protected_regions_not_writable(self):
        c, io, l = prepare()
        for a in c.factory_flash_expected:
            with self.assertRaises(ValueError):
                c.packet('write', a, c.factory_flash_expected[a])
        l.preflight()
        l.attach(Journal())
        l.probe()
        r, h = l.stage()
        for field, value in ((9, r[9] + 4), (10, 16424), (12, 131071)):
            bad = list(r)
            bad[field] = value
            with self.assertRaises(ValueError):
                c.allocation_header_addresses(bad)

    def test_complete_rollback_restores_factory_without_malloc_or_free(self):
        c, io, l = rollback_setup()
        retained = bytes(io.cpu.u.mem_read(c.candidate['base'], len(c.candidate_blob)))
        allocations, free = io.cpu.malloc_calls, io.cpu.free_bytes()
        l.preflight()
        j = Journal()
        l.attach(j)
        l.probe()
        l.stage()
        l.restore()
        self.assertEqual(l.phase, 'rolled_back_until_restart')
        self.assertEqual(j.record['restoredMode'], 'factory_af')
        self.assertEqual(io.cpu.malloc_calls, allocations)
        self.assertEqual(io.cpu.free_bytes(), free)
        self.assertEqual(bytes(io.cpu.u.mem_read(c.candidate['base'], len(c.candidate_blob))), retained)
        for a, value in {**c.restored_hooks, **c.restore_bootstrap}.items():
            self.assertEqual(io.cpu.word(a), value)
        self.assertIsNone(j.record['inFlight'])
        self.assertIsNone(j.record['cacheInFlight'])
        self.assertTrue(io.closed)
        self.assert_flash_preserved(c, io)

    def test_combined_or_incomplete_journal_rejected(self):
        c, io, l, j = install()
        for field, value in (('installationMode', 'factory-first-install'),
                ('installationMode', 'historical-upgrade'), ('installed', False),
                ('phase', 'installing_native_hooks'), ('allHandlesClosed', False),
                ('inFlight', ['write', 1, 2]), ('cacheInFlight', {'pending': True})):
            record = dict(j.record)
            record[field] = value
            with self.assertRaises(ValueError):
                AfOnlyRollbackContract(record, FARM)

    def test_install_ambiguity_stops_without_flash_writes(self):
        for phase in ('cache_probe', 'staging_idle_allocation', 'uploading_owned_body',
                      'installing_native_hooks', 'releasing_native_gate'):
            for timing in ('before', 'after'):
                c, io, l = prepare()
                l.preflight()
                j = Journal()
                l.attach(j)
                io.fault = lambda p, k, a, v: timing if p == phase and k == 'write' else None
                with self.assertRaises(OSError):
                    l.probe()
                    r, h = l.stage()
                    l.install(r, h, read_json(OUT / 'capture-manifest.json'), (OUT / 'candidate.bin').read_bytes())
                self.assertTrue(io.failed)
                self.assertTrue(io.closed)
                self.assertIsNotNone(j.record['inFlight'])
                requests = io.requests
                with self.assertRaises(RuntimeError):
                    io.read(old.CB)
                self.assertEqual(io.requests, requests)
                self.assert_flash_preserved(c, io)

    def test_rollback_ambiguity_retains_heap_and_stops(self):
        for phase in ('staging_rollback_gate', 'restoring_previous_hooks', 'restoring_previous_bootstrap'):
            for timing in ('before', 'after'):
                c, io, l = rollback_setup()
                l.preflight()
                j = Journal()
                l.attach(j)
                allocations, free = io.cpu.malloc_calls, io.cpu.free_bytes()
                io.fault = lambda p, k, a, v: timing if p == phase and k == 'write' else None
                with self.assertRaises(OSError):
                    l.probe()
                    l.stage()
                    l.restore()
                self.assertTrue(io.failed)
                self.assertTrue(io.closed)
                self.assertIsNotNone(j.record['inFlight'])
                self.assertEqual(io.cpu.malloc_calls, allocations)
                self.assertEqual(io.cpu.free_bytes(), free)
                requests = io.requests
                with self.assertRaises(RuntimeError):
                    io.read(old.CB)
                self.assertEqual(io.requests, requests)
                self.assert_flash_preserved(c, io)

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AfOnlyTests))
    paths = [Path(__file__)] + [HERE / name for name in ('af_only_install.py', 'af_only_rollback.py', 'af_only_loader.py')]
    report = {'passed': result.wasSuccessful(), 'tests': result.testsRun, 'hardwareRequests': 0,
        'candidateSha256': hashlib.sha256((HERE / 'build/00800000/candidate.bin').read_bytes()).hexdigest(),
        'relocatedSha256': hashlib.sha256((OUT / 'candidate.bin').read_bytes()).hexdigest(),
        'sourceSha256': {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'scope': '独立 AF 原厂首次安装/回滚；原厂 ARM 分配器；模型 USB/缓存/调度；无 HFS1 驻留'}
    (HERE / 'build/af-only-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
