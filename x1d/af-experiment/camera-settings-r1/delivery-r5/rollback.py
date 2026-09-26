"""已完整安装设置版的独立回滚事务；部分安装不进入此路径，不释放堆块。"""
import hashlib, struct
from pathlib import Path
from af_only_install import *

class AfOnlyRollbackContract(AfOnlyContract):
    def __init__(self, record, farm=None):
        historical = False
        if record.get('installationMode') != MODE:
            raise ValueError('known completed installation mode required')
        self.historical = historical
        super().__init__(farm, record['bootstrapNonce'])
        if (record.get('contractSha256') != self.identity or not record.get('installed')
                or record.get('phase') != 'installed_settings_until_restart'
                or record.get('inFlight') is not None or record.get('cacheInFlight') is not None
                or not record.get('allHandlesClosed')):
            raise ValueError('unchanged complete settings installation required')
        self.source_identity = self.identity
        self.source_record = record
        m = record['candidate']
        folder = Path(__file__).resolve().parent / 'build' / f"{m['base']:08x}"
        if read_json(folder / 'capture-manifest.json') != m:
            raise ValueError('installed settings manifest changed')
        result = record['allocationResponse']
        self.bind(result, (0, result[10] | 0x80000000), m, (folder / 'candidate.bin').read_bytes())
        for a in self.candidate_words:
            self.allowed.pop(a)
        self.expected.update({a: v for a, v in self.candidate_words.items() if a < m['state_start']})
        self.expected.update({a: new for a, _, new in m['emulatorOnlyHooks']})
        self.expected.update({a: v for a, v in zip(self.allocation_header_addresses(result),
                                                 (0, result[10] | 0x80000000))})
        self.expected.update(old.words(self.request, struct.pack('<13I', *result)))
        self.expected.update({self.control: 2, self.sent: 1})
        # 首次安装的原始零 bootstrap 已被本次已验证代码替代。
        for a, v in self.bootstrap_words.items():
            if a < self.request:
                self.expected[a] = v
        self.expected.pop(self.count, None)
        capture = m['symbols']['nc_capture']
        self.expected.update({capture: 0x3150434e, capture + 4: 2, capture + 24: 1,
                              capture + 28: old.EXEC_MAGIC})
        self.restored_hooks = {a: self.previous_hooks.get(a, factory)
                               for a, factory, _ in m['emulatorOnlyHooks']}
        if historical:
            count = record.get('previousGateCount')
            if type(count) != int or not 1 <= count < 0x80000000:
                raise ValueError('previous gate count snapshot required')
            self.restore_bootstrap = dict(self.previous_bootstrap)
            self.restore_bootstrap[self.count] = count
        else:
            self.restore_bootstrap = {a: 0 for a in self.bootstrap_words}
        # 完整旧状态仅可在临时入口全部移除后恢复；不能伪造新分配结果。
        for a in self.bootstrap_words:
            self.allowed[a] = {self.restore_bootstrap[a]}
        for a in (self.control, self.count, self.sent):
            self.allowed[a].add(0)
        self.allowed[self.control].add(2)
        self.reads.update(self.expected)
        self.identity = old.digest({'schema': 'af-only-rollback-r1', 'source': self.source_identity,
            'sourceAllocation': result, 'restoreBootstrap': self.restore_bootstrap,
            'implementation': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    @classmethod
    def from_journal(cls, path, farm=None):
        from r3_install_journal import InstallJournal
        path = Path(path).resolve()
        if not path.is_relative_to(Path(__file__).resolve().parent / 'recovery'):
            raise ValueError('settings recovery path required')
        record = InstallJournal.read_record(path, read_json(path)['artifactSha256'])
        if record['journalAudit']['incompleteTail']:
            raise ValueError('incomplete durable event chain')
        return cls(record, farm)

    def check_write_phase(self, phase, a):
        if a in self.candidate_words:
            raise ValueError('rollback cannot overwrite retained settings body')
        if a in self.bootstrap_words:
            if phase == 'staging_rollback_gate' and a in (self.control, self.count, self.sent):
                return
            if phase == 'releasing_native_gate' and a == self.control:
                return
            if phase == 'restoring_previous_bootstrap':
                return
            raise ValueError('rollback bootstrap phase')
        if a in self.restored_hooks and phase != 'restoring_previous_hooks':
            raise ValueError('rollback hook phase')
        if a in self.restored_hooks:
            return
        super().check_write_phase(phase, a)

class AfOnlyRollbackLoader(AfOnlyLifecycle, old.NativeLoader):
    def preflight(self):
        super().preflight()
        if not 1 <= self.io.read(self.c.count) < 0x80000000:
            raise RuntimeError('installed gate ACK missing')

    def attach(self, journal):
        super().attach(journal)
        self.persist(operation='af-only-rollback', standaloneAf=True, flashInstalled=False, sourceContractSha256=self.c.source_identity,
            sourceCandidate=self.c.candidate, allocated=self.c.source_record['allocated'],
            previousAllocation=self.c.previous_response,
            recovery='回滚失败后保留 AF 代码及分配；仅按失败阶段审阅，不重试或自动释放')

    def stage(self):
        if self.phase != 'cache_ready':
            raise RuntimeError('cache probe required')
        self.hold_boundary('before_rollback_gate', park=True)
        self.idle()
        c = self.c
        self.phase_to('staging_rollback_gate')
        # READY 请求不变，原厂 reserve 应直接返回既有块，不再 malloc。
        for a in (c.control, c.count, c.sent):
            self.write(a, 0)
        self.sync(c.bootstrap['base'], len(c.bootstrap_blob))
        for a in (old.GATE_HOOK, old.WAKE_HOOK):
            factory, new = c.bootstrap_hooks[a]
            if self.io.read(a) != factory:
                raise RuntimeError('rollback temporary entry changed')
            self.write(a, new)
            self.sync_hook(a)
        self.phase_to('waiting_rollback_idle')
        for _ in range(64):
            if self.io.read(c.count) and self.io.read(c.sent) == 1:
                break
        else:
            raise RuntimeError('rollback idle gate ACK missing')
        self.idle()
        if ([self.io.read(c.request + 4 * i) for i in range(13)] != c.allocation
                or self.io.read(c.control) != 0):
            raise RuntimeError('rollback READY allocation changed')
        header = tuple(self.io.read(a) for a in c.allocation_header_addresses(c.allocation))
        if header != (0, c.allocation[10] | 0x80000000):
            raise RuntimeError('rollback allocation header changed')
        self.gated = True
        self.phase_to('removing_wake_entry')
        self.write(old.WAKE_HOOK, c.bootstrap_hooks[old.WAKE_HOOK][0])
        self.sync_hook(old.WAKE_HOOK)
        self.hold_boundary('rollback_gated', park=True)
        self.phase_to('rollback_gated')

    def restore(self):
        if self.phase != 'rollback_gated' or not self.gated:
            raise RuntimeError('rollback gate required')
        c = self.c
        self.idle()
        self.phase_to('restoring_previous_hooks')
        for a, _, new in c.candidate['emulatorOnlyHooks']:
            if self.io.read(a) != new:
                raise RuntimeError('settings hook changed during rollback')
            self.write(a, c.restored_hooks[a])
            self.sync_hook(a)
            self.hold_boundary('rollback_hook_' + str(a), park=True)
        for a, value in {**c.previous_code, **c.previous_header, **c.restored_hooks}.items():
            if self.io.read(a) != value:
                raise RuntimeError('previous code/allocation/hook verification')
        for a, value in c.candidate_words.items():
            if a < c.candidate['state_start'] and self.io.read(a) != value:
                raise RuntimeError('retained settings code changed')
        self.verify_flash()
        self.idle()
        self.hold_boundary('before_rollback_release')
        self.phase_to('releasing_native_gate')
        self.write(c.control, 2)
        self.write(old.GATE_HOOK, c.bootstrap_hooks[old.GATE_HOOK][0])
        self.sync_hook(old.GATE_HOOK)
        for a in (old.GATE_HOOK, old.WAKE_HOOK):
            if self.io.read(a) != c.bootstrap_hooks[a][0]:
                raise RuntimeError('rollback temporary entry remains')
        self.quiescent()
        self.idle()
        self.phase_to('restoring_previous_bootstrap')
        for a, value in sorted(c.restore_bootstrap.items()):
            self.write(a, value)
        self.sync(c.bootstrap['base'], len(c.bootstrap_blob))
        self.phase_to('restoring_cache_slot')
        self.quiet()
        self.write(old.ARG, old.ORIG_ARG)
        self.write(old.CB, old.ORIG_CB)
        self.quiescent()
        for a, value in {**c.restore_bootstrap, old.CB: old.ORIG_CB, old.ARG: old.ORIG_ARG}.items():
            if self.io.read(a) != value:
                raise RuntimeError('rollback final state changed')
        self.verify_flash()
        self.idle()
        self.phase_to('rolled_back_until_restart')
        self.persist(phase=self.phase, rolledBack=True, installed=False,
            restoredMode='native_af_observation' if c.historical else 'factory_af',
            settingsAllocationRetained=True, previousAllocationRetained=c.historical,
            requests=self.io.requests, writeRequests=self.io.writes,
            hardwareRequests=self.io.requests if self.io.is_hardware else 0,
            allHandlesClosed=self.io.closed)
