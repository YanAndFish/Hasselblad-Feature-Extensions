"""构建输入契约及原子报告；仅处理调用者指定的本地文件。"""
import hashlib
import json
import os
from pathlib import Path
import tempfile

PREPARED_SHA256 = '654f13688c17e017497184b1a6873347c6b8cd7b01abdab5327bc8035d08f688'
# 生成器支持的唯一版本；统一换行后比较，兼容 Windows 和 Unix。
TABLE_SHA256 = {
    'formal_flash_hashes.h': '345915679143ce849ce0c8a1ed1d5e2a804be52af83db7bb7ef50dfebf5e0dd0',
    'formal_flash_lut.h': 'ccbf7bbce065139681e74d0a607966dde6ffd066ead7131b301bf525ae8fed46',
}

def atomic_write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def write_report(path, report):
    atomic_write(path, (json.dumps(report, indent=2)+'\n').encode('utf-8'))

def validate_radio_tables(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'radio-tables.json').read_text(encoding='utf-8'))
    if (manifest.get('passed') is not True or manifest.get('inputSha256') != PREPARED_SHA256
            or manifest.get('waveCount') != 1345 or set(manifest.get('files', {})) != set(TABLE_SHA256)):
        raise ValueError('Unsupported or incomplete radio table manifest; regenerate with the supported input')
    for name, expected in TABLE_SHA256.items():
        data = (folder/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['files'][name]:
            raise ValueError('Radio table integrity mismatch: '+name)
        if hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError('Radio table does not match the supported baseline: '+name)
    return manifest
