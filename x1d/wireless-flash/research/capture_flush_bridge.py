"""官方 X1D 1.25.0 的曝光通知、冲洗应答及镜头命令离线证据。"""
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
FARM_SHA = '317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
SUC_SHA = '6bce5b264f431250be952dcfcaefee45a435a6355ebc22b45c9e824c165725a7'


def run(farm, suc):
    assert Path.cwd().resolve() == HERE.parents[1]
    assert hashlib.sha256(farm.data).hexdigest() == FARM_SHA
    assert hashlib.sha256(suc.data).hexdigest() == SUC_SHA
    word = lambda image, a: struct.unpack('<I', image.read(a, 4))[0]
    names = {}
    for message, expected in ((0x30, 'image_sensor_exposure_start_event'),
                              (0x19, 'image_calib_sensor_flush_req'),
                              (0x2a, 'image_sensor_flush_req'),
                              (0x21d, 'image_sensor_flush_combined_req'),
                              (0x3ee, 'image_sensor_flush_fsync_req')):
        a = word(farm, 0x29effc + message * 4)
        name = farm.read(a, 96).split(b'\0')[0].decode('ascii')
        assert name == expected, (hex(message), name)
        names[hex(message)] = {'name': name, 'pointer': hex(a)}
    assert [word(suc, a) for a in (0x08004368, 0x080047d0, 0x08006178, 0x08004df4)] == [0x200034a4, 0x200034a4, 0x08004de1, 0x200034a0]
    assert struct.unpack('<6I', suc.read(0x08022538, 24)) == (0x08004355, 0x080223fc, 0x100, 0, 5, 0x200034a0)
    assert suc.read(0x080223fc, 14).split(b'\0')[0] == b'CameraHandler'
    assert word(suc, 0x0800e154) == 0x0800d95d
    assert word(suc, 0x0800e158) == 0x0800d949
    calls = []
    for name, img, pairs in (
        ('FARM', farm, ((0x1c383c, 0x1e80d0), (0x1c52a0, 0x1c3810),
                        (0x1c52e4, 0x1c4dc8), (0x1c4ea0, 0x1e80d0))),
        ('SUC', suc, ((0x080053de, 0x0800ed04), (0x080053e4, 0x0800ec9c),
                      (0x080053f4, 0x080020cc), (0x08004358, 0x080060f0),
                      (0x0800d954, 0x080047c0), (0x0800d968, 0x080047c0),
                      (0x08004dec, 0x08002194), (0x08009676, 0x080086ac))),
    ):
        for at, target in pairs:
            i = img.instructions(at, 4)[0]
            assert i.mnemonic == 'bl' and int(i.op_str[1:], 16) == target
            calls.append({'image': name, 'at': hex(at), 'target': hex(target), 'bytes': bytes(i.bytes).hex()})
    snippets = []
    for name, img, spans in (
        ('FARM', farm, ((0x1c3810, 0x1c3848), (0x1c4dc8, 0x1c4eac), (0x1c5240, 0x1c52e8))),
        ('SUC', suc, ((0x080053c2, 0x0800541c), (0x0800ec9c, 0x0800ed30),
                      (0x0800d948, 0x0800d96e), (0x080047c0, 0x080047ce),
                      (0x08006128, 0x08006132), (0x08004de0, 0x08004df2),
                      (0x08009554, 0x0800967e))),
    ):
        for begin, end in spans:
            snippets.append({'image': name, 'begin': hex(begin), 'end_exclusive': hex(end),
                             'instructions': [f'{i.address:08x} {i.mnemonic} {i.op_str}' for i in img.instructions(begin, end-begin)]})
    report = {'status': 'offline_static_binding', 'new_hardware_requests': 0,
              'farm_sha256': FARM_SHA, 'suc_sha256': SUC_SHA, 'message_names': names,
              'original_call_checks': calls, 'snippets': snippets,
              'note': 'G7R1 实机通知记录不区分三个 caller，不能据此确定该次拍摄走哪一个；此处是原厂普通冲洗路径的静态衔接。'}
    path = HERE / 'research/capture-flush-bridge.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'message_names': len(names), 'original_calls': len(calls), 'hardware_requests': 0, 'path': str(path)}
