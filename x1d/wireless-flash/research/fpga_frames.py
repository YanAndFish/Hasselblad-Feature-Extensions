"""固定官方 PL 的离线帧映射、CRC 与局部 ECC 复核；不接触硬件。

调用方提供内存中的原始字节和公开数据库。此模块不联网、不读取设备，
不输出修改后的配置。CRC/ECC 算法参考 Project X-Ray；数据库版本见文档。
"""

import hashlib
import json
import struct


PL_SHA256 = "8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30"
DATABASE_COMMIT = "e8b8e8e46a91334f6232df84d36954323e15a1d1"
INPUT_HASHES = {
    "part": "a6b5d444e85ef56b911f9c608d9f6564d17a85c7d19509f564c73bbb6cc3437d",
    "tilegrid": "a3b2ec28c10ba7a40471e4aa808c9c0ee1fec5e2852c6ec45dcc04b139de3f7f",
    "segbits_clblm_l.db": "07dca7c6b00f07a2a255f5178153c42bf16aff202623f2e3bc4bb0f2b974ba41",
    "segbits_clblm_r.db": "3ddfeca1b01bdc04b4f1b3d0dc73cf39f4230708fbbcb5b6170d5b50dc49ad64",
}


def require_hash(data, expected, name):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"{name} 不属于本次固定输入")


def crc_table():
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
        table.append(value)
    return table


CRC_TABLE = crc_table()


def crc_word(crc, value, register):
    for shift in (0, 8, 16, 24):
        crc = (crc >> 8) ^ CRC_TABLE[(crc ^ (value >> shift)) & 255]
    for bit in range(5):
        crc = (crc >> 1) ^ (0x82F63B78 if (crc ^ (register >> bit)) & 1 else 0)
    return crc


def verify_crc(raw, packets):
    """使用 fpga_bitstream.parse_packets 的 register 字段，不更改 CRC。"""
    crc, checks = 0, []
    for packet in packets:
        if packet["opcode"] != 2 or not packet["count"]:
            continue
        register = packet["register"]
        offset = packet["payload_offset"]
        if register == 0:
            if packet["count"] != 1:
                raise ValueError("本输入 CRC 写入长度应为一个字")
            stored = struct.unpack_from("<I", raw, offset)[0]
            checks.append({"offset": packet["offset"], "stored": stored,
                           "calculated": crc, "match": stored == crc})
            crc = 0
        elif register == 4 and struct.unpack_from("<I", raw, offset)[0] & 31 == 7:
            crc = 0
        elif register not in (15, 18, 20, 21, 22):
            if not 0 <= register < 32:
                raise ValueError("寄存器不在当前 CRC 地址范围")
            for word_offset in range(offset, offset + packet["count"] * 4, 4):
                crc = crc_word(crc, struct.unpack_from("<I", raw, word_offset)[0], register)
    return checks


def map_frames(raw, part, packets):
    writes = [p for p in packets if p["register"] == 2 and p["count"]]
    ids = [p for p in packets if p["register"] == 12 and p["count"] == 1]
    if len(writes) != 1 or len(ids) != 1 or ids[0]["values"] != [part["idcode"]]:
        raise ValueError("PL 配置目标或 FDRI 数量不符合固定输入")
    packet = writes[0]
    payload = memoryview(raw)[packet["payload_offset"]:
                              packet["payload_offset"] + packet["count"] * 4]
    frames, padding, cursor = {}, [], 0
    for bus_id, bus in ((0, "CLB_IO_CLK"), (1, "BLOCK_RAM")):
        for bottom, half in ((0, "top"), (1, "bottom")):
            rows = part["global_clock_regions"][half]["rows"]
            for row in sorted(map(int, rows)):
                columns = rows[str(row)]["configuration_buses"][bus]["configuration_columns"]
                for column in sorted(map(int, columns)):
                    for minor in range(columns[str(column)]["frame_count"]):
                        address = (bus_id << 23) | (bottom << 22) | (row << 17) | (column << 7) | minor
                        frame = payload[cursor * 404:(cursor + 1) * 404]
                        if len(frame) != 404 or address in frames:
                            raise ValueError("帧被截断或地址重复")
                        frames[address] = frame
                        cursor += 1
                pad = payload[cursor * 404:(cursor + 2) * 404]
                if len(pad) != 808 or any(pad):
                    raise ValueError("固定输入的行末两帧零填充不匹配")
                padding.append({"bus": bus, "bottom": bottom, "row": row, "index": cursor})
                cursor += 2
    if cursor * 404 != len(payload):
        raise ValueError("帧映射没有精确覆盖 FDRI 数据")
    return frames, padding


