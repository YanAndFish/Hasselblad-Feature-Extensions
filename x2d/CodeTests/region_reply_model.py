"""X2D 100C 4.2.0 人工回复模型；纯内存验证，无设备或文件 I/O。"""
import binascii
import json
import random
import struct


EXPECTED_HEADER = (49, 2, 0x13572468)  # 第三个值仅为人工回显，不推定业务语义。


def firmware_crc(data):
    value = 0
    for byte in data:
        temp = ((value & 0xFF00) >> 8) ^ byte
        temp ^= (temp & 0xF0) >> 4
        value = (((value << 8) & 0xFFFFFF00) | (temp & 255)) ^ ((temp & 255) << 12) ^ ((temp & 255) << 5)
    return value & 65535


def mock_reply(command=49, function=2, echo=0x13572468, status=0, index=13, value=6):
    """仅构造人工响应；不构造设备请求。"""
    body = struct.pack('<III', status, index, value) + bytes(224)
    return struct.pack('<IIII', command, function, echo, binascii.crc_hqx(body, 0)) + body


def parse_reply(raw):
    if len(raw) != 252:
        return 'bad_length'
    command, function, echo, crc = struct.unpack_from('<IIII', raw)
    if (command, function, echo) != EXPECTED_HEADER:
        return 'unmatched_header'
    if crc != binascii.crc_hqx(raw[16:], 0):
        return 'bad_crc'
    status, index, value = struct.unpack_from('<III', raw, 16)
    if status != 0:
        return 'failure_status'
    if index != 13:
        return 'wrong_property'
    if value != 6:
        return 'different_region'
    return 'target_value_observed'


def parse_envelope(raw):
    if len(raw) != 260:
        return 'length'
    if struct.unpack_from('<HBB', raw) != (9, 5, 8):
        return 'route'
    if raw[4] != 252:
        return 'inner_length'
    if raw[257:] != bytes(3):
        return 'padding'
    return 'accepted_envelope'


def check(condition, name):
    if not condition:
        raise AssertionError(name)


def main():
    rng = random.Random(420)
    for length in [0, 1, 2, 9, 235, 236, 252, 255]:
        for _ in range(20):
            data = bytes(rng.randrange(256) for _ in range(length))
            check(firmware_crc(data) == binascii.crc_hqx(data, 0), 'CRC cross-check')
    check(firmware_crc(b'123456789') == 0x31C3, 'known vector')
    valid = mock_reply()
    cases = [
        ('CN', valid, 'target_value_observed'),
        ('JP', mock_reply(value=8), 'different_region'),
        ('2gOnly', mock_reply(value=2), 'different_region'),
        ('unknown', mock_reply(value=255), 'different_region'),
        ('set reply', mock_reply(function=1), 'unmatched_header'),
        ('other command', mock_reply(command=48), 'unmatched_header'),
        ('other echo', mock_reply(echo=7), 'unmatched_header'),
        ('failure', mock_reply(status=1), 'failure_status'),
        ('other failure', mock_reply(status=2), 'failure_status'),
        ('other property', mock_reply(index=12), 'wrong_property'),
        ('short', valid[:-1], 'bad_length'),
        ('extra', valid + b'x', 'bad_length'),
        ('changed CRC', valid[:12] + bytes(4) + valid[16:], 'bad_crc'),
        ('changed body', valid[:24] + struct.pack('<I', 8) + valid[28:], 'bad_crc'),
    ]
    for name, raw, expected in cases:
        check(parse_reply(raw) == expected, name)
    for bit in range(236 * 8):
        raw = bytearray(valid)
        raw[16 + bit // 8] ^= 1 << (bit % 8)
        check(parse_reply(raw) == 'bad_crc', 'body bit')
    for bit in range(12 * 8):
        raw = bytearray(valid)
        raw[bit // 8] ^= 1 << (bit % 8)
        check(parse_reply(raw) == 'unmatched_header', 'header bit')
    frame = struct.pack('<HBBB', 9, 5, 8, 252) + valid + bytes(3)
    outer_cases = [
        ('valid', frame, 'accepted_envelope'),
        ('short', frame[:-1], 'length'),
        ('extra', frame + b'x', 'length'),
        ('ordinary reply', struct.pack('<H', 3) + frame[2:], 'route'),
        ('wrong origin', frame[:2] + b'\x08' + frame[3:], 'route'),
        ('wrong destination', frame[:3] + b'\x09' + frame[4:], 'route'),
        ('wrong embedded length', frame[:4] + b'\xfb' + frame[5:], 'inner_length'),
        ('wrong padding', frame[:-1] + b'x', 'padding'),
    ]
    for name, raw, expected in outer_cases:
        check(parse_envelope(raw) == expected, name)
    print(json.dumps({
        'model': 'X2D 100C', 'firmware': '4.2.0',
        'source': 'synthetic-offline-response-model', 'result': 'pass',
        'crcCrossChecks': 160, 'knownVector': '31c3',
        'innerScenarios': len(cases), 'outerScenarios': len(outer_cases),
        'bodySingleBitRejections': 1888, 'headerMismatchRejections': 96,
        'deviceAccesses': 0,
        'limitations': ['无传输或会话验证', '无同头旧回复新鲜度证明', '无实机写入回读或跨启动持久验证'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
