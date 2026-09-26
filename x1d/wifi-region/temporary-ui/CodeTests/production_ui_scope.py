"""只读复核无实验联网的发行范围；只写 build/production-ui-scope。

运行：py -3.14 -B x1d/wifi-region/temporary-ui/CodeTests/production_ui_scope.py
不导入发行主入口，不读签名私钥，不连接设备，不执行 ARM、网络或相机程序。
实际 collect 函数在内存文件系统执行；资源封装只记录调用，不生成签名包。
预处理使用现有 Zig / Qt5.5.1 头文件，shell 仅执行 -n 语法检查。
"""
from pathlib import Path
import ast
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import types
import zlib

sys.dont_write_bytecode = True
UI = Path(__file__).resolve().parents[1]
ROOT = UI.parents[2]
DIST = ROOT / 'x1d/patch-distribution'
BASE = DIST / 'build/candidate-r40/stage/files'
OUT = UI / 'build/production-ui-scope'
CACHE = ROOT / '.research-cache/x1d-1.25.0'
CHECKS = []
INPUTS = {}
EXCLUDED = ['Main.qml', 'Entry.qml', 'network.sh', 'dhcp.sh',
            'hotspot-ui', 'network-native', 'dhcp-native']
MARKERS = ['hblprotected/network/', 'temporaryHotspotEntry',
           'panel-created-waiting-wifi-page', 'network.sh', 'dhcp.sh',
           'network-native', 'dhcp-native', '/ctrl/wlp1s0', 'SCAN_RESULTS',
           'ADD_NETWORK', '临时联网测试', '正在连接热点']
CORES = {'_hblFocusCore': 'NativeFocusCore', '_hblTouchCore': 'NativeTouchCore',
         '_hblFlashCore': 'NativeFlashLogic', '_hblPagePoolCore': 'NativePagePoolCore',
         '_hblSettingsRulesCore': 'NativeSettingsRules'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    path = Path(path).resolve()
    path.relative_to(ROOT)
    assert '.app-data' not in path.parts
    data = path.read_bytes()
    INPUTS[path.relative_to(ROOT).as_posix()] = sha(data)
    return data


def source(path):
    return read(path).decode('utf-8-sig').replace('\r\n', '\n')


def check(name, passed, detail=None):
    row = {'name': name, 'passed': bool(passed)}
    if detail is not None:
        row['detail'] = detail
    CHECKS.append(row)
    return bool(passed)


def functions(path, names, namespace):
    tree = ast.parse(source(path))
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in selected} == set(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def cpp_body(text, start):
    begin = text.index('{', start)
    depth, quote, escaped = 1, None, False
    for i in range(begin + 1, len(text)):
        c = text[i]
        if quote:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == quote:
                quote = None
        elif c in ('"', "'"):
            quote = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[begin:i + 1]
    raise ValueError('Unterminated preprocessed function')


def preprocess(sealed):
    qt = CACHE / 'qt-public'
    base = qt / 'qtbase-opensource-src-5.5.1'
    env = dict(os.environ)
    for key, name in [('ZIG_GLOBAL_CACHE_DIR', 'global'), ('ZIG_LOCAL_CACHE_DIR', 'local'),
                      ('TEMP', 'tmp'), ('TMP', 'tmp')]:
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        env[key] = str(folder)
    cmd = [str(CACHE / 'toolchain/zig-windows-x86_64-0.13.0/zig.exe'), 'c++',
           '-E', '-P', '-std=c++11', '-target', 'arm-linux-gnueabihf.2.22',
           '-mcpu=cortex_a9', '-marm', '-O2', '-fPIC', '-fno-stack-protector',
           '-I', str(base / 'src/3rdparty/angle/include'),
           '-I', str(UI / 'build/include'), '-isystem', str(base / 'include'),
           '-isystem', str(qt / 'qtdeclarative-opensource-src-5.5.1/include'),
           '-I', str(base / 'mkspecs/linux-arm-gnueabi-g++'),
           '-Wno-deprecated-declarations', '-Wno-enum-constexpr-conversion']
    if sealed:
        cmd.append('-DHBL_SEALED_UI=1')
    cmd.append(str(UI / 'entry.cpp'))
    process = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, timeout=60)
    assert process.returncode == 0, process.stderr.decode('utf-8', errors='replace')[-3000:]
    text = process.stdout.decode('utf-8')
    guard = cpp_body(text, text.index('static bool componentAuthorized()'))
    names = re.findall(r'"([^"\n]+)"', re.search(r'const char \*names\[\]=\{(.*?)\};', guard, re.S)[1])
    load = cpp_body(text, text.rindex('extern "C" void load('))
    register = cpp_body(text, text.index('extern "C" bool previewResource(const QString &file'))
    tag = 'sealed' if sealed else 'plain'
    check('preprocessor-' + tag + '-only-radio-runtime-check', names == ['radio-mode.sh'], names)
    check('preprocessor-' + tag + '-network-absent',
          not any(marker in text for marker in MARKERS) and 'class Embedded:public QObject' not in text)
    for context, cls in CORES.items():
        call = 'new ' + cls + '(e)'
        check('preprocessor-' + tag + '-load-' + context,
              context in load and call in load and load.index(call) < load.index('next(e,u)'))
    check('preprocessor-' + tag + '-resource-registration',
          'registerSealedResource' in register if sealed else 'return next(dir+' in register)
    evidence = {'sealedQml': sealed, 'experimentalNetworkDefined': False,
                'runtimeRequired': ['flash-ui.rcc'] + names, 'componentAuthorized': guard,
                'load': load, 'previewResource': register,
                'preprocessedSha256': sha(process.stdout), 'compilerExecutedArmCode': False}
    (OUT / ('preprocessor-' + tag + '.json')).write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return evidence


