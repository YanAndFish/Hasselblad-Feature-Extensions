#!/usr/bin/env python3
"""离线解析 EF-HX V1.04 的 Canon EF 50mm F1.8 STM 配置。

只读取用户指定的固件文件，不访问相机或转接环。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


EXPECTED_SHA256 = "f6f5c8dc416cebe2a40a3e975862b57e43b2069f4f270f0113eb25c2a93a13fe"
HEADER = b"PRODUCTVER:1.001"
IMAGE_BASE = 0x10000
HEADER_SIZE = 16
TABLE_ADDRESS = 0x17B26
RECORD_SIZE = 18
RECORD_COUNT = 52
TARGET_ID = 4156


def profile_scale(value: int) -> int:
    """逐条复现固件 0x1329c 的有效输入分支。"""
    scale = 100
    if value < 9 or value > 10000:
        return scale
    while value > 2550:
        value //= 2
        scale = (scale * 2) & 0xFFFF
    return (scale * 2) & 0xFFFF


def reported_word(value: int, scale: int) -> int:
    """复现 0x104f8-0x10514 / 0x12196-0x121b2。"""
    return (((value + 5) // 10) * 2 * 100) // scale


def parse(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"固件 SHA-256 不匹配：{digest}")
    if raw[:HEADER_SIZE] != HEADER:
        raise ValueError(f"固件头不匹配：{raw[:HEADER_SIZE]!r}")

    payload = raw[HEADER_SIZE:]
    table_offset = TABLE_ADDRESS - IMAGE_BASE
    rows = [
        struct.unpack_from("<9H", payload, table_offset + i * RECORD_SIZE)
        for i in range(RECORD_COUNT)
    ]
    matches = [
        (index, row)
        for index, row in enumerate(rows)
        if row[0] == TARGET_ID and row[1] == 50 and row[2] == 50
    ]
    if len(matches) != 1:
        raise ValueError(f"目标镜头记录数量异常：{len(matches)}")

    index, row = matches[0]
    lens_id, focal_min, focal_max, near_limit, focus_span, speed_source, variant, flags, extra = row
    scale = profile_scale(speed_source)
    wire_word = reported_word(speed_source, scale)
    normalized_span = focus_span * 100 // scale

    return {
        "firmware": str(path),
        "sha256": digest,
        "table": {
            "address": hex(TABLE_ADDRESS),
            "record_count": RECORD_COUNT,
            "record_size": RECORD_SIZE,
        },
        "profile": {
            "index": index,
            "address": hex(TABLE_ADDRESS + index * RECORD_SIZE),
            "raw_u16": list(row),
            "lens_id": lens_id,
            "focal_min_mm": focal_min,
            "focal_max_mm": focal_max,
            "near_limit_code": near_limit,
            "focus_span_raw": focus_span,
            "speed_source_raw": speed_source,
            "variant": variant,
            "flags": flags,
            "extra": extra,
        },
        "derived": {
            "scale": scale,
            "normalized_focus_span": normalized_span,
            "wire_speed_word_decimal": wire_word,
            "wire_speed_word_hex": f"0x{wire_word:04x}",
            "wire_speed_fields_hex": f"{wire_word:04x} {wire_word:04x}",
            "x1d_internal_reported_start_speed": wire_word * 100,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware", type=Path)
    args = parser.parse_args()
    print(json.dumps(parse(args.firmware), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
