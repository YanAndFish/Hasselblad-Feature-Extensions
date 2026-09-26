"""固定系统MMC容量查询；只处理已核属性和根设备字段。"""
from decimal import Decimal
import re
import struct
from sutest_ram_contract import (_reviewed_helpers, _token, PACKET_SIZE, REQUEST_HEADER)
from sutest_error_log_contract import parse_envelope

COMMAND = "cd /sys/class/block/mmcblk3&&/bin/cat device/type removable size;/usr/bin/awk '{for(i=1;i<=NF;i++)if($i~/^root=/){n++;r=$i}}END{print n==1&&r~/^root=\\/dev\\/mmcblk3p[1-9][0-9]?$/?r:\"UNKNOWN\"}' /proc/cmdline"
MAX_OUTPUT_BYTES = 48
ROOT_LINE = re.compile(rb"root=/dev/mmcblk3p([1-9][0-9]?)")
SECTOR_LINE = re.compile(rb"[1-9][0-9]{0,19}")


def build_query(token):
    _token(token)
    if len(COMMAND.encode("ascii")) != 205:
        raise ValueError("固定容量命令发生变化")
    make_request, crc16 = _reviewed_helpers()
    packet = bytearray(make_request(COMMAND))
    if len(packet) != 257 or packet[:5] != REQUEST_HEADER:
        raise ValueError("固定工具封装变化")
    struct.pack_into("<I", packet, 13, token)
    if struct.unpack_from("<I", packet, 17)[0] != crc16(packet[21:257]):
        raise ValueError("请求 CRC 不匹配")
    return bytes(packet) + bytes(PACKET_SIZE - len(packet))


def parse_capacity(field):
    if type(field) is not bytes or len(field) != 232 or b"\0" not in field:
        raise ValueError("输出字段无完整终止")
    end = field.index(b"\0")
    if not 1 <= end <= MAX_OUTPUT_BYTES or any(field[end:]):
        raise ValueError("输出为空、过长或终止后还有内容")
    output = field[:end]
    if not output.endswith(b"\n"):
        raise ValueError("输出行未完整结束")
    lines = output[:-1].split(b"\n")
    if len(lines) != 4 or lines[:2] != [b"MMC", b"0"]:
        raise ValueError("设备类型、标志或字段数不符合固定目标")
    if not SECTOR_LINE.fullmatch(lines[2]) or not ROOT_LINE.fullmatch(lines[3]):
        raise ValueError("扇区或根设备未知；不枚举或改用其他设备")
    sectors = int(lines[2])
    if sectors > 0xffffffffffffffff:
        raise ValueError("扇区数超出uint64")
    count = sectors * 512
    return dict(device="/dev/mmcblk3", deviceType="MMC", removableFlag=0,
                rootPartition=lines[3][5:].decode("ascii"),
                sectors512=sectors, sectorUnitBytes=512, capacityBytes=count,
                decimalGB=format(Decimal(count) / Decimal(1000000000), ".6f"),
                binaryGiB=format(Decimal(count) / Decimal(1073741824), ".6f"),
                rootParameterOnMeasuredDisk=True, boardMappingBasis="官方1.25 Wedge USDHC4/eMMC既有静态证据",
                removableFlagAloneProvesPhysicalMounting=False, mainUserAreaOnly=True,
                freeSpaceMeasured=False, otherControllerStorageMeasured=False,
                rawBlockContentsRead=False, serialOrCidRead=False)

