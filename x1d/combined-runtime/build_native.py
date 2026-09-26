"""统一界面适配器和健康检查器的离线构建；不连接相机。"""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FLASH = ROOT / 'x1d/wireless-flash'
CACHE = ROOT / '.research-cache/x1d-1.25.0'
BASELINE = CACHE / 'baseline'
OUT = HERE / 'build/native'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('workspace mismatch')
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for key, name in [('ZIG_GLOBAL_CACHE_DIR', 'global-cache'), ('ZIG_LOCAL_CACHE_DIR', 'local-cache'),
                      ('TEMP', 'tmp'), ('TMP', 'tmp')]:
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        env[key] = str(folder)
    qt = CACHE / 'qt-public'
    base = qt / 'qtbase-opensource-src-5.5.1'
    include = OUT / 'include/QtCore'
    include.mkdir(parents=True, exist_ok=True)
    (include / 'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n', encoding='ascii')
    (include / 'qfeatures.h').write_text('/* Fixed Qt 5.5.1 public ABI. */\n', encoding='ascii')
    compiler = CACHE / 'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    commands = []

    def run(args):
        result = subprocess.run([str(compiler)] + args, env=env, capture_output=True, text=True, timeout=60)
        commands.append({'arguments': args, 'exit': result.returncode, 'stderr': result.stderr})
        if result.returncode:
            raise RuntimeError(result.stderr)

    target = ['-target', 'arm-linux-gnueabihf.2.22', '-mcpu=cortex_a9']
    flags = target + ['-marm', '-O2', '-fPIC', '-fno-stack-protector',
                     '-I', str(OUT / 'include'), '-I', str(FLASH / 'native'),
                     '-isystem', str(base / 'include'),
                     '-isystem', str(qt / 'qtdeclarative-opensource-src-5.5.1/include'),
                     '-I', str(base / 'mkspecs/linux-arm-gnueabi-g++'),
                     '-Wno-deprecated-declarations', '-Wno-enum-constexpr-conversion',
                     '-Wall', '-Wextra', '-Werror']
    layout = OUT / 'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n', encoding='ascii')
    libs = [BASELINE / ('usr/lib/libQt5' + name + '.so.5.5.1') for name in ('Qml', 'Core')]
    libs += [BASELINE / path for path in ('usr/lib/libstdc++.so.6.0.21', 'lib/libgcc_s.so.1',
                                        'lib/libdl-2.22.so', 'lib/libc-2.22.so', 'lib/libpthread-2.22.so')]
    entries = [
        (HERE / 'native/combined_runtime.cpp', 'libhbl-combined.so', True, False),
        (HERE / 'native/system_check.cpp', 'system-check', False, True),
        (FLASH / 'native/formal_runtime.cpp', 'legacy/libhbl-formal.so', True, False),
        (FLASH / 'native/formal_system_check.cpp', 'legacy/formal-system-check', False, True),
    ]
    outputs = []
    for source, name, shared, dbus in entries:
        output = OUT / name
        output.parent.mkdir(exist_ok=True)
        obj = output.with_name(output.name + '.o')
        run(['c++', '-std=c++11'] + flags + ['-c', str(source), '-o', str(obj)])
        extra = ['-Wl,-soname,' + output.name] if shared else ['-Wl,--export-dynamic']
        if dbus:
            extra.append(str(BASELINE / 'usr/lib/libQt5DBus.so.5.5.1'))
        run(['cc'] + target + ['-shared' if shared else '-no-pie', '-Wl,--no-undefined', '-Wl,-s',
                              '-Wl,-T,' + str(layout)] + extra + [str(obj)] + list(map(str, libs)) + ['-o', str(output)])
        outputs.append(output)

    sys.path.insert(0, str(CACHE / 'python'))
    from elftools.elf.elffile import ELFFile
    abi = {}
    for path in outputs:
        elf = ELFFile(io.BytesIO(path.read_bytes()))
        rel = elf.get_section_by_name('.rel.dyn')
        plt = elf.get_section_by_name('.rel.plt')
        if not rel or not plt or rel['sh_addr'] + rel['sh_size'] != plt['sh_addr']:
            raise RuntimeError('old loader relocation layout mismatch')
        if elf.elfclass != 32 or not elf.little_endian or elf['e_machine'] != 'EM_ARM':
            raise RuntimeError('ARM ABI mismatch')
        abi[str(path.relative_to(OUT))] = {
            'relocationsContiguous': True,
            'needed': [tag.needed for tag in elf.get_section_by_name('.dynamic').iter_tags() if tag.entry.d_tag == 'DT_NEEDED']}

    # 参数化只应改变新组合程序；默认引闪程序必须仍与本轮实装字节相同。
    legacy_expected = {
        'legacy/libhbl-formal.so': '6bd2742c005a41e436a6036edd7d99eb7af2827443ef4cff719688b822dbc569',
        'legacy/formal-system-check': '8a0225ea00b74c549575f8d7599ecf106135bacf081bad230fa00fc9b16ce6dc',
    }
    legacy_matches = {name: sha(OUT / name) == expected for name, expected in legacy_expected.items()}
    if not all(legacy_matches.values()):
        raise RuntimeError('默认引闪构建与已安装基线不一致：' + json.dumps(legacy_matches))
    sources = [Path(__file__)] + sorted((HERE / 'native').glob('*'))
    sources += [FLASH / 'native' / name for name in ('formal_runtime.cpp', 'formal_system_check.cpp',
                'formal_install_hold.h', 'formal_bridge.h', 'rf_local_socket.h')]
    report = {
        'kind': 'x1d-combined-native', 'sourceVersion': 'X1D 1.25.0', 'compiled': True,
        'outputs': {str(path.relative_to(OUT)).replace('\\', '/'): {'sha256': sha(path), 'bytes': path.stat().st_size} for path in outputs},
        'sources': {str(path.relative_to(ROOT)).replace('\\', '/'): sha(path) for path in sources},
        'abi': abi, 'legacyDefaultsByteIdentical': legacy_matches, 'commands': commands,
        'holdMaximumMs': 1200000, 'holdNamespace': '/tmp/hbl-x1d-combined/install-state',
        'hardwareRequests': 0, 'installed': False, 'targetSelfChecksRun': False,
    }
    (OUT / 'build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {key: report[key] for key in ('compiled', 'outputs', 'legacyDefaultsByteIdentical', 'hardwareRequests', 'installed')}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
