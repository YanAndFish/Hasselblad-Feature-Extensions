"""构建、故障注入及 ARM 编译；不安装、不操作相机。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0, str(BASE))
import build_fast_baseline
_, _, manifest = build_fast_baseline.build()
out = BASE / 'build/fast-start-research'
env = dict(os.environ)
for key, folder in [('ZIG_GLOBAL_CACHE_DIR', 'global'), ('ZIG_LOCAL_CACHE_DIR', 'local'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
    path = out / folder
    path.mkdir(exist_ok=True)
    env[key] = str(path)
zig = str(ROOT / '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe')
source = BASE / 'native/fast_baseline.c'
exe = out / 'fast_baseline_check.exe'
subprocess.run([zig, 'c++', '-x', 'c++', '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), str(BASE/'CodeTests/fast_baseline.test.cpp'), '-o', str(exe)], env=env, check=True)
run = subprocess.run([str(exe)], env=env, check=True, capture_output=True, text=True)
subprocess.run([zig, 'cc', '-target', 'arm-freestanding-eabi', '-mcpu=cortex_a9', '-marm', '-Oz', '-ffreestanding', '-fno-stack-protector', '-c', str(source), '-o', str(out/'fast_baseline_arm.o')], env=env, check=True)
report = {'passed': True, 'model': run.stdout.strip(), 'manifest': manifest,
          'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'armObjectBytes': (out/'fast_baseline_arm.o').stat().st_size,
          'installed': False, 'hardwareRequests': 0, 'timingProven': False}
(out/'fast-baseline-validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report))
