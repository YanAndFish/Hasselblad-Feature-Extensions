"""唯一获准的 sutest RAM 缓存查询；纯封装/解析，不访问设备。"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "x1d/references/hasselblad-x1d-reverse-engineering-87b39648a962"
UPSTREAM_SHA = {
    "x1d_usb_pull_file.py": "63bf84f88697090d1a879338895c0b4fd8e0b4a58e58a494e8f5abb9a4ebf109",
    "x1d_usb_exec.py": "5fb11b102c557a6cc3fd554254f747facf86cfcb3e8eb40684ce6a78e9e6fd0a",
}
COMMAND = ("exec /usr/bin/busctl --system --auto-start=no "
           "--allow-interactive-authorization=no --timeout=2s "
           "call com.hasselblad.farm /farm org.freedesktop.DBus.Properties "
           "Get ss com.hasselblad.farm ram_only_mode")
PACKET_SIZE = 512
PAYLOAD_SIZE = 252
REQUEST_HEADER = bytes.fromhex("0a 00 08 05 fc")
RESPONSE_HEADER = bytes.fromhex("09 00 05 08 fc")


def _reviewed_helpers():
    """实际复用固定仓库的三个纯函数；不执行其导入、main 或 USB 入口。"""
    namespace = {"struct": struct, "SUTEST_PACKET_LEN": 252, "CMD_OS_SYSTEM": 52}
    for filename, names in (("x1d_usb_pull_file.py", ("sutest_crc16", "make_testd_frame")),
                            ("x1d_usb_exec.py", ("make_exec_request",))):
        path = REFERENCE / "tools/usb" / filename
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != UPSTREAM_SHA[filename]:
            raise ValueError("参考工具哈希发生变化")
        parsed = ast.parse(data.decode("utf-8"), filename=str(path))
        functions = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
        if tuple(node.name for node in functions) != names or any(node.decorator_list for node in functions):
            raise ValueError("参考工具函数集合不符合已审阅版本")
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["make_exec_request"], namespace["sutest_crc16"]


def _token(value):
    if type(value) is not int or not 1 <= value <= 0xffffffff:
        raise ValueError("需要本次非零 32 位关联标记")


def build_query(token):
    _token(token)
    make_request, crc16 = _reviewed_helpers()
    if len(COMMAND.encode("ascii")) != 199:
        raise ValueError("固定命令发生变化")
    packet = bytearray(make_request(COMMAND))
    if len(packet) != 257 or packet[:5] != REQUEST_HEADER:
        raise ValueError("参考工具封装不匹配")
    struct.pack_into("<I", packet, 5 + 8, token)
    # 原厂 CRC 覆盖内部 +0x10 起 236 字节；本请求前四字节为零，
    # 与上游以零初值计算 +0x14 起 232 字节的结果相同。
    if struct.unpack_from("<I", packet, 5 + 12)[0] != crc16(packet[5 + 16:257]):
        raise ValueError("请求原厂 CRC 不匹配")
    return bytes(packet) + bytes(PACKET_SIZE - len(packet))


@dataclass(frozen=True)
class RamCacheValue:
    cached_value: int
    cache_reports_ram_only: bool
    freshness_verified: bool = False
    current_demo_mode_confirmed: bool = False


def parse_reply(packet, token):
    _token(token)
    if type(packet) is not bytes or len(packet) != PACKET_SIZE or packet[:5] != RESPONSE_HEADER:
        raise ValueError("回复长度或路由不在白名单内")
    payload = packet[5:257]
    command, operation, echoed, checksum, result = struct.unpack_from("<5I", payload)
    if (command, operation, echoed) != (52, 0, token):
        raise ValueError("回复命令、种类或关联标记不匹配")
    _, crc16 = _reviewed_helpers()
    if checksum != crc16(payload[16:]):
        raise ValueError("回复 CRC 无效")
    if result != 0:
        raise ValueError("相机命令未成功")
    output = payload[20:]
    accepted = {b"v i 0\n" + bytes(226): 0, b"v i 1\n" + bytes(226): 1}
    if output not in accepted:
        raise ValueError("属性类型、值或输出尾部未通过白名单")
    value = accepted[output]
    return RamCacheValue(value, value == 1)


def is_late_farm_reply(packet):
    """只识别先前唯一一次超时查询的已审阅回复，不接受其他旧帧。"""
    return (type(packet) is bytes and len(packet) == PACKET_SIZE
            and packet[:4] == bytes.fromhex("2e 02 01 08") and packet[4] in (0, 1))
