"""在已交付全尺寸 Q85 基线上构建 Q95 候选，不执行安装。"""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
ROOT = P.parents[3]
sys.path.insert(0, str(ROOT / 'x1d/tools'))
from binary import ArmElf


def build():
    previous = P / 'build/full-jpeg-output/stage/files'
    source = (previous / 'jpeg-daemon-full').read_bytes()
    assert hashlib.sha256(source).hexdigest() == 'c31035127b111936acdd76949ac64625a41144f5aa7880c4e4394ca4c4ed7e80'
    elf = ArmElf(source)
    assert elf.word(0x22490) == 0xe3a07055
    candidate = bytearray(source)
    struct.pack_into('<I', candidate, elf.offset(0x22490, 4), 0xe3a0705f)
    out = P / 'build/jpeg-quality95'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'jpeg-daemon-full').write_bytes(candidate)
    metadata = dict(quality=95, previousQuality=85, fullResolutionPreserved=True,
                    rawPlaybackUnchanged=True, installed=False, actualEncodingMeasured=False,
                    sha256=hashlib.sha256(candidate).hexdigest(), bytes=len(candidate))
    (out / 'candidate.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return bytes(candidate), metadata


if __name__ == '__main__':
    print(json.dumps(build()[1]))
