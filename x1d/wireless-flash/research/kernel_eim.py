"""固定 X1D 1.25.0 原厂 Linux 内核的离线 EIM 检查；不含设备访问。

输入仅接受已经核对哈希的 zImage。ARM 仿真只执行其中独立的 LZO
解压函数，全部地址均为主机内存中的模拟映射，不启动内核。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path


ZIMAGE_SHA256 = "2ed302a02c37c40fbf43fe4074f8069c1be0e4f6cf53fb556ad4daf0ba4c1a0a"
KERNEL_SHA256 = "4fefe290be2c10fc2ac2215e8f9d991ffe9e553c5a7df4541c63a4a6ca8be34f"
KERNEL_BASE = 0x80008000
SYMBOL_COUNT = 44884
SYMBOL_ADDRESSES = 0x4FAE10
SYMBOL_NAMES = 0x526B70


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def decompress(zimage: bytes) -> bytes:
    require(hashlib.sha256(zimage).hexdigest() == ZIMAGE_SHA256,
            "仅接受已核对的 X1D 1.25.0 原厂 zImage")
    import unicorn as u
    import unicorn.arm_const as a

    # 与此固定文件的 lzop 头以及 Linux 3.14 unlzo 解析布局交叉核对。
    start = 15452
    require(zimage[start:start + 9] == b"\x89LZO\x00\r\n\x1a\n", "lzop 头不符")
    p = start + 9
    version = int.from_bytes(zimage[p:p + 2], "big")
    p += 7
    if version >= 0x940:
        p += 1
    flags = int.from_bytes(zimage[p:p + 4], "big")
    require(flags == 0x0300000D, "校验与压缩标志不符")
    p += 8 if flags & 0x800 else 4
    p += 8
    if version >= 0x940:
        p += 4
    name_length = zimage[p]
    p += 1 + name_length + 4

    uc = u.Uc(u.UC_ARCH_ARM, u.UC_MODE_ARM)
    uc.mem_map(0x1000000, 0x10000)
    uc.mem_write(0x1000000, zimage[:0x3A50])
    for base in (0x2000000, 0x3000000, 0x4000000):
        uc.mem_map(base, 0x100000)
    blocks = []
    while True:
        require(p + 4 <= len(zimage), "缺少压缩块长度")
        size = int.from_bytes(zimage[p:p + 4], "big")
        p += 4
        if size == 0:
            break
        require(p + 8 <= len(zimage), "压缩块头截断")
        compressed, checksum = struct.unpack_from(">II", zimage, p)
        p += 8
        require(0 < compressed <= size <= 0x40000 and p + compressed <= len(zimage),
                "压缩块边界错误")
        block = zimage[p:p + compressed]
        p += compressed
        if compressed != size:
            uc.mem_write(0x2000000, block)
            uc.mem_write(0x4000000, struct.pack("<I", size))
            values = (
                (a.UC_ARM_REG_R0, 0x2000000), (a.UC_ARM_REG_R1, compressed),
                (a.UC_ARM_REG_R2, 0x3000000), (a.UC_ARM_REG_R3, 0x4000000),
                (a.UC_ARM_REG_SP, 0x40F0000), (a.UC_ARM_REG_LR, 0x1008000),
            )
            for register, value in values:
                uc.reg_write(register, value)
            uc.emu_start(0x1000B6C, 0x1008000, timeout=5000000, count=20000000)
            require(uc.reg_read(a.UC_ARM_REG_PC) == 0x1008000
                    and uc.reg_read(a.UC_ARM_REG_R0) == 0,
                    "模拟解压没有正常返回")
            require(struct.unpack("<I", uc.mem_read(0x4000000, 4))[0] == size,
                    "模拟解压长度不符")
            block = bytes(uc.mem_read(0x3000000, size))
        require(zlib.adler32(block) == checksum, "压缩块 Adler-32 不符")
        blocks.append(block)
        require(len(blocks) <= 28, "压缩块数量超出固定输入")
    kernel = b"".join(blocks)
    require(len(blocks) == 28 and len(kernel) == 7235068 and p == 3770130,
            "内核解包布局不符")
    require(hashlib.sha256(kernel).hexdigest() == KERNEL_SHA256, "内核哈希不符")
    return kernel


def symbols(kernel: bytes) -> list[tuple[int, str]]:
    require(hashlib.sha256(kernel).hexdigest() == KERNEL_SHA256, "内核哈希不符")
    require(struct.unpack_from("<I", kernel, SYMBOL_ADDRESSES + 4 * SYMBOL_COUNT)[0]
            == SYMBOL_COUNT, "符号数不符")
    p = SYMBOL_NAMES
    names, markers = [], []
    for i in range(SYMBOL_COUNT):
        if i % 256 == 0:
            markers.append(p - SYMBOL_NAMES)
        length = kernel[p]
        names.append(kernel[p + 1:p + 1 + length])
        p += length + 1
    marker_bytes = struct.pack("<" + "I" * len(markers), *markers)
    marker_start = kernel.find(marker_bytes, p, p + 64 + len(marker_bytes))
    require(marker_start == 0x5AACD0, "符号分组索引不符")
    token_start, token_index = 0x5AAF90, 0x5AB340
    q = token_start
    tokens, offsets = [], []
    for _ in range(256):
        offsets.append(q - token_start)
        end = kernel.index(b"\0", q)
        tokens.append(kernel[q:end])
        q = end + 1
    require(kernel[token_index:token_index + 512]
            == struct.pack("<256H", *offsets), "符号 token 索引不符")
    addresses = struct.unpack_from("<" + "I" * SYMBOL_COUNT, kernel, SYMBOL_ADDRESSES)
    require(all(a <= b for a, b in zip(addresses, addresses[1:])), "符号地址未排序")
    decoded = [b"".join(tokens[b] for b in name).decode("ascii") for name in names]
    return list(zip(addresses, decoded))


def analyze(zimage: bytes) -> dict:
    kernel = decompress(zimage)
    table = symbols(kernel)
    guards = {
        0x8023EE80: "0c00e0e300a89de8",  # read 固定返回 -13
        0x8023F53C: "013504e3083044e3",  # ioctl 唯一命令 0x40084501
        0x8023EF74: "010050e3416fa013",  # poll 检查 DMA 状态
        0x8023FA60: "011aa0e30203a0e3",  # 映射 0x08000000 起的 4096 字节
    }
    for address, expected in guards.items():
        offset = address - KERNEL_BASE
        require(kernel[offset:offset + 8].hex() == expected, "EIM 指令守卫不符")
    return {
        "source": "X1D 1.25.0 official Linux 3.14.28-1.0.0_ga+yocto+gf7d0ab5",
        "zimageSha256": ZIMAGE_SHA256, "kernelSha256": KERNEL_SHA256,
        "decompressedBytes": len(kernel), "verifiedAdlerBlocks": 28,
        "verifiedSymbols": len(table), "hardwareRequests": 0,
        "eimSymbols": [{"address": hex(address), "type": name[:1], "name": name[1:]}
                       for address, name in table if "eim" in name.lower()],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zimage", type=Path, help="已经从官方包取出的固定 zImage 文件")
    args = parser.parse_args()
    print(json.dumps(analyze(args.zimage.read_bytes()), ensure_ascii=False, indent=2))
