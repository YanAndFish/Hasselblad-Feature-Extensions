"""用显式工具链构建真实核心的主机测试；不访问设备或私有缓存。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from build_contract import validate_radio_tables, write_report

ROOT = Path(__file__).resolve().parents[1]
TESTS = {
    'flash-policy': 'x1d/combined-runtime/four-module-r1/persistent-r1/CodeTests/formal_policy.test.cpp',
    'halfpress-policy': 'x1d/wireless-flash/halfpress-power/CodeTests/policy_check.cpp',
    'persistent-settings': 'x1d/combined-runtime/four-module-r1/persistent-r1/CodeTests/persistent_settings.test.cpp',
    'settings-restore': 'x1d/combined-runtime/four-module-r1/persistent-r1/CodeTests/settings_restore.test.cpp',
    'audio-route': 'x1d/shutter-effects/CodeTests/audio_route_test.cpp',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, help='C++ compiler or Zig executable')
    parser.add_argument('--driver', choices=['cxx', 'zig'], default='cxx')
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--radio-tables', type=Path, help='Explicit locally generated radio tables; enables real adapter test')
    args = parser.parse_args()
    output = args.build_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['ZIG_GLOBAL_CACHE_DIR'] = str(output / 'zig-global')
    env['ZIG_LOCAL_CACHE_DIR'] = str(output / 'zig-local')
    report = {'passed': False, 'scope': 'host core tests', 'deviceAccess': False,
              'cameraUpdateBuilt': False, 'tests': []}
    report_path = output / 'core-validation.json'
    write_report(report_path, report)
    tests = dict(TESTS)
    include_flags = []
    if args.radio_tables:
        folder = args.radio_tables.resolve()
        manifest = validate_radio_tables(folder)
        include_flags = ['-DHBL_EXTERNAL_RADIO_TABLES', '-I', str(folder)]
        tests['flash-adapter'] = 'x1d/combined-runtime/four-module-r1/persistent-r1/CodeTests/formal_policy_adapter.test.cpp'
    for name, relative in tests.items():
        source = ROOT / relative
        executable = output / (name + ('.exe' if os.name == 'nt' else ''))
        command = [args.compiler] + (['c++'] if args.driver == 'zig' else [])
        command += include_flags + ['-I', str(ROOT / 'x1d/combined-runtime/four-module-r1/persistent-r1/CodeTests')] + ['-std=c++11', '-O0', '-I', str(ROOT / 'x1d/combined-runtime/four-module-r1/persistent-r1/native'), str(source), '-o', str(executable)]
        subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=180)
        result = subprocess.run([str(executable)], cwd=ROOT, env=env,
                                check=True, text=True, capture_output=True, timeout=60)
        print(result.stdout, end='')
        report['tests'].append({'name': name, 'passed': True, 'output': result.stdout.strip(),
                               'testSourceSha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    report['passed'] = True
    write_report(report_path, report)
    print('PASS: host core compiled and executed; no device access; camera update not built')

if __name__ == '__main__':
    main()
