"""X1D 1.25.0 FX3 单项状态读取的离线数据契约；没有 USB、设备或执行入口。"""
from __future__ import annotations

from dataclasses import dataclass
import struct

PACKET_SIZES = frozenset((64, 512, 1024))
REQUEST_PREFIX = bytes.fromhex("71 04 08 09 00")
RESPONSE_HEADER = bytes.fromhex("72 04 09 08")


def _check_packet_size(packet_size: int) -> None:
    if type(packet_size) is not int or packet_size not in PACKET_SIZES:
        raise ValueError("传输长度必须来自已核对的原厂控制端点")


def build_fx3_link_query(packet_size: int) -> bytes:
    """只生成一种正常 usbhost → FX3 读取；其余部分补零，不提供任意 ID 或节点。"""
    _check_packet_size(packet_size)
    return REQUEST_PREFIX + bytes(packet_size - len(REQUEST_PREFIX))


@dataclass(frozen=True)
class Fx3LinkStatus:
    flags: int
    link_active: bool
    super_speed: bool


def parse_fx3_link_reply(packet: bytes, packet_size: int) -> Fx3LinkStatus:
    """只保留 8 字节语义区的已知状态；丢弃填充区，不输出原始收包。"""
    _check_packet_size(packet_size)
    if not isinstance(packet, bytes) or len(packet) != packet_size:
        raise ValueError("回复长度不符合固定传输契约")
    if packet[:4] != RESPONSE_HEADER:
        raise ValueError("回复种类或方向不符合白名单")
    flags = struct.unpack_from("<I", packet, 4)[0]
    if flags not in (0, 1, 3):
        raise ValueError("回复含该固件 getter 未定义的状态")
    return Fx3LinkStatus(flags, bool(flags & 1), bool(flags & 2))
