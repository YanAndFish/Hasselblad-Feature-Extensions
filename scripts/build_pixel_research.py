"""使用显式工具链验证公开内存合成候选，仅生成合成输入，不连接设备。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'x2d/CodeTests/pixel_shift_rgb'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, help='Zig executable; validated with 0.13.0')
    parser.add_argument('--build-dir', required=True, type=Path)
    args = parser.parse_args()
    output = args.build_dir.resolve()
    try:
        output.relative_to(SOURCE.resolve())
    except ValueError:
        pass
    else:
        parser.error('Build output must be outside the source module')
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'public-validation.json'
    state = {'passed': False, 'scope': 'offline synthetic inputs',
             'device_requests': 0, 'camera_update_built': False,
             'real_capture_memory_connected': False, 'checks': []}
    report.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    compiler = args.compiler
    os.environ['HFE_ZIG'] = compiler
    # 原验证脚本仍使用同一公开源码；只把输出和允许的运行根置于显式工作目录。
    memory = load('verify_capture_memory_pipeline')
    memory.ROOT = Path.cwd().resolve()
    memory.OUT = output / 'memory'
    memory.main()
    state['checks'].append('memory kernel / frozen file pixels / bounded consumers / host and ARM builds')
    env = dict(os.environ, TEMP=str(output), TMP=str(output),
               ZIG_LOCAL_CACHE_DIR=str(output / 'zig-local'),
               ZIG_GLOBAL_CACHE_DIR=str(output / 'zig-global'))
    checks = ['check_factory_light_sharpen', 'check_factory_preview_scale',
              'check_factory_raw_stream', 'check_factory_raw_tile',
              'check_four_hundred_policy', 'check_heif_grid',
              'check_pixel_mode_events', 'check_pixel_render_route',
              'check_pixel_shutter_policy']
    for name in checks:
        executable = output / (name + ('.exe' if os.name == 'nt' else ''))
        subprocess.run([compiler, 'cc', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(SOURCE / (name + '.c')), '-o', str(executable)],
                       env=env, check=True, capture_output=True, timeout=120)
        result = subprocess.run([str(executable)], capture_output=True, text=True,
                                check=True, timeout=30)
        state['checks'].append({'name': name, 'output': result.stdout.strip()})
    tracking = ROOT / 'x2d/subject-tracking'
    executable = output / ('subject-test.exe' if os.name == 'nt' else 'subject-test')
    subprocess.run([compiler, 'cc', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I', str(tracking), str(tracking / 'subject_tracker.c'),
                    str(ROOT / 'x2d/CodeTests/subject_tracking/test_subject_tracker.c'),
                    '-lm', '-o', str(executable)], env=env, check=True,
                   capture_output=True, timeout=120)
    result = subprocess.run([str(executable)], capture_output=True, text=True,
                            check=True, timeout=30)
    state['checks'].append({'name': 'subject_tracker', 'output': result.stdout.strip()})
    sys.path.insert(0, str(SOURCE))
    tests = []
    for name in ('test_prototype', 'test_finalize_factory_jpeg'):
        module = load(name)
        if hasattr(module, 'OUT'):
            module.OUT = output / 'python-tests'
            module.OUT.mkdir(exist_ok=True)
        tests.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(tests))
    if not result.wasSuccessful():
        raise RuntimeError('Synthetic Python tests failed')
    state['checks'].append({'name': 'python image/EXIF tests', 'tests': result.testsRun})
    state['passed'] = True
    report.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    print('PASS: public synthetic validation; no camera access or installable update')


if __name__ == '__main__':
    main()
