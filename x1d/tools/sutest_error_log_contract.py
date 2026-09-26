"""唯一已审阅的错误日志快照查询；不访问硬件，不接受任意命令。"""
from dataclasses import dataclass
import re
import struct

from sutest_ram_contract import (_reviewed_helpers, _token, PACKET_SIZE, REQUEST_HEADER, RESPONSE_HEADER)

COMMAND = ("/bin/journalctl -b -n 200 --no-pager -o cat _COMM=system-manager|"
           "/bin/grep -oE 'onErrorReportReceived [0-9 ]+|"
           "SUC: (true|false) FARM: (true|false) SPC: (true|false)'|/usr/bin/tail -n 3")
MAX_OUTPUT_BYTES = 192
ERROR_LINE = re.compile(rb"onErrorReportReceived ([0-9]{1,10}) ([0-9]{1,10}) ([0-9]{1,10}) *")
LINK_LINE = re.compile(rb"SUC: (true|false) FARM: (true|false) SPC: (true|false)")


def build_query(token):
    _token(token)
    if len(COMMAND.encode("ascii")) != 184:
        raise ValueError("固定日志命令发生变化")
    make_request, crc16 = _reviewed_helpers()
    packet = bytearray(make_request(COMMAND))
    if len(packet) != 257 or packet[:5] != REQUEST_HEADER:
        raise ValueError("固定工具封装变化")
    struct.pack_into("<I", packet, 13, token)
    if struct.unpack_from("<I", packet, 17)[0] != crc16(packet[21:257]):
        raise ValueError("请求 CRC 不匹配")
    return bytes(packet) + bytes(PACKET_SIZE - len(packet))


@dataclass(frozen=True)
class Envelope:
    result: int
    output_field: bytes


def parse_envelope(packet, token):
    _token(token)
    if type(packet) is not bytes or len(packet) != PACKET_SIZE or packet[:5] != RESPONSE_HEADER:
        raise ValueError("回复长度或路由无效")
    payload = packet[5:257]
    command, operation, echoed, checksum, result = struct.unpack_from("<5I", payload)
    if (command, operation, echoed) != (52, 0, token):
        raise ValueError("回复命令或关联标记不匹配")
    _, crc16 = _reviewed_helpers()
    if checksum != crc16(payload[16:]) or result not in (0, 1):
        raise ValueError("回复 CRC 或执行状态无效")
    return Envelope(result, payload[20:])


def parse_records(field):
    if type(field) is not bytes or len(field) != 232 or b"\0" not in field:
        raise ValueError("输出字段无完整终止")
    end = field.index(b"\0")
    if not 1 <= end <= MAX_OUTPUT_BYTES or any(field[end:]):
        raise ValueError("输出为空、过长或终止后还有内容")
    output = field[:end]
    if not output.endswith(b"\n"):
        raise ValueError("输出行未完整结束")
    lines = output[:-1].split(b"\n")
    if not 1 <= len(lines) <= 3:
        raise ValueError("输出行数不在白名单内")
    records = []
    for line in lines:
        if match := ERROR_LINE.fullmatch(line):
            values = [int(x) for x in match.groups()]
            if any(x > 0x7fffffff for x in values):
                raise ValueError("错误字段超出原厂有符号整数范围")
            records.append(dict(kind="error-report", code=values[0], category=values[1], severity=values[2]))
        elif match := LINK_LINE.fullmatch(line):
            values = [x == b"true" for x in match.groups()]
            records.append(dict(kind="link-history", suc=values[0], farm=values[1], spc=values[2]))
        else:
            raise ValueError("输出含未审阅字段")
    return records