class MemoryPath:
    """执行 collect 的受限 Path 适配器；写操作仅允许在本报告的内存树内。"""
    def __init__(self, path, fs):
        self.path, self.fs = Path(path), fs

    def __truediv__(self, part):
        return MemoryPath(self.path / part, self.fs)

    def __str__(self):
        return str(self.path)

    def read_bytes(self):
        key = self.path.resolve()
        if key in self.fs:
            return self.fs[key]
        return read(key)

    def read_text(self, encoding='utf-8'):
        return self.read_bytes().decode(encoding).replace('\r\n', '\n')

    def write_bytes(self, data):
        key = self.path.resolve()
        key.relative_to(OUT)
        self.fs[key] = bytes(data)
        return len(data)

    def write_text(self, data, encoding='utf-8', newline=None):
        return self.write_bytes(data.encode(encoding))

    def unlink(self, missing_ok=False):
        key = self.path.resolve()
        key.relative_to(OUT)
        if key not in self.fs and not missing_ok:
            raise FileNotFoundError(key)
        self.fs.pop(key, None)


def collect_simulation(extra_legacy=False):
    """实际执行当前内层 collect AST；封装与签名不运行，收集文件仅驻内存。"""
    from elftools.elf.elffile import ELFFile
    fs, sealed_calls, shell_checks = {}, [], []
    label = 'legacy-input' if extra_legacy else 'current-input'
    output = OUT / ('collect-' + label)

    class ElfReader:
        def __init__(self, data):
            self.data, self.elf = data, ELFFile(io.BytesIO(data))
            assert self.elf.elfclass == 32 and self.elf.little_endian and self.elf['e_machine'] == 'EM_ARM'

        def offset(self, address, size=1):
            for section in self.elf.iter_sections():
                if section['sh_type'] != 'SHT_NOBITS' and section['sh_addr'] <= address and address + size <= section['sh_addr'] + section['sh_size']:
                    return section['sh_offset'] + address - section['sh_addr']
            raise ValueError('ELF address outside mapped file')

        def word(self, address):
            return struct.unpack_from('<I', self.data, self.offset(address, 4))[0]

    def copytree(src, dst):
        assert src.path.resolve() == BASE.resolve()
        assert not any(p.is_dir() for p in BASE.iterdir())
        for path in sorted(BASE.iterdir()):
            # Removed by collect immediately; no need to read device authorization data.
            data = b'not-inspected-removed-input' if path.name == 'authorization.bin' else read(path)
            (dst / path.name).write_bytes(data)
        if extra_legacy:
            for name in EXCLUDED[:4]:
                (dst / ('hotspot-' + name)).write_bytes(b'legacy-experimental-test-input')

    def copyfile(src, dst):
        dst.write_bytes(src.read_bytes())

    def package_resource(src, dst):
        check('collect-' + label + '-seal-input', src.read_bytes() == dst.read_bytes())
        sealed_calls.append({'source': str(src.path.relative_to(ROOT)),
                             'destination': str(dst.path.relative_to(OUT)),
                             'plaintextSha256': sha(src.read_bytes())})

    def shell_run(args, check):
        assert args[:2] == ['C:/Program Files/Git/bin/sh.exe', '-n']
        key = Path(args[2]).resolve()
        key.relative_to(OUT)
        data = fs[key]
        actual = OUT / ('collect-' + label + '-gui.sh')
        actual.write_bytes(data)
        result = subprocess.run([args[0], '-n', str(actual)], capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
        shell_checks.append({'mode': 'parse-only', 'exitCode': result.returncode})
        return result

    path = DIST / 'build_confirmed_ui.py'
    tree = ast.parse(source(path))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    inner = next(n for n in main.body if isinstance(n, ast.FunctionDef) and n.name == 'collect')
    ns = {'out': MemoryPath(output, fs), 'P': MemoryPath(DIST, fs), 'UI': MemoryPath(UI, fs),
          'shutil': types.SimpleNamespace(copytree=copytree, copyfile=copyfile),
          'subprocess': types.SimpleNamespace(run=shell_run), 'sealed_qml': True,
          'sys': sys, 'struct': struct, 'ArmElf': ElfReader}
    functions(path, ['restore_jpeg_quality'], ns)
    exec(compile(ast.Module(body=[inner], type_ignores=[]), str(path), 'exec'), ns)
    old_module = sys.modules.get('seal_resources')
    old_path = list(sys.path)
    sys.modules['seal_resources'] = types.SimpleNamespace(package_resource=package_resource)
    try:
        ns['collect']()
    finally:
        sys.path[:] = old_path
        if old_module is None:
            del sys.modules['seal_resources']
        else:
            sys.modules['seal_resources'] = old_module
    files = {key.name: data for key, data in fs.items()}
    leaked = [name for name in files if name in EXCLUDED or name.removeprefix('hotspot-') in EXCLUDED]
    check('collect-' + label + '-experimental-files-absent', not leaked, leaked)
    check('collect-' + label + '-sealing-call-retained', len(sealed_calls) == 1)
    check('collect-' + label + '-old-signature-removed',
          'manifest.sha256' not in files and 'authorization.bin' not in files)
    check('collect-' + label + '-radio-and-entry-copied', all(
        files['hotspot-' + name] == read(UI / 'build' / name)
        for name in ['radio-mode.sh', 'libhotspot-entry.so']))
    gui = files['gui.sh'].decode('utf-8')
    check('collect-' + label + '-gui-preparation-scope',
          'for name in libhotspot-entry.so radio-mode.sh; do' in gui and
          'cp "$p/af-ui.rcc" "$h/flash-ui.rcc"' in gui and
          'LD_PRELOAD="$h/libhotspot-entry.so:$p/libhbl-af-ui.so"' in gui and
          not any(marker in gui for marker in MARKERS))
    check('collect-' + label + '-gui-verification-order',
          gui.index('if ! verify;') < gui.index('h=/run/hbl-hotspot-ui') < gui.index('exec env HBL_FORMAL_ENABLE_PLUGIN=1'))
    preserved = ['radio-mode.sh', 'radio.bin', 'prepare-radio.sh',
                 'configstore-full', 'libhbl-af-loader.so', 'libhbl-af-ui.so', 'libhbl-viewfinder-body.so']
    check('collect-' + label + '-formal-backends-preserved', all(
        files[name] == read(BASE / name) for name in preserved), preserved)
    check('collect-' + label + '-runtime-required-files-available',
          'af-ui.rcc' in files and 'hotspot-radio-mode.sh' in files)
    return {'kind': 'actual-collect-with-memory-filesystem', 'legacyFilesInjected': extra_legacy,
            'signed': False, 'resourceActuallySealed': False, 'productionPackageCreated': False,
            'files': {name: sha(data) for name, data in sorted(files.items())},
            'sealingCalls': sealed_calls, 'shellChecks': shell_checks}


def main():
    assert Path.cwd().resolve() == ROOT
    OUT.mkdir(parents=True, exist_ok=True)
    read(Path(__file__))
    sys.path.insert(0, str(CACHE / 'python'))
    from elftools.elf.elffile import ELFFile
    features = json.loads(source(UI / 'build/ui-features.json'))
    native = json.loads(source(UI / 'build/build.json'))
    check('feature-gates-no-experimental-network', features.get('experimentalNetwork') is False and native.get('experimentalNetwork') is False)
    check('feature-gates-five-cores', all(features.get(key) is True for key in
          ['nativeFocusCore', 'nativeTouchCore', 'nativeFlashCore', 'nativePagePoolCore', 'nativeSettingsRules']))
    check('feature-gates-factory-playback-viewfinder', all(features.get(key) is False for key in
          ['newReplayEnabled', 'ownViewfinderEnabled', 'formatLockEnabled']))
    check('feature-gates-sealed-compatible', features.get('sealedQml') is True and native.get('sealedQml') is True)
    check('native-files-only-production', set(native['files']) == {'libhotspot-entry.so', 'radio-mode.sh', 'flash-ui.rcc'}, list(native['files']))
    for name, digest in native['files'].items():
        check('native-artifact-binding-' + name, sha(read(UI / 'build' / name)) == digest)
    for name, digest in native['sources'].items():
        check('native-source-binding-' + name, sha(read(ROOT / name)) == digest)
    manifest = dict(line.split('  ', 1)[::-1] for line in source(UI / 'build/manifest.sha256').splitlines())
    check('ui-build-manifest-matches', manifest == native['files'])
    ns = functions(ROOT / 'x1d/combined-runtime/four-module-r1/compose.py', ['read_rcc'], {'struct': struct, 'zlib': zlib})
    values = ns['read_rcc'](read(UI / 'build/flash-ui.rcc'))
    baseline = ns['read_rcc'](read(BASE / 'af-ui.rcc'))
    leaks = {marker: [name for name, text in values.items() if marker in name or marker in text]
             for marker in MARKERS}
    check('rcc-experimental-content-absent', not any(leaks.values()), leaks)
    check('rcc-factory-menu-route', 'generalSettingsWiFi' in values['/mainmenu/DirectMainMenu.qml'] and
          'WIFI_power' in values['/settings/SettingsGeneric.qml'])
    check('rcc-formal-radio-components-preserved', all(values.get(name) == baseline[name] for name in
          ['/common/RadioModeIcon.qml', '/common/RadioModeSettingsRow.qml']))
    check('rcc-formal-radio-selector', all(marker in values['/settings/SettingsGeneric.qml'] for marker in
          ['radioModeVerified', 'radioModeBusy', 'openRadio(list, hblNative.radioMode)']))
    check('rcc-settings-native-radio-bridge', 'property var nativeRadio:typeof hblNative' in values['/settings/NativeSettingsPage.qml'] and
          'name=="WIFI_power"' in source(UI / 'settings_rules_core.h'))
    for context in CORES:
        check('rcc-adapter-' + context, any(context in text for text in values.values()))
    check('rcc-new-replay-and-viewfinder-absent', not any(
          marker in name for marker in ['OwnViewfinder', 'OwnFocusFrame', 'JpegPlaybackSurface', 'NativePhotoPlayback', 'PhotoPlaybackPage'] for name in values))
    check('rcc-format-selection-preserved', 'property bool formatLocked:false' in values['/settings/NativeSettingsPage.qml'] and
          'CaptureFormatPolicy.qml' not in values['/common/TouchWindow.qml'])
    check('rcc-factory-liveview-root-and-evf-preserved', values['/main.qml'] == baseline['/main.qml'] and
          values['/liveview/EVFWindow.qml'] == baseline['/liveview/EVFWindow.qml'])
    expected = dict(baseline)
    functions(UI / 'raw_replay_recovery.py', ['apply_raw_replay_recovery'], ns)
    ns['apply_raw_replay_recovery'](expected, UI)
    read(UI / 'FullResolutionRetry.qml')
    check('rcc-raw-playback-only-declared-retry-change', values['/components/MediaBrowseView.qml'] == expected['/components/MediaBrowseView.qml'])
    check('rcc-original-playback-route', 'source: "qrc:///components/MediaBrowseView.qml"' in values['/common/TouchWindow.qml'])
    radio = read(UI / 'build/radio-mode.sh')
    old_radio = read(UI / 'radio-mode.sh').replace(b'\r\n', b'\n')
    block = b'if [ -f /run/hbl-hotspot-ui/started ];then\n    /bin/sh /run/hbl-hotspot-ui/network.sh restore || exit 71\nfi\n'
    check('radio-only-experimental-cleanup-removed', old_radio.count(block) == 1 and radio == old_radio.replace(block, b''))
    check('radio-formal-modes-retained', all(marker in radio for marker in
          [b'boot|0|1|2', b'target=flash', b'target=factory', b'wait_ap || exit 70', b'radio-mode-ready:%s']))
    binary = read(UI / 'build/libhotspot-entry.so')
    elf = ELFFile(io.BytesIO(binary))
    exported = [s.name for s in elf.get_section_by_name('.dynsym').iter_symbols()
                if s.name and s['st_shndx'] != 'SHN_UNDEF' and
                s['st_info']['bind'] in ('STB_GLOBAL', 'STB_WEAK') and s['st_other']['visibility'] == 'STV_DEFAULT']
    expected_exports = ['_ZN9QResource16registerResourceERK7QStringS2_',
                        '_ZN8QProcess5startERK7QStringRK11QStringList6QFlagsIN9QIODevice12OpenModeFlagEE',
                        '_ZN21QQmlApplicationEngine4loadERK4QUrl']
    check('elf-qt-interposition-exports', sorted(exported) == sorted(expected_exports) == sorted(native['definedExports']), exported)
    check('elf-arm32-little-endian', elf.elfclass == 32 and elf.little_endian and elf['e_machine'] == 'EM_ARM')
    check('elf-no-experimental-markers', not any(marker.encode(codec) in binary for marker in MARKERS for codec in ['utf-8', 'utf-16le']))
    check('elf-five-context-names-present', all(name.encode() in binary or name.encode('utf-16le') in binary for name in CORES))
    check('elf-no-implementation-symbol-table', not any(section.name == '.symtab' or section.name.startswith('.debug') for section in elf.iter_sections()))
    preprocessing = [preprocess(True), preprocess(False)]
    collects = [collect_simulation(False), collect_simulation(True)]
    build_source = source(DIST / 'build.py')
    check('distribution-signs-after-collect', build_source.index('stage, files = collect()') < build_source.index("manifest = ''.join") < build_source.index('blob, _ = lic.issue'))
    checked_builder = source(DIST / 'build_confirmed_ui.py')
    check('distribution-rejects-network-features', "features.get('experimentalNetwork') is False and native_build.get('experimentalNetwork') is False" in checked_builder)
    check('distribution-rejects-network-resource-namespace', "assert not any('/hblprotected/network/' in name for name in values)" in checked_builder)
    check('distribution-retains-core-target-regression-gates', all(marker in checked_builder for marker in
          ['flash-native-arm-regression/validation.json', "checked_rules('page-pool-native')", "checked_rules('settings-rules-native')"]))
    stale = [name for name in EXCLUDED if (UI / 'build' / name).is_file()]
    r40_names = sorted(p.name for p in BASE.iterdir())
    check('r40-no-experimental-files', not any(name in EXCLUDED or name.removeprefix('hotspot-') in EXCLUDED for name in r40_names))
    # Reject concurrent production edits so evidence always refers to one stable input set.
    changed = [name for name, digest in INPUTS.items() if sha((ROOT / name).read_bytes()) != digest]
    check('inputs-unchanged-during-audit', not changed, changed)
    report = {'schema': 'hbl-production-ui-scope-v1', 'passed': all(x['passed'] for x in CHECKS),
              'checks': CHECKS, 'checkCount': len(CHECKS), 'hardwareRequests': 0,
              'armCodeExecuted': False, 'networkOperations': 0, 'productionFilesWritten': 0,
              'finalPackageGenerated': False, 'signedReleaseVerified': False,
              'features': features, 'uiArtifactHashes': native['files'], 'rccResourceCount': len(values),
              'rccResources': {name: sha(text.encode()) for name, text in sorted(values.items())},
              'r40Files': r40_names, 'localBuildExperimentalResidueNotCollected': stale,
              'preprocessorRequiredRuntime': [p['runtimeRequired'] for p in preprocessing],
              'collectSimulations': collects, 'sourcesAndInputs': INPUTS,
              'observations': [
                  '本地 build 仍有旧实验产物；当前 manifest 与 collect 均不收集它们。',
                  'gui 准备只复制入口、radio 与 RCC；它不会删除既有 /run/hbl-hotspot-ui 中的历史文件。无实验入口引用这些文件。',
                  'componentAuthorized 在当前 nohotspot 预处理结果只要求 flash-ui.rcc 与 radio-mode.sh，缺少实验文件不会导致整体拒绝。',
                  '五个原生核心在 next(e,u) 前注册；已核查源码预处理和 ELF 证据，尚未执行此次完整 ARM GUI。',
                  'radio 生成物只删除实验客户端 restore 块；正式 boot/0/1/2 与引闪/原厂驱动事务保留。',
                  '收集演练执行真实 collect 代码，但封装仅记录调用，未访问密钥、签发、打包或安装。'],
              'pendingFinalPackageAssertions': [
                  '最终 tgz/签名 manifest 的文件清单、无 network/dhcp/native-network 候选及源码泄漏。',
                  '最终 sealed RCC 与本报告 plaintext RCC 同源，以及 resourceSealId 与 native ELF 配对。',
                  '安装后 /opt 与 /run 的 radio/RCC 副本逐字节一致；核心注册与原厂 RAW/取景实机集成及性能。']}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'README.md').write_text(
        '# 无实验联网的发行范围复核\n\n'
        + ('通过' if report['passed'] else '未通过') + f'：{len(CHECKS)} 项离线检查。\n\n'
        + '当前结果仅覆盖已构建 UI 产物、真实源码预处理及内存 collect 演练；未生成最终发行包。\n\n'
        + '\n'.join('- ' + row for row in report['observations']) + '\n\n'
        + '仍需最终合包核查：\n\n' + '\n'.join('- ' + row for row in report['pendingFinalPackageAssertions'])
        + '\n\n全部输入 SHA-256、检查与演练文件清单见 [report.json](report.json)。\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': len(CHECKS),
                      'failed': [x['name'] for x in CHECKS if not x['passed']],
                      'hardwareRequests': 0, 'finalPackageGenerated': False,
                      'report': str((OUT / 'report.json').relative_to(ROOT))}, ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
