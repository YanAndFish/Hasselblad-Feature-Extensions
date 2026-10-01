"""无损保留主 JPEG，添加待实机验证的官方 4.2.0 FlashPix 预览流。"""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
from PIL import Image, JpegImagePlugin

MAGIC = b'FPXR\0\0'
DIRECTORY_ID = bytes.fromhex('9b5c69998f836c83774232382807013f')

def name(value):
    return value.encode('utf-16-be') + b'\0\0\0'

def directory(size):
    return (MAGIC + b'\x01\0\x02' + b'\xff'*4 + name('/HASSELBLAD') +
            DIRECTORY_ID + struct.pack('>I', size) + name('/HASSELBLAD/preview'))

def marker(data):
    if len(data) > 65533:
        raise ValueError('APP2 payload too long')
    return b'\xff\xe2' + struct.pack('>H', len(data)+2) + data

def segments(preview):
    if not preview.startswith(b'\xff\xd8') or not preview.endswith(b'\xff\xd9'):
        raise ValueError('Invalid preview JPEG')
    # 三份原厂样本的流长度均按 4096 对齐。仅补零，不复制样本尾部数据。
    preview += bytes((-len(preview)) % 4096)
    result = marker(directory(len(preview)))
    for offset in range(0, len(preview), 65407):
        result += marker(MAGIC + b'\x02\0\x01' + struct.pack('>I', offset) + preview[offset:offset+65407])
    return result

def app2_headers(jpeg):
    if jpeg[:2] != b'\xff\xd8':
        raise ValueError('Not JPEG')
    pos = 2
    while pos+4 <= len(jpeg):
        if jpeg[pos] != 255:
            raise ValueError('Invalid marker')
        kind = jpeg[pos+1]
        if kind in (0xda, 0xd9):
            return
        size = int.from_bytes(jpeg[pos+2:pos+4], 'big')
        if size < 2 or pos+size+2 > len(jpeg):
            raise ValueError('Truncated marker')
        if kind == 0xe2:
            yield jpeg[pos+4:pos+2+size]
        pos += size+2
    raise ValueError('Missing scan')

def preview_insertion_offset(jpeg):
    # 4.2.0 parseJpegExif 从 EXIF 后向前寻找 APP2；不能插到 EXIF 前。
    if jpeg[:2] != b'\xff\xd8':
        raise ValueError('Not JPEG')
    pos = 2
    found_exif = False
    while pos+4 <= len(jpeg):
        if jpeg[pos] != 255:
            raise ValueError('Invalid marker')
        kind = jpeg[pos+1]
        if not 0xe0 <= kind <= 0xef:
            break
        size = int.from_bytes(jpeg[pos+2:pos+4], 'big')
        if size < 2 or pos+size+2 > len(jpeg):
            raise ValueError('Truncated marker')
        if kind == 0xe1 and jpeg[pos+4:pos+10] == b'Exif\0\0':
            found_exif = True
        pos += size+2
    if not found_exif:
        raise ValueError('EXIF must precede FlashPix')
    return pos

def build(source, original_reference, output, preview_pixels=None):
    source, original_reference, output = map(Path, (source, original_reference, output))
    if output.exists():
        raise FileExistsError(output)
    raw = source.read_bytes()
    if any(s.startswith(MAGIC) for s in app2_headers(raw)):
        raise ValueError('Source already has FlashPix')
    # Reference is inspected only for format structure, never copied as image content.
    native_headers = list(app2_headers(original_reference.read_bytes()))
    native = next(s for s in native_headers if s.startswith(MAGIC+b'\x01'))
    if len(native) != 99 or native != directory(int.from_bytes(native[54:58], 'big')):
        raise ValueError('Native FlashPix directory differs from reviewed format')
    native_preview = b''.join(s[13:] for s in native_headers if s.startswith(MAGIC+b'\x02\0\x01'))
    with Image.open(io.BytesIO(native_preview)) as reference_preview:
        native_size = reference_preview.size
        native_sampling = JpegImagePlugin.get_sampling(reference_preview)
    if native_size != (3888, 2918) or native_sampling != 1:
        raise ValueError('Reference default preview differs from reviewed dimensions/sampling')
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(source) as image:
        full_size = image.size
        if full_size != (23326, 17498):
            raise ValueError('Only the validated 408MP image is supported')
        if preview_pixels is None:
            target = native_size
        else:
            if not 1000000 <= preview_pixels <= 25000000:
                raise ValueError('Requested preview budget must be between 1MP and 25MP')
            scale = min(math.sqrt(preview_pixels / (full_size[0]*full_size[1])),
                        8191/full_size[0], 8191/full_size[1])
            target = tuple(int(value*scale) for value in full_size)
        image.draft('RGB', target)
        preview_size = target
        stream = io.BytesIO()
        image.resize(target, Image.Resampling.LANCZOS).convert('RGB').save(
            stream, 'JPEG', quality=90, subsampling=native_sampling)
    preview = stream.getvalue()
    with Image.open(io.BytesIO(preview)) as image:
        image.load()
        assert image.size == preview_size
    extra = segments(preview)
    insertion = preview_insertion_offset(raw)
    result = raw[:insertion] + extra + raw[insertion:]
    # Verify every preview fragment reconstructs the generated image in order.
    chunks = [s for s in app2_headers(result) if s.startswith(MAGIC+b'\x02')]
    offset = 0
    for chunk in chunks:
        assert int.from_bytes(chunk[9:13], 'big') == offset
        offset += len(chunk)-13
    padded_preview = preview + bytes((-len(preview)) % 4096)
    assert b''.join(c[13:] for c in chunks) == padded_preview
    assert result[:insertion] + result[insertion+len(extra):] == raw
    temporary = output.with_name(output.name+'.partial')
    owned = False
    try:
        with temporary.open('xb') as f:
            owned = True
            f.write(result)
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, output)
    finally:
        if owned:
            temporary.unlink()
    report = dict(full_size=full_size, preview_size=preview_size, preview_bytes=len(preview),
                  preview_mode='native-default' if preview_pixels is None else 'custom',
                  preview_subsampling=native_sampling,
                  preview_quality=90, preview_stream_bytes=len(padded_preview),
                  source_sha256=hashlib.sha256(raw).hexdigest(), sha256=hashlib.sha256(result).hexdigest(),
                  original_jpeg_preserved_byte_for_byte=True, camera_preview_verified=False)
    output.with_suffix('.preview-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source'); parser.add_argument('reference'); parser.add_argument('output')
    parser.add_argument('--preview-pixels', type=int, default=None,
                        help='Optional custom budget; omitted uses verified native preview dimensions')
    args = parser.parse_args()
    build(args.source, args.reference, args.output, args.preview_pixels)
