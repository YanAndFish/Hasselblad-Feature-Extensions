"""首次/历史升级事务执行原厂 ARM 分配器；USB、调度和缓存为模型。"""
import hashlib, json, sys, unittest
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parent / 'CodeTests'), str(HERE.parent)]
from settings_upgrade import *
from test_native_loader import ModelIO, HoldPacket, Journal, FARM
from settings_rollback import RollbackContract, RollbackLoader
import settings_hold

class NewHoldPacket(HoldPacket):
    def write_query(self, size):
        o = self.owner
        assert size == 512 and self.packet == settings_hold.query(self.token)
        assert o.transfer_active and not o.closed
        assert o.cpu.word(old.CB) == old.ORIG_CB and o.cpu.word(old.ARG) == old.ORIG_ARG
        assert not (o.cpu.word(old.PENDING) | o.cpu.word(old.ACTIVE)) & 0x8000
        assert not o.journal or o.journal.record.get('cacheInFlight') is None
        o.effects.append((o.phase, 'hold_check', 0, self.token))
        if o.fault and o.fault(o.phase, 'hold_check', 0, self.token):
            raise OSError('injected hold ambiguity')
        return size

class Model(ModelIO, UpgradeIO):
    def __init__(self, c):
        super().__init__(c)
        if c.historical:
            # 原厂分配器构造同地址的已占用旧块；释放其前方测试占位块。
            # 这是离线堆布局，不声称重建当前硬件堆的其他分配。
            cpu = self.cpu
            cpu.phase = 'heap_init'
            prefix = cpu.alloc(c.previous_response[8] - 0x2bacb0 - 8)
            previous = cpu.alloc(c.previous_response[10] - 8)
            assert previous == c.previous_response[8]
            assert cpu.block(previous) == c.previous_response[10]
            cpu.free(prefix)
            cpu.phase = 'af'
            for a, value in c.previous_code.items():
                cpu.put(a, value)
            for a, value in c.previous_bootstrap.items():
                cpu.put(a, value)
            cpu.put(c.count, 7)
            for a, value in c.previous_hooks.items():
                cpu.put(a, value)
            for name, offset, value in (('nc_capture', 0, 0x3150434e), ('nc_capture', 4, 2),
                                       ('nc_capture', 24, 1), ('nc_capture', 28, old.EXEC_MAGIC),
                                       ('na_speed_overrides', 0, 0)):
                cpu.put(c.previous_manifest['symbols'][name] + offset, value)
        self.old_bytes = bytes(self.cpu.u.mem_read(0x39cec0, 16384)) if c.historical else None
    def hold_transport(self, packet, token):
        return NewHoldPacket(self, packet, token)

OUT = HERE / 'build/002bacc0'

def prepare(historical=True):
    c = (UpgradeContract if historical else FirstInstallContract)(FARM, nonce=31)
    io = Model(c)
    loader = UpgradeLoader(c, io)
    return c, io, loader

def install(historical=True, fault=None):
    c, io, l = prepare(historical)
    io.fault = fault
    l.preflight()
    j = Journal()
    l.attach(j)
    l.probe()
    result, header = l.stage()
    manifest = read_json(OUT / 'capture-manifest.json')
    blob = (OUT / 'candidate.bin').read_bytes()
    assert manifest['base'] == result[9]
    l.install(result, header, manifest, blob)
    return c, io, l, j

