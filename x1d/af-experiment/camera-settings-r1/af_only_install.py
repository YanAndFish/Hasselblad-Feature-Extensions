"""仅 AF 的原厂首次安装合同；不要求、不安装也不写入 HFS1。"""
import hashlib
from pathlib import Path
from settings_upgrade import *

MODE = 'factory-af-only-first-install'

class AfOnlyContract(FirstInstallContract):
    def __init__(self, farm=None, nonce=1):
        super().__init__(farm, nonce)
        # 复用已冻结的 AF/分配/缓存来源；将共存区域改为原厂只读保护。
        fm = self.flash
        self.factory_flash_expected = {
            a: self.farm.word(a) for a in self.flash_expected
            if not fm['base'] <= a < fm['base'] + fm['bytes']
        }
        for a in range(0x2b2880, self.bootstrap['base'], 4):
            if self.farm.word(a) != 0:
                raise ValueError('fixed factory empty region changed')
            self.factory_flash_expected[a] = 0
        for key, value in fm['originalHooks'].items():
            if self.factory_flash_expected[int(key)] != value:
                raise ValueError('factory flash hook source mismatch')
        for a in self.flash_expected:
            self.expected.pop(a, None)
        for a in range(fm['record'], fm['record'] + 16, 4):
            self.guards.pop(a, None)
            self.reads.discard(a)
        self.flash_expected = dict(self.factory_flash_expected)
        self.expected.update(self.factory_flash_expected)
        self.reads.update(self.expected)
        self.flash = {'mode': 'factory-read-only', 'installed': False,
            'originalHooks': fm['originalHooks'], 'emptyBase': 0x2b2880,
            'emptyEnd': self.bootstrap['base'], 'baselineSha256': old.BASELINE_SHA}
        if set(self.allowed) & set(self.factory_flash_expected):
            raise ValueError('AF writes overlap protected factory flash region')
        self.identity = old.digest({'schema': 'af-only-first-install-r1',
            'combinedSourceContract': self.identity, 'mode': MODE,
            'expected': self.expected, 'guards': self.guards, 'flash': self.flash,
            'allowed': {a: sorted(v) for a, v in self.allowed.items()},
            'implementation': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def packet(self, kind, a=None, v=None, size=512):
        if kind == 'write' and a in self.factory_flash_expected:
            raise ValueError('factory flash region is read-only')
        return super().packet(kind, a, v, size)

class AfOnlyLifecycle:
    def idle(self):
        for a in (0x6bb46c, 0x6bb598, 0x2adc78, 0x2adc8c):
            mask, value = self.c.guards[a]
            if self.io.read(a) & mask != value:
                raise RuntimeError('AF/profile changed ' + hex(a))
        for address, value in self.c.flash['originalHooks'].items():
            if self.io.read(int(address)) != value:
                raise RuntimeError('factory flash entry changed')

    def preflight(self):
        if self.phase != 'new':
            raise RuntimeError('new session required')
        self.phase_to('preflight')
        self.hold_initial()
        self.io.exchange('version')
        for a, (mask, value) in self.c.guards.items():
            if self.io.read(a) & mask != value:
                raise RuntimeError('preflight guard ' + hex(a))
        for index, (a, value) in enumerate(sorted(self.c.expected.items())):
            if index % 256 == 0:
                self.hold_boundary('preflight_' + str(index))
            if self.io.read(a) != value:
                raise RuntimeError('factory/AF code/bootstrap mismatch ' + hex(a))
        self.c.scratch_before = {a: self.io.read(a) for a in range(old.SCRATCH, old.SCRATCH + 64, 4)}
        self.idle()
        self.phase_to('prepared')

    def verify_flash(self):
        for a, value in self.c.factory_flash_expected.items():
            if self.io.read(a) != value:
                raise RuntimeError('protected factory flash region changed ' + hex(a))

class AfOnlyLoader(AfOnlyLifecycle, UpgradeLoader):
    def attach(self, journal):
        super().attach(journal)
        self.persist(installationMode=MODE, standaloneAf=True, flashInstalled=False,
            previousAuditSha256=None, previousCandidate=None, previousAllocation=None,
            recovery='保留 AF 堆块；禁止释放或自动回退；部分失败按日志阶段独立审阅')
