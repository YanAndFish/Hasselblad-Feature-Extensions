"""从固定官方帧构建双 IRQ 离线候选，重解全部受影响资源；无设备入口。"""
from collections import defaultdict
from copy import copy
from pathlib import Path
import hashlib
import json
import struct

HERE = Path(__file__).resolve().parents[1]
OUT = HERE/'build/mechanical-irq-candidate'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(route, plan):
    from fpga_frames import PL_SHA256, frame_ecc, dynamic_lut_masks, verify_crc, crc_word, map_frames, parse_segbits
    from fpga_bitstream import parse_packets
    from fpga_logic import Logic
    if Path.cwd().resolve() != HERE.parents[1] or not plan['found']:
        raise ValueError('工作区或布线计划不符合要求')
    extension = json.loads((HERE/'research/mechanical-irq-database-extension.json').read_text(encoding='utf-8'))
    if extension['database_commit'] != 'e8b8e8e46a91334f6232df84d36954323e15a1d1':
        raise ValueError('相邻资源数据库版本不匹配')
    route = copy(route)
    route.segbits = dict(route.segbits)
    route.active_features = dict(route.active_features)
    for name, expected in extension['resources'].items():
        data = (OUT/'database'/name).read_bytes()
        if sha(data) != expected['sha256'] or len(data) != expected['bytes']:
            raise ValueError('相邻资源数据库校验失败')
        route.segbits[name[8:-3].upper()] = parse_segbits(data)
    raw = next(iter(route.frames.values())).obj
    if sha(raw) != PL_SHA256:
        raise ValueError('仅接受已固定官方 PL 输入')
    frames = dict(route.frames)
    assignments = {}
    muxes, additions, removals = {}, defaultdict(set), defaultdict(set)

    def assign(tile, frame, bit, value):
        segment = route.grid[tile]['bits']['CLB_IO_CLK']
        if segment.get('alias'):
            raise ValueError('本补丁不写入别名 tile')
        address = int(segment['baseaddr'], 16)+frame
        absolute_bit = segment['offset']*32+bit
        key = address, absolute_bit
        if key in assignments and assignments[key] != int(value):
            raise ValueError('配置位赋值冲突')
        assignments[key] = int(value)

    for row in plan['routes']:
        for tile, feature in row['addPips']:
            dest = feature.split('.')[0]
            key = tile, dest
            if key in muxes and muxes[key] != feature:
                raise ValueError('两条路线占用同一选择端')
            muxes[key] = feature
            additions[tile].add(feature)
        for tile, feature in row['removePips']:
            removals[tile].add(feature)
    for (tile, dest), selected in muxes.items():
        db = route.segbits[route.grid[tile]['type']]
        domain = {(f, b) for feature, entries in db.items() if feature.split('.')[0] == dest
                  for f, b, _ in entries}
        values = {key: 0 for key in domain}
        for f, b, value in db[selected]:
            values[f, b] = int(value)
        for (f, b), value in values.items():
            assign(tile, f, b, value)
    inverter = plan['inverter']
    tile, slot = inverter['tile'], inverter['slot']
    prefix = route.prefix(tile, slot)+'.ALUT.INIT['
    db = route.segbits[route.grid[tile]['type']]
    for index in range(64):
        feature = prefix+f'{index:02d}]'
        value = bool(inverter['init'] & (1 << index))
        entries = db[feature]
        if len(entries) != 1 or not entries[0][2]:
            raise ValueError('LUT INIT 不是已核对的独立正配置位')
        f, b, _ = entries[0]
        assign(tile, f, b, value)
        if value:
            additions[tile].add(feature)
    changed = {}
    for (address, bit), value in assignments.items():
        old = bool(frames[address][bit//8] & (1 << (bit%8)))
        if old == bool(value):
            continue
        candidate = changed.setdefault(address, bytearray(frames[address]))
        candidate[bit//8] = (candidate[bit//8] & ~(1 << (bit%8))) | (value << (bit%8))
    frames.update(changed)
    candidate = copy(route)
    candidate.frames = frames
    candidate.active_features = {}
    candidate.selected, candidate.selected_back, candidate.ambiguities = {}, {}, {}
    # 配置帧可能被相邻 tile 共用。遍历所有覆盖这些位的 tile，不只看计划列出的 tile。
    affected, changed_features, unsupported = [], [], []
    for name, meta in route.grid.items():
        segment = meta.get('bits', {}).get('CLB_IO_CLK')
        if not segment:
            continue
        base = int(segment['baseaddr'], 16)
        lo, hi = segment['offset']*32, (segment['offset']+segment['words'])*32
        if not any(base <= a < base+segment['frames'] and lo <= b < hi
                   and route.frames[a][b//8] != frames[a][b//8] for a, b in assignments):
            continue
        affected.append(name)
        kind = segment.get('alias', {}).get('type', meta['type'])
        if kind not in route.segbits:
            unsupported.append(name)
            continue
        before, after = set(route.features(name)), set(candidate.features(name))
        added, removed = after-before, before-after
        if added != additions[name] or removed != removals[name]:
            raise ValueError('出现计划外配置变化: '+repr((name, sorted(added), sorted(removed),
                             sorted(additions[name]), sorted(removals[name]))))
        if added or removed:
            changed_features.append({'tile': name, 'added': sorted(added), 'removed': sorted(removed)})
    if unsupported:
        raise ValueError('修改位覆盖尚未解码的资源: '+repr(unsupported))
    expected = [(('PSS2_X32Y157', 'PS7_IRQF2P14'), plan['routes'][0]['source']),
                (tuple(inverter['input']), plan['routes'][1]['source']),
                (('PSS2_X32Y157', 'PS7_IRQF2P15'), tuple(inverter['output']))]
    driver_checks = []
    for target, source in expected:
        drivers, nodes, _ = candidate.drivers(target)
        if drivers != [tuple(source)]:
            raise ValueError('候选存在错误驱动或多驱动: '+repr((target, drivers)))
        driver_checks.append({'target': target, 'driver': drivers[0], 'nodeCount': len(nodes)})
    logic = Logic(candidate)
    cell = logic.cell(tuple(inverter['output']))
    # 直接解码构建后的 LUT 与来源，避免把计划中的反相意图当作实际电路。
    lut = candidate.lut(tile, slot, 'A')
    if lut['init'] != inverter['init'] or lut['inputs'][1] != [tuple(plan['routes'][1]['source'])]:
        raise ValueError('反相 LUT 的实际 INIT 或输入不符')
    database = HERE/'build/farm-sync-capture/public-database'
    dbfiles = {f'segbits_{kind.lower()}.db': (database/f'segbits_{kind.lower()}.db').read_bytes()
               for kind in ('CLBLM_L', 'CLBLM_R')}
    masks, _ = dynamic_lut_masks(route.frames, route.grid, dbfiles)
    for address, frame in changed.items():
        _, ecc = frame_ecc(frame, masks.get(address))
        word = struct.unpack_from('<I', frame, 200)[0]
        struct.pack_into('<I', frame, 200, (word & ~0x1fff) | ecc)
        if frame_ecc(frame, masks.get(address))[0] != frame_ecc(frame, masks.get(address))[1]:
            raise ValueError('候选帧 ECC 不一致')
    packets = parse_packets(raw)
    payload = [p for p in packets if p['register'] == 2 and p['count']]
    if len(payload) != 1:
        raise ValueError('只接受一段固定 FDRI 数据')
    output = bytearray(raw)
    cursor, previous = payload[0]['payload_offset'], None
    for address, frame in route.frames.items():
        row = address >> 17
        if previous is not None and row != previous:
            cursor += 808
        if raw[cursor:cursor+404] != frame.tobytes():
            raise ValueError('FDRI 帧位置与原字节不一致')
        if address in changed:
            output[cursor:cursor+404] = changed[address]
        cursor += 404
        previous = row
    crc = 0
    for packet in packets:
        if packet['opcode'] != 2 or not packet['count']:
            continue
        register, offset = packet['register'], packet['payload_offset']
        if register == 0:
            if packet['count'] != 1:
                raise ValueError('CRC 长度改变')
            struct.pack_into('<I', output, offset, crc)
            crc = 0
        elif register == 4 and struct.unpack_from('<I', output, offset)[0] & 31 == 7:
            crc = 0
        elif register not in (15, 18, 20, 21, 22):
            for position in range(offset, offset+packet['count']*4, 4):
                crc = crc_word(crc, struct.unpack_from('<I', output, position)[0], register)
    crc_checks = verify_crc(output, packets)
    if not crc_checks or not all(c['match'] for c in crc_checks):
        raise ValueError('候选配置 CRC 校验失败')
    rebuilt, _ = map_frames(output, json.loads((database/'part').read_bytes()), parse_packets(output))
    if set(rebuilt) != set(frames) or any(rebuilt[a].tobytes() != bytes(frames[a]) for a in frames):
        raise ValueError('候选序列化后配置帧不一致')
    OUT.mkdir(exist_ok=True)
    (OUT/'irq-pl-candidate.bin').write_bytes(output)
    report = {'built': True, 'installed': False, 'hardwareRequests': 0,
              'baselineFpgaSha256': PL_SHA256, 'candidateSha256': sha(output), 'bytes': len(output),
              'changedFrameCount': len(changed), 'affectedTilesChecked': affected,
              'changedFeatures': changed_features, 'driverChecks': driver_checks,
              'inverter': {'cell': cell, 'init': lut['init'], 'input1': lut['inputs'][1]},
              'onlyPlannedFeaturesChanged': True, 'crc': crc_checks, 'changedFramesEccChecked': True,
              'serializedFramesRechecked': True, 'newInterruptSoftwareImplemented': False,
              'timingConstraintsChecked': False, 'hardwareTimingMeasured': False,
              'configurationLoaderImplemented': False,
              'adjacentResourceDatabase': extension,
              'sourceHashes': {p.name: sha(p.read_bytes()) for p in
                  (Path(__file__), HERE/'research/mechanical_irq_route.py')},
              'limitations': ['结构及配置完整性检查，不代表已完成硬件静态时序或实机验证。',
                  '只有离线 PL 候选；中断处理、装载恢复、事件安全投递未完成，禁止直接安装。']}
    (OUT/'fpga-build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return candidate, report


if __name__ == '__main__':
    from mechanical_fpga_route import load
    from mechanical_irq_route import run
    route, _, _ = load()
    _, plan = run(route)
    _, report = build(route, plan)
    print({k: v for k, v in report.items() if k not in ('changedFeatures', 'affectedTilesChecked')})
