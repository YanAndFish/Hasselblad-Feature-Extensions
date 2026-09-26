"""组合窗口固定查询；不创建、延长或释放设备窗口。"""
import hashlib, sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import native_hold as legacy

MIN_REMAINING_MS = 180000
SEGMENT_MS = 120000
COMMAND = '/tmp/hbl-x1d-combined/system-check --require-held-min-ms 180000'
SUCCESS = legacy.SUCCESS
TIMEOUT_MS = 20000
MAX_CHECKS = 96
CHECKER = 'x1d/combined-runtime/build/fixed/install-window-e373262db5b23f56/system-check'
CHECKER_SHA = 'e373262db5b23f567b22060f1a61687c723cbbbae3c1e237e60728015d3ccca0'

def identity():
    if hashlib.sha256((ROOT / CHECKER).read_bytes()).hexdigest() != CHECKER_SHA:
        raise ValueError('fixed combined checker changed')
    legacy.helpers()  # 验证固定封包纯函数来源。
    return {'command': COMMAND, 'successOutput': SUCCESS.decode('ascii'),
            'minimumRemainingMs': MIN_REMAINING_MS, 'segmentBudgetMs': SEGMENT_MS,
            'targetExecutableSha256': CHECKER_SHA, 'targetExecutableBytes': 22436,
            'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

def query(token):
    import struct
    if type(token) != int or not 1 <= token <= 0xffffffff:
        raise ValueError('hold token')
    make, crc, header, _ = legacy.helpers()
    packet = bytearray(make(COMMAND))
    if len(packet) != 257 or packet[:5] != header:
        raise ValueError('hold request framing')
    struct.pack_into('<I', packet, 13, token)
    if struct.unpack_from('<I', packet, 17)[0] != crc(packet[21:]):
        raise ValueError('hold request CRC')
    return bytes(packet) + bytes(255)

# 复用已审阅流程的函数代码，以独立 globals 绑定新固定命令；不修改旧模块状态。
import types
_bindings = dict(legacy.__dict__)
_bindings.update(globals())
check = types.FunctionType(legacy.check.__code__, _bindings, 'check')
reply = legacy.reply
transport = legacy.transport
