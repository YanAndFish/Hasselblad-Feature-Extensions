"""AF bus 启动修正版的附加绑定，不覆盖之前的 AF-only 报告。"""
import hashlib, json, os, sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from af_only_loader import readiness, read_json

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    previous = readiness()
    if previous is None:
        raise ValueError('previous frozen AF-only sources changed')
    tests = read_json(HERE / 'bus-startup-r2/startup-tests.json')
    if not tests['passed'] or tests['hardwareRequests'] != 0:
        raise ValueError('ARM startup model evidence required')
    files = dict(previous['files'])
    for name, expected in tests['files'].items():
        if sha(HERE / name) != expected:
            raise ValueError('startup test input changed: ' + name)
        files[name] = expected
    folder = HERE / 'bus-startup-r2'
    build = read_json(folder / 'linux-build/client-build.json')
    for name, expected in build['sourceHashes'].items():
        path = (folder / name).resolve()
        if sha(path) != expected:
            raise ValueError('startup build input changed: ' + name)
        files[os.path.relpath(path, HERE)] = expected
    for name, expected in build['outputs'].items():
        path = folder / 'linux-build' / name
        if sha(path) != expected['sha256']:
            raise ValueError('startup library changed')
        files[os.path.relpath(path, HERE)] = expected['sha256']
    for path in (Path(__file__), HERE / 'af_only_bus_r2_loader.py',
            HERE / 'build/af-only-validation.json', folder / 'startup-tests.json',
            folder / 'linux-build/client-build.json'):
        files[os.path.relpath(path, HERE)] = sha(path)
    report = dict(previous)
    report.update({'revision': 'af-only-bus-startup-r2', 'previousValidationSha256': sha(HERE / 'build/af-only-validation.json'),
        'files': files, 'busStartupArmTests': tests['tests'], 'targetQtRuntimeVerified': False,
        'runtimeBus': {'path': 'bus-startup-r2/linux-build/libhbl-af-bus.so',
                       **build['outputs']['libhbl-af-bus.so']},
        'runtimeUi': {'path': 'linux-build/libhbl-af-ui.so', 'sha256': sha(HERE / 'linux-build/libhbl-af-ui.so')},
        'backendStatusPath': '/tmp/hbl-af-settings/backend-r2.status',
        'limitation': '真实 Qt 事件循环、端点绑定及消息往返仍由主任务现场验收；无自动设备消息'})
    (HERE / 'build/af-only-bus-r2-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('passed', 'standaloneAf', 'requiresInstalledHfs1',
        'offlineFirstInstallReady', 'offlineRollbackReady', 'busStartupArmTests', 'runtimeBus',
        'runtimeUi', 'previousValidationSha256', 'targetQtRuntimeVerified', 'hardwareRequests')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