class UpgradeTests(unittest.TestCase):
    def rollback_setup(self, historical=True):
        c, io, l, j = install(historical)
        rc = RollbackContract(j.record, FARM)
        rio = Model.__new__(Model)
        UpgradeIO.__init__(rio, rc)
        rio.cpu = io.cpu
        rio.cpu.block_af()
        rio.clean = io.clean
        rio.visible = io.visible
        rio.effects = []
        rio.opens = rio.closes = 0
        rio.fault = None
        rio.suppress_probe = rio.suppress_wake = False
        return rc, rio, RollbackLoader(rc, rio)

    def test_completed_first_and_upgrade_rollback_without_allocation_or_free(self):
        for historical in (False, True):
            c, io, l = self.rollback_setup(historical)
            retained = bytes(io.cpu.u.mem_read(c.candidate['base'], len(c.candidate_blob)))
            old_retained = bytes(io.cpu.u.mem_read(0x39cec0, 16384)) if historical else None
            free = io.cpu.free_bytes()
            allocations = io.cpu.malloc_calls
            l.preflight()
            j = Journal()
            l.attach(j)
            l.probe()
            l.stage()
            l.restore()
            self.assertEqual(l.phase, 'rolled_back_until_restart')
            self.assertEqual(io.cpu.malloc_calls, allocations)
            self.assertEqual(io.cpu.free_bytes(), free)
            self.assertEqual(bytes(io.cpu.u.mem_read(c.candidate['base'], len(c.candidate_blob))), retained)
            if historical:
                self.assertEqual(bytes(io.cpu.u.mem_read(0x39cec0, 16384)), old_retained)
            for a, value in {**c.restore_bootstrap, **c.restored_hooks, **c.flash_expected}.items():
                self.assertEqual(io.cpu.word(a), value)
            self.assertIsNone(j.record['inFlight'])
            self.assertIsNone(j.record['cacheInFlight'])
            self.assertTrue(io.closed)

    def test_partial_installation_cannot_enter_completed_rollback(self):
        c, io, l, j = install()
        for field, value in (('installed', False), ('phase', 'installing_native_hooks'),
                             ('allHandlesClosed', False), ('inFlight', ['write', 1, 2])):
            record = dict(j.record)
            record[field] = value
            with self.assertRaises(ValueError):
                RollbackContract(record, FARM)

    def test_rollback_ambiguity_retains_allocation_and_blocks_retry(self):
        for phase in ('staging_rollback_gate', 'restoring_previous_hooks', 'restoring_previous_bootstrap'):
            for timing in ('before', 'after'):
                c, io, l = self.rollback_setup()
                l.preflight()
                j = Journal()
                l.attach(j)
                free = io.cpu.free_bytes()
                io.fault = lambda p, k, a, v: timing if p == phase and k == 'write' else None
                with self.assertRaises(OSError):
                    l.probe()
                    l.stage()
                    l.restore()
                self.assertTrue(io.failed)
                self.assertTrue(io.closed)
                self.assertIsNotNone(j.record['inFlight'])
                self.assertEqual(io.cpu.free_bytes(), free)
                requests = io.requests
                with self.assertRaises(RuntimeError):
                    io.read(old.CB)
                self.assertEqual(io.requests, requests)

    def test_first_and_upgrade_execute_one_new_allocation_and_restore_callbacks(self):
        for historical in (False, True):
            c, io, l, j = install(historical)
            self.assertEqual(l.phase, 'installed_settings_until_restart')
            self.assertEqual(io.cpu.malloc_calls, 1)
            self.assertEqual(j.record['allocated']['payloadBytes'], 32768)
            self.assertEqual(io.cpu.word(old.CB), old.ORIG_CB)
            self.assertEqual(io.cpu.word(old.ARG), old.ORIG_ARG)
            self.assertEqual(io.cpu.word(c.exec_ack), old.EXEC_MAGIC)
            self.assertTrue(j.record['speedOverrides'])
            self.assertFalse(j.record['predictionActuation'])
            self.assertIsNone(j.record['inFlight'])
            self.assertIsNone(j.record['cacheInFlight'])
            self.assertLess(io.requests, REQUEST_LIMIT)
            self.assertEqual(io.opens, io.closes)
            self.assertTrue(io.closed)
            for a, value in c.flash_expected.items():
                self.assertEqual(io.cpu.word(a), value)
            if historical:
                self.assertEqual(bytes(io.cpu.u.mem_read(0x39cec0, 16384)), io.old_bytes)
            print(json.dumps({'mode': j.record['installationMode'], 'requests': io.requests,
                              'writes': io.writes, 'holds': io.hold_requests, 'hardwareRequests': 0}))

    def test_rebooted_or_missing_old_image_is_zero_write_rejection(self):
        for address in (0x39cec0, 0x19d1b0, 0x2b3400, 0x39cea4):
            c, io, l = prepare()
            io.cpu.put(address, 0)
            with self.assertRaises(RuntimeError):
                l.preflight()
            self.assertEqual(io.writes, 0)

    def test_first_path_rejects_prior_af_or_uninstalled_flash(self):
        for address in (0x19d1b0, 0x2b3400, 0x2b2880):
            c, io, l = prepare(False)
            io.cpu.put(address, 1)
            with self.assertRaises(RuntimeError):
                l.preflight()
            self.assertEqual(io.writes, 0)

    def test_fixed_write_scope_and_invalid_allocations(self):
        c, io, l = prepare()
        l.preflight()
        l.attach(Journal())
        l.probe()
        result, header = l.stage()
        for a in (0x39cec0, 0x39cea4, 0x2b2880, result[8] - 4, c.request + 24):
            with self.assertRaises(ValueError):
                c.packet('write', a, 3)
        for field, value in ((9, result[9] + 4), (10, 16424), (12, 131071)):
            bad = list(result)
            bad[field] = value
            with self.assertRaises(ValueError):
                c.allocation_header_addresses(bad)
        overlap = list(result)
        overlap[8:11] = [c.previous_response[8], c.previous_response[9], 32808]
        overlap[11:13] = [1000000, 1000000 - 32808]
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            c.allocation_header_addresses(overlap)

    def test_ambiguous_writes_stop_without_retry_or_old_body_mutation(self):
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
                    result, header = l.stage()
                    l.install(result, header, read_json(OUT / 'capture-manifest.json'),
                              (OUT / 'candidate.bin').read_bytes())
                self.assertTrue(io.failed)
                self.assertTrue(io.closed)
                self.assertIsNotNone(j.record['inFlight'])
                requests = io.requests
                with self.assertRaises(RuntimeError):
                    io.read(old.CB)
                self.assertEqual(io.requests, requests)
                self.assertEqual(bytes(io.cpu.u.mem_read(0x39cec0, 16384)), io.old_bytes)

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(UpgradeTests))
    report = {'tests': result.testsRun, 'passed': result.wasSuccessful(), 'hardwareRequests': 0,
              'candidateSha256': hashlib.sha256((HERE / 'build/00800000/candidate.bin').read_bytes()).hexdigest(),
              'relocatedSha256': hashlib.sha256((OUT / 'candidate.bin').read_bytes()).hexdigest(),
              'scope': '首次/历史升级固定事务、原厂 ARM 分配器、模型 USB/调度/缓存',
              'experimentalInstallReady': False,
              'limitations': ['没有实际目标窗口、Qt 或硬件缓存验收'],
              'sourceSha256': {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in [Path(__file__), HERE / 'settings_upgrade.py', HERE / 'settings_rollback.py',
                           HERE / 'settings_hold.py', HERE / 'upgrade_primitives.py']}}
    (HERE / 'build/upgrade-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
