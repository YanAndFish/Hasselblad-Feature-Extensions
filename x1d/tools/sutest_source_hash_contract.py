"""唯一获核对的声明版本与三份控制器源文件摘要查询；不访问硬件。"""
import re
import struct
from sutest_ram_contract import (_reviewed_helpers, _token, PACKET_SIZE, REQUEST_HEADER)
from sutest_error_log_contract import parse_envelope

COMMAND = "/bin/grep -E '^VERSION=\"v[0-9.]{3,11}\"$' /etc/os-release;cd /lib/firmware/hbl&&/usr/bin/sha256sum farm/bootimage_even-wedge.bin farm/bootimage_odd-wedge.bin power-control/power-control.bin|/bin/grep -oE '^[0-9a-f]{64}'"
MAX_OUTPUT_BYTES = 219
VERSION_LINE = re.compile(rb'VERSION="(v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})"')
DIGEST_LINE = re.compile(rb"[0-9a-f]{64}")
BASELINE_VERSION = "v1.25.0"
SOURCES = (
    ("FARM even", "/lib/firmware/hbl/farm/bootimage_even-wedge.bin", 3954444,
     "e0575442e0831f0ba6cd65a5beedfc64bff2c992182220b7832a27e49928cac0"),
    ("FARM odd", "/lib/firmware/hbl/farm/bootimage_odd-wedge.bin", 3954444,
     "2c1ff341653f6548c04c0cfb10db7e864887135f259e278066de49ae1c7967be"),
    ("SPC", "/lib/firmware/hbl/power-control/power-control.bin", 48455,
     "dc0a77dd46f7e07a5640fb9407e077b8f544871d007f9c3fa4233ea5fc8e7616"),
)


def build_query(token):
    _token(token)
    if len(COMMAND.encode("ascii")) != 218:
        raise ValueError("固定摘要命令发生变化")
    make_request, crc16 = _reviewed_helpers()
    packet = bytearray(make_request(COMMAND))
    if len(packet) != 257 or packet[:5] != REQUEST_HEADER:
        raise ValueError("固定工具封装变化")
    struct.pack_into("<I", packet, 13, token)
    if struct.unpack_from("<I", packet, 17)[0] != crc16(packet[21:257]):
        raise ValueError("请求 CRC 不匹配")
    return bytes(packet) + bytes(PACKET_SIZE - len(packet))


def parse_sources(field):
    if type(field) is not bytes or len(field) != 232 or b"\0" not in field:
        raise ValueError("输出字段无完整终止")
    end = field.index(b"\0")
    if not 1 <= end <= MAX_OUTPUT_BYTES or any(field[end:]):
        raise ValueError("输出为空、过长或终止后还有内容")
    output = field[:end]
    if not output.endswith(b"\n"):
        raise ValueError("输出行未完整结束")
    lines = output[:-1].split(b"\n")
    if len(lines) != 4 or not (version_match := VERSION_LINE.fullmatch(lines[0])):
        raise ValueError("声明版本与三摘要必须完整且顺序固定")
    if any(not DIGEST_LINE.fullmatch(line) for line in lines[1:]):
        raise ValueError("摘要不完整或包含非白名单字符")
    declared = version_match[1].decode("ascii")
    same_version = declared == BASELINE_VERSION
    files = []
    for (role, path, size, expected), line in zip(SOURCES, lines[1:]):
        observed = line.decode("ascii")
        match = observed == expected if same_version else None
        files.append(dict(role=role, path=path, sha256=observed,
                          referenceVersion=BASELINE_VERSION, referenceBytes=size,
                          referenceSha256=expected, digestMatchesReference=match,
                          independentlyMeasuredBytes=None,
                          byteLengthInferredFromMatchingDigest=size if match else None,
                          comparison="same-version-match" if match else
                          ("same-version-digest-mismatch" if same_version else "not-compared-different-version")))
    return dict(declaredRootfsVersion=declared, files=files,
                sameVersionReferenceAvailable=same_version,
                allThreeSourcesMatch=all(x["digestMatchesReference"] is True for x in files),
                allRetryInputsChecked=False, targetControllerFlashChecked=False,
                wholeSystemIntegrityChecked=False)

