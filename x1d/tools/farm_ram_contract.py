"""X1D 1.25.0 的固定 RAM 模式读取契约；没有硬件访问接口。"""
from __future__ import annotations

from dataclasses import dataclass

from usb_diagnostic_contract import PACKET_SIZES

REQUEST_PREFIX = bytes.fromhex("2d 02 08 01 00")
RESPONSE_HEADER = bytes.fromhex("2e 02 01 08")


def check_packet_size(size):
    if type(size) is not int or size not in PACKET_SIZES:
        raise ValueError("传输长度必须来自已核对的控制端点")


def build_farm_ram_query(size):
    """唯一可生成的请求为 557；不接收任意消息 ID、节点或设置值。"""
    check_packet_size(size)
    return REQUEST_PREFIX + bytes(size - len(REQUEST_PREFIX))


@dataclass(frozen=True)
class FarmRamStatus:
    reported_value: int
    ram_mode_reported_active: bool


def parse_farm_ram_reply(packet, size):
    """只保留一字节的 getter 结果；0 包括原厂中间状态，不能解释为恢复正常。"""
    check_packet_size(size)
    if not isinstance(packet, bytes) or len(packet) != size:
        raise ValueError("回复长度不符合固定控制传输")
    if packet[:4] != RESPONSE_HEADER or packet[4] not in (0, 1):
        raise ValueError("回复种类、方向或值不符合白名单")
    return FarmRamStatus(packet[4], packet[4] == 1)
