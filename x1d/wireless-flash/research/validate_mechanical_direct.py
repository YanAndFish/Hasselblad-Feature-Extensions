"""专用触发线程的离线并发／取消检查，不访问相机。"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / 'build/mechanical-direct-candidate'
BASE = HERE / 'build/mechanical-options-candidate'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Workspace mismatch')
    compiler = ROOT / '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env = dict(os.environ)
    for key, name in [('ZIG_GLOBAL_CACHE_DIR', 'global-cache'), ('ZIG_LOCAL_CACHE_DIR', 'local-cache'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
        env[key] = str(OUT / name)
    target = OUT / 'dispatch-check.exe'
    command = [str(compiler), 'c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
               '-I', str(HERE / 'native'), '-I', str(HERE / 'CodeTests'),
               str(HERE / 'CodeTests/mechanical_direct_dispatch.test.cpp'), '-o', str(target)]
    compiled = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    if compiled.returncode:
        raise RuntimeError(compiled.stderr)
    checked = subprocess.run([str(target)], env=env, capture_output=True, text=True, timeout=15)
    if checked.returncode:
        raise RuntimeError(checked.stdout + checked.stderr)
    match = re.fullmatch(r'direct-dispatch-checks=(\d+) device-requests=0\s*', checked.stdout)
    assert match and int(match[1]) >= 30, checked.stdout
    for name in ('options_netlink_wire.h', 'options_prepared_request.h', 'options_rf_bridge.h'):
        assert (OUT / name).read_bytes() == (BASE / name).read_bytes(), 'Protocol baseline changed: ' + name
    worker = (OUT / 'options_worker.cpp').read_text(encoding='utf-8')
    for old_path in ('timer.start(core.deadline_us)', 'timing.bin', 'HblTimingRing', 'timingActive', 'recordTiming('):
        assert old_path not in worker, old_path
    assert 'transmit(core.deadline_us)' in worker
    assert 'if (core.pending) radio.cancelPendingDispatch();' in worker
    dispatch = (HERE / 'native/mechanical_direct_dispatch.h').read_text(encoding='utf-8')
    assert dispatch.count('const ssize_t submitted=sendto(') == 1
    assert 'QSocketNotifier' not in dispatch and 'QCoreApplication' not in dispatch
    assert 'F_DUPFD_CLOEXEC' in dispatch and 'PTHREAD_EXPLICIT_SCHED' in dispatch
    files = [Path(__file__), HERE / 'CodeTests/mechanical_direct_dispatch.test.cpp',
             HERE / 'CodeTests/mechanical_direct_fake_platform.h', HERE / 'native/mechanical_direct_dispatch.h',
             HERE / 'native/mechanical_direct_check.h', HERE / 'research/build_mechanical_direct.py']
    files += list(OUT.glob('options_*.h')) + list(OUT.glob('options_*.cpp'))
    report = {'passed': True, 'concurrencyChecks': int(match[1]), 'hostThreadsReal': True,
              'linuxDescriptorsAndSendSimulated': True, 'deviceRequests': 0,
              'targetSelfCheckRequired': True, 'physicalTimingVerified': False,
              'sameWireWhitelist': True, 'timingRecordingRemoved': True,
              'cancelBeforeCommitPreventsSend': True, 'cancelAfterCommitDoesNotClaimWithdrawal': True,
              'ambiguousSendNotRetried': True,
              'sourceHashes': {str(path.relative_to(HERE)): sha(path) for path in files}}
    (OUT / 'dispatch-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'sourceHashes'}, ensure_ascii=False))


if __name__ == '__main__':
    validate()
