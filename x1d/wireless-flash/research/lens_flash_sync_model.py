"""共享镜头 1.9.11 原指令的桌面同步队列回放；不含设备接口。

定时器到期由桌面测试显式注入，不代表真实计时或板级连线。
"""
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

from lens_flash_sync import SharedLensImage, HEX_SHA, IMAGE_SHA, HERE

EXPOSURE, SIGNAL_POINTER = 0x20204e68, 0x20202c6c
SEQUENCER, STOP = EXPOSURE + 4, 0x3f000


def static_checks(img):
    assert img.word(0x18f1c) == 0x2b194
    callbacks = struct.unpack('<8I', img.read(0x2b194, 32))
    assert callbacks == (0x18869, 0x189ed, 0x18235, 0x18911, 0x18109, 0x28701, 0x188a9, 0x18829)
    assert img.word(0x20dc0) == 0x20205454
    assert img.word(0x18110) == EXPOSURE
    assert img.word(0x4918) == SIGNAL_POINTER
    assert img.word(0xd564) == 0x20201814
    interface = img.initial_word(0x20201814)
    assert interface == 0x2aca8
    signal_config = img.word(interface + 4)
    assert signal_config == 0x2acd0
    out_selector, in_selector, polarity = (img.word(signal_config + o) for o in (4, 8, 12))
    assert (out_selector, in_selector, polarity) == (0x56, 0x55, 0)
    assert img.word(0x59e0) == 0x20200024
    port = img.initial_word(0x20200024 + (out_selector >> 5) * 0x110)
    assert port == 0x401c0000
    assert img.word(0x1dc10) == 0x28ebd
    assert img.word(0x1d9cc) == 1000000
    checks = []
    for at, target in (
        (0x17a7a, 0x20c20), (0x20cda, 0x4af4), (0x4b0a, 0x4ad4),
        (0x20d52, 0x2112c), (0x18ad8, 0x183d4),
        (0x183ec, 0x1dcc4), (0x183fc, 0x1dcc4),
        (0x286d4, 0x29430), (0x286ca, 0x29434),
        (0x29430, 0x4908), (0x29434, 0x491c), (0x2531c, 0x59a4),
    ):
        i = img.instructions(at, 4)[0]
        assert i.mnemonic in ('bl', 'b.w') and int(i.op_str[1:], 16) == target
        checks.append({'at': hex(at), 'target': hex(target), 'bytes': bytes(i.bytes).hex()})
    return {'callbacks': [hex(x) for x in callbacks], 'signal_config': hex(signal_config),
            'output_selector': out_selector, 'afsync_input_selector': in_selector,
            'active_level': polarity, 'port': hex(port), 'bit': out_selector & 31,
            'original_call_checks': checks}


