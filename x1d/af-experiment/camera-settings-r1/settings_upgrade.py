"""历史观察版到机内设置版的固定升级合同；导入和 report 均不连接设备。

只能用于旧观察版仍存活的同一次开机。换电重启必须零写入拒绝。
尚无 install 命令：物理窗口和最终组合包由主任务审核。
"""
import hashlib, json, struct, sys, types
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import upgrade_primitives as old
import native_loader as old_io
import settings_hold

CAPACITY = 32768
REQUEST_LIMIT = 32000
AUDIT_SHA = 'd22c49cadf8497900010cdf5dc2ded71954fa28f9e99d582f39f7b67fd6122c2'

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

class UpgradeContract(old.NativeContract):
    capacity = CAPACITY
    historical = True
    def __init__(self, farm=None, nonce=1):
        frozen = HERE / 'installed-baseline'
        sources = read_json(frozen / 'source-manifest.json')
        for name in ('native_install.py', 'native_loader.py', 'native_hold.py', 'r3_install_journal.py'):
            relative = 'x1d/af-experiment/' + name
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != sources[relative]['sha256']:
                raise ValueError('reviewed transport/journal source changed: ' + name)
        super().__init__(farm, nonce)
        factory_expected = dict(self.expected)
        audit_path = HERE / 'installed-baseline/audited-installation.json'
        if hashlib.sha256(audit_path.read_bytes()).hexdigest() != AUDIT_SHA:
            raise ValueError('historical installation audit changed')
        self.previous = p = read_json(audit_path)
        if (not p['installed'] or p['phase'] != 'installed_observation_until_restart'
                or p['inFlight'] is not None or p['cacheInFlight'] is not None
                or not p['allHandlesClosed'] or p['journalAudit']['incompleteTail']):
            raise ValueError('complete historical installation required')
        if nonce == p['bootstrapNonce']:
            raise ValueError('new installation nonce required')
        self.previous_manifest = m = p['candidate']
        self.previous_response = r = p['allocationResponse']
        previous_dir = HERE / 'installed-baseline/x1d/af-experiment/build/native-capture-r1' / f"{m['base']:08x}"
        self.previous_blob = blob = (previous_dir / 'candidate.bin').read_bytes()
        if (hashlib.sha256(blob).hexdigest() != m['payload_sha256'] or
                m != read_json(previous_dir / 'capture-manifest.json') or
                m['base'] != r[9] or r[9] != 0x39cec0 or r[10] != 16424):
            raise ValueError('fixed historical payload identity')
        self.previous_code = old.words(m['base'], blob[:m['state_start'] - m['base']])
        self.previous_hooks = {a: new for a, _, new in m['emulatorOnlyHooks']}
        self.expected.update(self.previous_code)
        self.expected.update(self.previous_hooks)
        self.previous_header = {r[8] - 8: 0, r[8] - 4: r[10] | 0x80000000}
        self.expected.update(self.previous_header)
        # bootstrap 的代码及 READY 结果绑定旧日志；count 是运行期值，预检保存。
        previous_boot = bytearray(self.bootstrap_blob)
        struct.pack_into('<13I', previous_boot, self.request - self.bootstrap['base'], *r)
        struct.pack_into('<3I', previous_boot, self.control - self.bootstrap['base'], 2, 0, 1)
        self.previous_bootstrap = old.words(self.bootstrap['base'], previous_boot)
        self.previous_bootstrap.pop(self.count)
        self.expected.update(self.previous_bootstrap)
        self.expected.pop(self.count, None)
        self.previous_count = None
        capture = m['symbols']['nc_capture']
        self.expected.update({capture: 0x3150434e, capture + 4: 2, capture + 24: 1,
                              capture + 28: old.EXEC_MAGIC, m['symbols']['na_speed_overrides']: 0})
        # 新请求仍执行原厂分配器，只扩大申请容量和更换 nonce。
        runtime = bytearray(self.bootstrap_blob)
        offset = self.request - self.bootstrap['base']
        struct.pack_into('<I', runtime, offset + 12, CAPACITY)
        checksum = 0x6c871ae5
        for value in struct.unpack_from('<5I', runtime, offset):
            checksum ^= value
        struct.pack_into('<I', runtime, offset + 20, checksum)
        self.bootstrap_blob = bytes(runtime)
        self.bootstrap_words = old.words(self.bootstrap['base'], runtime)
        self.offline = c = read_json(HERE / 'build/00800000/capture-manifest.json')
        offline_blob = (HERE / 'build/00800000/candidate.bin').read_bytes()
        for name, sha in c['source_sha256'].items():
            if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != sha:
                raise ValueError('settings source changed: ' + name)
        if (hashlib.sha256(offline_blob).hexdigest() != c['payload_sha256'] or
                c['requestedHeapCapacity'] != CAPACITY or c['baseline_sha256'] != old.BASELINE_SHA):
            raise ValueError('settings candidate identity')
        self.allowed.update({a: {v} for a, v in self.bootstrap_words.items()})
        self.allowed[self.control].add(2)
        for a, factory, _ in c['emulatorOnlyHooks']:
            if self.farm.word(a) != factory:
                raise ValueError('factory hook mismatch')
            for q in range(a & ~31, (a & ~31) + 32, 4):
                self.expected.setdefault(q, self.farm.word(q))
            self.allowed[a] = {self.previous_hooks.get(a, factory)}
        self.ranges.update((a & ~31, 32) for a, _, _ in c['emulatorOnlyHooks'])
        self.allowed[old.DESC].update(a for a, _ in self.ranges)
        self.reads.update(self.expected)
        self.reads.update(self.allowed)
        self.reads.discard(old.SGIR)
        self.reads.add(self.count)
        if not self.historical:
            # 首次路径要求原厂 AF 入口及零 bootstrap，绝不先重装观察版。
            self.expected = factory_expected
            for a, factory, _ in c['emulatorOnlyHooks']:
                for q in range(a & ~31, (a & ~31) + 32, 4):
                    self.expected.setdefault(q, self.farm.word(q))
                self.allowed[a] = {factory}
            self.previous_code = {}
            self.previous_header = {}
            self.previous_hooks = {}
            self.previous_bootstrap = {}
            self.previous_response = None
            self.reads = set(self.expected) | set(self.allowed) | set(self.guards)
            self.reads.discard(old.SGIR)
            self.reads.update((0x6badd0, 0x6bb470, 0x6baccc, 0x6bacb0, 0x6bacb4,
                               0x6bacbc, self.flash['record'] + 12))
        for low, high in ((0x1a03e0, 0x1a0960), (0x1e0a50, 0x1e0b80), (0x1e1e1c, 0x1e1ff8)):
            for a in range(low, high, 4):
                self.expected.setdefault(a, self.farm.word(a))
        self.reads.update(self.expected)
        self.hold = settings_hold.identity()
        self.identity = old.digest({'schema': 'settings-upgrade-r1', 'audit': AUDIT_SHA,
            'mode': 'historical-upgrade' if self.historical else 'factory-first-install',
            'capacity': CAPACITY, 'bootstrapCode': self.bootstrap['payloadSha256'],
            'candidate': c['payload_sha256'], 'sources': c['source_sha256'],
            'hold': self.hold, 'expected': self.expected, 'guards': self.guards,
            'primitives': hashlib.sha256((HERE / 'upgrade_primitives.py').read_bytes()).hexdigest(),
            'implementation': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def allocation_header_addresses(self, r):
        prefix = struct.unpack_from('<6I', self.bootstrap_blob, self.request - self.bootstrap['base'])
        if len(r) != 13 or tuple(r[:6]) != prefix or r[6:8] != [3, 0]:
            raise ValueError('new allocation not READY')
        raw, base, size, before, after = r[8:]
        if (raw % 8 or not 0x2bacb0 <= raw < 0x6baca0 or base != (raw + 31) & ~31
                or size % 8 or size < CAPACITY + 40 or raw - 8 + size > 0x6baca0
                or base + CAPACITY > raw - 8 + size or before - after != size or after < 131072):
            raise ValueError('new allocation capacity/accounting')
        prior = self.previous_response
        if prior and raw - 8 < prior[8] - 8 + prior[10] and prior[8] - 8 < raw - 8 + size:
            raise ValueError('new allocation overlaps retained old block')
        self.reads.update((raw - 8, raw - 4))
        return raw - 8, raw - 4

    def bind(self, r, header, manifest, blob):
        if self.candidate is not None:
            raise ValueError('only one new allocation may be bound')
        self.allocation_header_addresses(r)
        if header != (0, r[10] | 0x80000000):
            raise ValueError('original allocator ownership header')
        if (manifest['base'] != r[9] or manifest['end'] > r[9] + CAPACITY
                or manifest['baseline_sha256'] != old.BASELINE_SHA
                or manifest['source_sha256'] != self.offline['source_sha256']
                or hashlib.sha256(blob).hexdigest() != manifest['payload_sha256']
                or len(blob) != manifest['end'] - manifest['base'] or len(blob) % 32
                or [(a, v) for a, v, _ in manifest['emulatorOnlyHooks']] !=
                   [(a, v) for a, v, _ in self.offline['emulatorOnlyHooks']]):
            raise ValueError('relocated settings candidate identity/bounds')
        self.candidate = manifest
        self.candidate_blob = blob
        self.allocation = list(r)
        self.candidate_words = old.words(manifest['base'], blob)
        if set(self.candidate_words) & (set(self.expected) | set(self.allowed)):
            raise ValueError('new body overlaps retained fixed regions')
        self.allowed.update({a: {v} for a, v in self.candidate_words.items()})
        for a, _, new in manifest['emulatorOnlyHooks']:
            self.allowed[a].add(new)
        self.ranges.add((manifest['base'], len(blob)))
        self.allowed[old.DESC].add(manifest['base'])
        self.allowed[old.DESC + 4].add(len(blob))
        self.exec_ack = manifest['symbols']['nc_capture'] + 28
        self.exec_probe = manifest['symbols']['nc_execution_probe']
        if not self.exec_probe & 1 or not manifest['base'] <= self.exec_probe & ~1 < manifest['state_start']:
            raise ValueError('Thumb execution probe bounds')
        if self.allowed[self.exec_ack] != {0}:
            raise ValueError('execution ACK must initialize zero')
        self.allowed[old.CB].add(self.exec_probe)
        self.allowed[old.ARG].add(self.exec_ack)
        self.reads.update(self.candidate_words)

    def check_write_phase(self, phase, a):
        if phase in ('new', 'preflight', 'prepared', 'installed_settings_until_restart', 'rolled_back_until_restart'):
            raise ValueError('writes denied in current phase')
        if a in {address for address, _, _ in self.offline['emulatorOnlyHooks']} and phase != 'installing_native_hooks':
            raise ValueError('settings hook phase')
        super().check_write_phase(phase, a)

class FirstInstallContract(UpgradeContract):
    """原厂 AF 首次安装；正式 HFS1 必须已由主任务独立安装并通过只读校验。"""
    historical = False

class UpgradeIO(old_io.NativeIO):
    def __init__(self, contract):
        super().__init__(contract)
        self.request_limit = REQUEST_LIMIT
    def check_hold(self, label):
        return settings_hold.check(self, label)
    def hold_transport(self, packet, token):
        return settings_hold.transport(self, packet)
    # 固定上限扩大；原类仍维持其已装版本的上限和模块 globals。
    exchange = types.FunctionType(old_io.NativeIO.exchange.__code__,
                                  dict(old_io.__dict__, REQUEST_LIMIT=REQUEST_LIMIT), 'exchange',
                                  old_io.NativeIO.exchange.__defaults__)

class UpgradeLoader(old.NativeLoader):
    def preflight(self):
        super().preflight()
        if self.c.historical:
            count = self.io.read(self.c.count)
            if not 1 <= count < 0x80000000:
                raise RuntimeError('previous idle gate ACK missing')
            self.c.previous_count = count

    def attach(self, journal):
        super().attach(journal)
        self.persist(installationMode='historical-upgrade' if self.c.historical else 'factory-first-install',
                     previousAuditSha256=AUDIT_SHA if self.c.historical else None,
                     previousCandidate=self.c.previous_manifest if self.c.historical else None,
                     previousAllocation=self.c.previous_response, previousGateCount=self.c.previous_count,
                     recovery='保留两份堆块；禁止释放或自动回退；部分失败按日志阶段独立审阅')

    def stage(self):
        # 基类使用同一请求协议；其 journal 中历史固定容量在返回后立即补记。
        result, header = super().stage()
        self.persist(allocated={'rawPointer': result[8], 'payloadBase': result[9],
                                'blockBytes': result[10], 'payloadBytes': CAPACITY})
        return result, header

    def verify_previous(self):
        for a, value in {**self.c.previous_code, **self.c.previous_header}.items():
            if self.io.read(a) != value:
                raise RuntimeError('retained observation code/allocation changed')

    def verify(self):
        c = self.c
        m = c.candidate
        self.verify_flash()
        self.verify_previous()
        for a, value in c.candidate_words.items():
            if a < m['state_start'] and (a not in self.cache_verified or self.io.read(a) != value):
                raise RuntimeError('settings body verification')
        for a, _, new in m['emulatorOnlyHooks']:
            if a not in self.cache_verified or self.io.read(a) != new:
                raise RuntimeError('settings hook verification')
        if self.io.read(c.exec_ack) != old.EXEC_MAGIC:
            raise RuntimeError('settings execution ACK missing')
        bank = m['symbols']['na_config_bank']
        for a in range(bank, bank + 100, 4):
            if self.io.read(a) != c.candidate_words[a]:
                raise RuntimeError('initial settings bank changed')
        for a, value in {m['symbols']['na_adapter']: 0,
                         m['symbols']['na_speed_overrides']: 1,
                         m['symbols']['nc_capture']: 0x3150434e,
                         m['symbols']['nc_capture'] + 4: 2,
                         m['symbols']['nc_capture'] + 24: 1}.items():
            if self.io.read(a) != value:
                raise RuntimeError('initial settings state changed')

    def install(self, result, header, manifest, blob):
        # 基类 install 的固定旧入口比较改成已安装观察版入口；manifest 本身保持原厂来源。
        # 使用独立代理完成比较，不能篡改 manifest 或原类的模块 globals。
        if self.phase != 'allocated_and_gated' or not self.gated:
            raise RuntimeError('owned idle allocation required')
        c = self.c
        c.bind(result, header, manifest, blob)
        self.persist(candidate=manifest)
        self.hold_boundary('before_body')
        self.idle()
        if self.io.read(old.GATE_HOOK) != c.bootstrap_hooks[old.GATE_HOOK][1] or self.io.read(c.control) != 0:
            raise RuntimeError('idle gate lost before body')
        if tuple(self.io.read(a) for a in c.allocation_header_addresses(result)) != header:
            raise RuntimeError('heap ownership changed before body')
        self.phase_to('uploading_owned_body')
        for offset in range(0, len(blob), 1024):
            if offset:
                self.hold_boundary('body_' + str(offset))
            self.upload(manifest['base'] + offset, blob[offset:offset + 1024])
        self.sync(manifest['base'], len(blob))
        self.phase_to('executing_owned_probe')
        self.invoke(c.exec_probe, c.exec_ack, (c.exec_ack, old.EXEC_MAGIC))
        self.persist(ownedCodeExecuted=True)
        self.hold_boundary('before_native_hooks', park=True)
        self.phase_to('installing_native_hooks')
        for a, factory, new in manifest['emulatorOnlyHooks']:
            if self.io.read(a) != c.previous_hooks.get(a, factory):
                raise RuntimeError('previous AF hook changed')
            self.write(a, new)
            self.sync_hook(a)
            self.hold_boundary('native_hook_' + str(a), park=True)
        self.phase_to('verifying_gated')
        self.verify()
        self.idle()
        self.hold_boundary('before_native_release')
        self.phase_to('releasing_native_gate')
        self.write(c.control, 2)
        self.write(old.GATE_HOOK, c.bootstrap_hooks[old.GATE_HOOK][0])
        self.sync_hook(old.GATE_HOOK)
        self.phase_to('restoring_cache_slot')
        self.quiet()
        self.write(old.ARG, old.ORIG_ARG)
        self.write(old.CB, old.ORIG_CB)
        self.quiescent()
        for a, value in ((old.GATE_HOOK, c.bootstrap_hooks[old.GATE_HOOK][0]),
                         (old.WAKE_HOOK, c.bootstrap_hooks[old.WAKE_HOOK][0]),
                         (old.CB, old.ORIG_CB), (old.ARG, old.ORIG_ARG)):
            if self.io.read(a) != value:
                raise RuntimeError('temporary entry restoration failed')
        self.verify_flash()
        self.idle()
        self.phase_to('installed_settings_until_restart')
        self.persist(phase=self.phase, installed=True, mode='native_af_camera_settings',
                     predictionActuation=False, speedOverrides=True, nativeFinePreserved=True,
                     flashCodePreserved=True, previousAllocationRetained=self.c.historical,
                     requests=self.io.requests, writeRequests=self.io.writes,
                     hardwareRequests=self.io.requests if self.io.is_hardware else 0,
                     allHandlesClosed=self.io.closed)

if __name__ == '__main__':
    c = UpgradeContract()
    print(json.dumps({'hardwareRequests': 0, 'contractSha256': c.identity,
        'historicalUpgradeOnly': True, 'experimentalInstallReady': False,
        'requestedHeapCapacity': CAPACITY, 'expectedWords': len(c.expected),
        'reason': '本文件只提供离线合同；换电后旧分配证明失效，禁止沿用'}, ensure_ascii=False))
