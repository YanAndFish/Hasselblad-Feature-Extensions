"""仅离线核对历史基线、本地候选和素材；不导入设备客户端或运行安装器。"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import wave

D = Path(__file__).resolve().parent


def baseline_files():
    manifest = json.loads((D / 'baseline-400ms.sources.json').read_text(encoding='utf-8'))
    files = {}
    for entry in manifest['files']:
        name = entry['name']
        assert Path(name).name == name and name not in files
        raw = entry['text'].encode('utf-8') if entry['storage'] == 'snapshot' else (D / name).read_bytes()
        assert len(raw) == entry['bytes'], name
        assert hashlib.sha256(raw).hexdigest() == entry['sha256'], name
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
        files[name] = raw
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--materialize', action='store_true', help='重建到本模块 outputs，只供审阅，不执行其中脚本')
    args = parser.parse_args()
    files = baseline_files()
    for path in D.glob('*.py'):
        ast.parse(path.read_bytes(), filename=path.name)
    baseline = files['X2dShutterAnimation.qml'].decode()
    current = (D / 'X2dShutterAnimation.qml').read_text(encoding='utf-8')
    assert 'duration: 400' in baseline and 'duration: 800' in current
    assert 'effect_mode.h' not in files['audio_preview.c'].decode()
    assert 'effect_mode.h' in (D / 'audio_preview.c').read_text(encoding='utf-8')
    assert 'networkEnabled:false' in (D / 'check_device_animation.py').read_text(encoding='utf-8')
    audio = json.loads((D / 'audio-source.json').read_text(encoding='utf-8'))
    path = D / audio['path']
    assert path.resolve().is_relative_to((D / 'outputs').resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == audio['sha256']
    with wave.open(str(path), 'rb') as wav:
        assert (wav.getnframes(), wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (59392, 48000, 2, 2)
    dependencies = [
        D.parents[1] / 'tools/firmware_image.py',
        D.parent / 'temporary_af_speed_probe/Usb.ps1',
        D.parent / 'temporary_af_speed_probe/AdbUsbCheck.cs',
        D.parent / 'temporary_af_speed_probe/original-menu-candidate/Bootstrap.qml',
        D.parent / 'temporary_af_speed_probe/menu-candidate/flash-ui',
    ]
    for dependency in dependencies:
        assert dependency.exists(), str(dependency)
    if args.materialize:
        out = D / 'outputs/baseline-400ms-review'
        out.mkdir(parents=True, exist_ok=True)
        for name, raw in files.items():
            target = out / name
            if target.exists() and target.read_bytes() != raw:
                raise ValueError('审阅副本已有不同内容，停止覆盖：' + name)
            target.write_bytes(raw)
        (out / 'REVIEW-ONLY.txt').write_text(
            '这是历史源码审阅副本。脚本中的相对依赖属于原模块位置；不得从本目录执行设备暂存或安装。\n'
            '历史精确哈希保护不代表适用于当前相机。本轮没有连接相机。\n', encoding='utf-8')
    print('PASS: 18 baseline hashes, candidate retained, Python syntax, local dependencies, complete original WAV; no device access.')


if __name__ == '__main__':
    main()
