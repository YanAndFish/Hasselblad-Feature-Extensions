"""解析固定官方 wedge bootimage 的 PL 分区；不加载或修改 FPGA。"""

import hashlib
import struct


BOOT_SHA256 = "96449fce1e2bd5d9f181e92d84704154f97f3a758a5adeac11b466cc023f82f5"
PL_SHA256 = "8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30"


def parse_packets(raw):
    """按 UG470 解析本次使用的 Type 1/2 写报文，长度均检查边界。"""
    sync = raw.find(bytes.fromhex("665599aa"))
    if sync < 0 or sync % 4 or len(raw) % 4:
        raise ValueError("缺少对齐的同步字或输入未按字对齐")
    position, address = sync + 4, None
    previous_type, previous_opcode, previous_count = None, None, None
    packets = []
    while position < len(raw):
        start = position
        word = struct.unpack_from("<I", raw, position)[0]
        position += 4
        packet_type, opcode = word >> 29, (word >> 27) & 3
        if packet_type == 1:
            address = (word >> 13) & 0x3FFF
            count = word & 0x7FF
            if word & 0x1800:
                raise ValueError("Type 1 保留位非零")
        elif packet_type == 2:
            if previous_type != 1 or previous_count != 0 or previous_opcode != opcode:
                raise ValueError("Type 2 前没有对应的零长度 Type 1")
            count = word & 0x7FFFFFF
        else:
            raise ValueError(f"未知配置报文：{word:#x}，偏移 {start:#x}")
        if opcode not in (0, 2) or (opcode == 0 and count != 0):
            raise ValueError("报文超出本复核使用的 NOP/写入范围")
        end = position + count * 4
        if end > len(raw):
            raise ValueError("配置报文被截断")
        packets.append(
            {
                "offset": start,
                "type": packet_type,
                "opcode": opcode,
                "register": address,
                "count": count,
                "payload_offset": position,
                "values": list(struct.unpack_from(f"<{count}I", raw, position))
                if count <= 4
                else None,
            }
        )
        position = end
        previous_type, previous_opcode, previous_count = packet_type, opcode, count
    return packets


def analyze(bootimage):
    """参数是解交织后的完整官方 bootimage 字节；返回元数据，不输出分区。"""
    if len(bootimage) != 7908888 or hashlib.sha256(bootimage).hexdigest() != BOOT_SHA256:
        raise ValueError("bootimage 与固定官方来源不匹配")
    table_offset = struct.unpack_from("<I", bootimage, 0x9C)[0]
    headers = [struct.unpack_from("<16I", bootimage, table_offset + i * 64) for i in range(4)]
    if any(sum(header) & 0xFFFFFFFF != 0xFFFFFFFF for header in headers):
        raise ValueError("分区头校验失败")
    if any(headers[3][:-1]):
        raise ValueError("缺少分区头结束记录")
    header = headers[1]
    if header[0] != header[1] or header[1] != header[2] or header[6] != 0x20:
        raise ValueError("PL 分区属性与预期不符")
    start, size = header[5] * 4, header[2] * 4
    if start + size > len(bootimage):
        raise ValueError("PL 分区越界")
    raw = bootimage[start : start + size]
    if hashlib.sha256(raw).hexdigest() != PL_SHA256:
        raise ValueError("PL 分区校验失败")
    packets = parse_packets(raw)
    payloads = [packet for packet in packets if packet["count"] > 4]
    idcodes = [packet["values"][0] for packet in packets if packet["register"] == 12 and packet["count"] == 1]
    controls = [packet["values"][0] for packet in packets if packet["register"] == 5 and packet["count"] == 1]
    commands = [packet["values"][0] for packet in packets if packet["register"] == 4 and packet["count"] == 1]
    if len(payloads) != 1 or payloads[0]["register"] != 2 or payloads[0]["type"] != 2:
        raise ValueError("FDRI 结构与预期不符")
    if idcodes != [0x0372C093] or controls != [0x501, 0x501] or commands[-1] != 13:
        raise ValueError("配置身份、控制值或结束命令与预期不符")
    return {
        "boot_sha256": BOOT_SHA256,
        "partition_header_offset": table_offset,
        "partition_headers_checked": len(headers),
        "pl_offset": start,
        "pl_bytes": size,
        "pl_sha256": PL_SHA256,
        "packet_count": len(packets),
        "idcode": idcodes[0],
        "ctl0_writes": controls,
        "fdri_offset": payloads[0]["payload_offset"],
        "fdri_words": payloads[0]["count"],
        "configuration_crc_checked": False,
        "logic_netlist_recovered": False,
        "hardware_requests": 0,
    }