class Replay:
    def __init__(self, img):
        self.img = img
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.uc.mem_map(0, 0x40000)
        self.uc.mem_write(0x410, img.read(0x410, 0x33834 - 0x410))
        self.uc.mem_map(0x20200000, 0x10000)
        self.uc.mem_write(0x20200000, img.initial_read(0x20200000, 0x20b4))
        self.uc.mem_map(0x401c0000, 0x1000)
        # 已由原 init 及常量表绑定的配置。不是从实机读取的 RAM。
        self.put(SIGNAL_POINTER, 0x2acd0)
        self.put(SEQUENCER + 8, 1)
        self.stubs = {}
        self.writes = []
        self.executed = []
        self.time = None
        self.uc.hook_add(UC_HOOK_CODE, self.code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.write)

    def put(self, a, v):
        self.uc.mem_write(a, struct.pack('<I', v & 0xffffffff))

    def word(self, a):
        return struct.unpack('<I', self.uc.mem_read(a, 4))[0]

    def code(self, u, at, size, _):
        self.executed.append(at)
        if at == STOP:
            u.emu_stop()
        elif at in self.stubs:
            u.reg_write(UC_ARM_REG_R0, self.stubs[at])
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def write(self, u, access, address, size, value, _):
        if address >= 0x40000000:
            assert address in (0x401c0084, 0x401c0088), hex(address)
            assert size == 4 and value == 1 << 22
            self.writes.append({'scheduled_time': self.time, 'address': hex(address),
                                'value': hex(value), 'logical_level': int(address == 0x401c0084)})

    def call(self, at, *args):
        self.executed = []
        self.uc.reg_write(UC_ARM_REG_SP, 0x2020f000)
        self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        for reg, val in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            self.uc.reg_write(reg, val & 0xffffffff)
        self.uc.emu_start(at | 1, STOP + 2, count=10000)
        assert self.executed[-1] == STOP, ('did not return', hex(at), hex(self.executed[-1]))
        return self.uc.reg_read(UC_ARM_REG_R0)

    def events(self):
        events = []
        for n in range(10):
            fn, arg, time = struct.unpack('<IIi', self.uc.mem_read(SEQUENCER + 0x18 + n * 12, 12))
            if not fn:
                break
            events.append({'callback': hex(fn & ~1), 'argument': arg, 'time': time})
        return events

    def schedule(self, exposure, sync, adjust):
        # 原 setter 保留有符号 16 位补偿；主函数为 0x183d4。
        self.call(0x18108, adjust)
        # 快门运动与完成查询不在本局部模型中。
        self.stubs = {0x18388: 0, 0x1813c: 0}
        self.call(0x183d4, exposure, sync, 0)
        assert not self.writes
        return self.events()

    def fire_scheduled(self):
        events = self.events()
        # 定时器重新装载、看门狗及完成通知使用固定成功返回。
        # 每次到期执行原 0x28ebc 分发器，随后执行原 GPIO 输出链。
        self.stubs = {0x28e66: 0, 0x2514a: 0, 0x28e2e: 0, 0x25568: 0}
        for time in sorted({e['time'] for e in events}):
            self.time = time
            self.call(0x28ebc, 0, SEQUENCER)
        assert self.word(SEQUENCER + 0xc) == len(events)
        assert len(self.writes) == len(events)
        return self.writes


def run():
    assert Path.cwd().resolve() == HERE.parents[1]
    img = SharedLensImage()
    checks = static_checks(img)
    cases = []
    for exposure, sync, adjust in ((10000, 0, 0), (10000, 0, -500),
                                   (10000, 1, 0), (10000, 1, -500),
                                   (10000, 2, 0), (1000, 2, 0),
                                   (10000, 2, -500), (10000, 2, 7000)):
        replay = Replay(img)
        events = replay.schedule(exposure, sync, adjust)
        expected = [(0x286d2, adjust), (0x286c8, adjust + 10)]
        if sync in (1, 2):
            second = exposure - 4100 if sync == 2 and adjust + 35 <= exposure - 4100 else max(adjust + 35, -55)
            expected += [(0x286d2, second), (0x286c8, second + 10000)]
        expected.sort(key=lambda e: e[1])
        assert [(int(e['callback'], 16), e['time']) for e in events] == expected
        writes = replay.fire_scheduled()
        assert [(w['scheduled_time'], w['logical_level']) for w in writes] == [(time, int(fn == 0x286c8)) for fn, time in expected]
        cases.append({'exposure_parameter': exposure, 'sync_mode': sync, 'factory_adjust': adjust,
                      'queue': events, 'virtual_gpio_writes': writes})
    report = {'status': 'offline_original_instruction_replay', 'new_hardware_requests': 0,
              'lens_version_source': 'official shared XCD 1.9.11 from XCD55V package',
              'hex_sha256': HEX_SHA, 'decoded_sha256': IMAGE_SHA,
              'current_lens_firmware_verified': False, 'board_net_verified': False,
              'physical_timing_measured': False, 'binding': checks, 'cases': cases,
              'stub_boundaries': ['shutter motion', 'timer reload and actual expiry',
                                  'watchdog and completion notification', 'GPIO selector validation'],
              'register_reference': 'https://raw.githubusercontent.com/nxp-mcuxpresso/legacy-mcux-sdk/main/devices/MIMXRT1062/MIMXRT1062.h'}
    path = HERE / 'research/lens-flash-sync-model.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'original_call_checks': len(checks['original_call_checks']), 'replay_cases': len(cases), 'hardware_requests': 0, 'path': str(path)}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False))