def ecc_tables():
    tables = []
    for index in range(101):
        base = index * 32 + (0x1360 if index > 0x25 else 0x1340 if index > 6 else 0x1320)
        word_tables = []
        for byte in range(4):
            values = []
            for value in range(256):
                contribution = 0
                for bit in range(8):
                    if value & (1 << bit):
                        contribution ^= base + byte * 8 + bit
                values.append(contribution)
            word_tables.append(values)
        tables.append(word_tables)
    return tables


ECC_TABLES = ecc_tables()


def frame_ecc(frame, masks=None):
    """masks 仅用于独立复核 LUTRAM/SRL 屏蔽候选，不改变输入。"""
    words, ecc = struct.unpack("<101I", frame), 0
    for index, value in enumerate(words):
        if masks:
            value &= ~masks.get(index, 0)
        if index == 50:
            value &= 0xFFFFE000
        tables = ECC_TABLES[index]
        ecc ^= (tables[0][value & 255] ^ tables[1][(value >> 8) & 255]
                ^ tables[2][(value >> 16) & 255] ^ tables[3][value >> 24])
    ecc ^= ((ecc & 0xFFF).bit_count() & 1) << 12
    return words[50] & 0x1FFF, ecc & 0x1FFF


def parse_segbits(data):
    features = {}
    for line in data.decode("ascii").splitlines():
        fields = line.split()
        if not fields:
            continue
        entries = []
        for term in fields[1:]:
            frame, bit = map(int, term.lstrip("!").split("_"))
            entries.append((frame, bit, not term.startswith("!")))
        features[fields[0].split(".", 1)[1]] = entries
    return features


def feature_matches(frames, tile, entries):
    segment = tile["bits"]["CLB_IO_CLK"]
    base, offset = int(segment["baseaddr"], 16), segment["offset"] * 32
    return all(bool(frames[base + frame][(offset + bit) // 8]
                    & (1 << ((offset + bit) % 8))) == value
               for frame, bit, value in entries)


def dynamic_lut_masks(frames, grid, dbfiles):
    databases = {kind: parse_segbits(dbfiles[f"segbits_{kind.lower()}.db"])
                 for kind in ("CLBLM_L", "CLBLM_R")}
    masks, count = {}, 0
    for tile in grid.values():
        if tile["type"] not in databases:
            continue
        features = databases[tile["type"]]
        segment = tile["bits"]["CLB_IO_CLK"]
        base, offset = int(segment["baseaddr"], 16), segment["offset"] * 32
        for letter in "ABCD":
            prefix = f"SLICEM_X0.{letter}LUT."
            if not any(feature_matches(frames, tile, features[prefix + kind])
                       for kind in ("RAM", "SRL")):
                continue
            count += 1
            for key, entries in features.items():
                if key.startswith(prefix + "INIT["):
                    for frame, bit, _ in entries:
                        word, within = divmod(offset + bit, 32)
                        words = masks.setdefault(base + frame, {})
                        words[word] = words.get(word, 0) | (1 << within)
    return masks, count


def analyze(raw, part_data, grid_data, dbfiles, packets):
    require_hash(raw, PL_SHA256, "PL")
    require_hash(part_data, INPUT_HASHES["part"], "part")
    require_hash(grid_data, INPUT_HASHES["tilegrid"], "tilegrid")
    for name in ("segbits_clblm_l.db", "segbits_clblm_r.db"):
        require_hash(dbfiles[name], INPUT_HASHES[name], name)
    part, grid = json.loads(part_data), json.loads(grid_data)
    frames, padding = map_frames(raw, part, packets)
    missing = [(name, bus) for name, tile in grid.items() for bus, segment in tile["bits"].items()
               if int(segment["baseaddr"], 16) not in frames]
    if missing:
        raise ValueError("数据库资源无法映射到配置帧")
    masks, count = dynamic_lut_masks(frames, grid, dbfiles)
    raw_failures, masked_failures = [], []
    for address, frame in frames.items():
        stored, calculated = frame_ecc(frame)
        if stored != calculated:
            raw_failures.append(address)
        stored, calculated = frame_ecc(frame, masks.get(address))
        if stored != calculated:
            masked_failures.append(address)
    return {
        "database_commit": DATABASE_COMMIT, "crc": verify_crc(raw, packets),
        "frame_count": len(frames), "padding_frame_count": len(padding) * 2,
        "tile_count": len(grid), "raw_ecc_mismatches": raw_failures,
        "dynamic_lut_count": count, "dynamic_mask_frame_count": len(masks),
        "ecc_mismatches_after_lut_mask": masked_failures,
        "physical_exposure_signal_identified": False,
    }
