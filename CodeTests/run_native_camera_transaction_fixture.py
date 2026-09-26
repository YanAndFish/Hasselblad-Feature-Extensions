"""仅在固定私有RAM目录测试原生事务；真实挂载、服务和授权均为替身。"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'x1d/patch-distribution'), str(ROOT / 'x1d/tools'), str(ROOT / 'CodeTests')]
from usb_transport import Channel
from installer import upload
from run_ui_native_arm_kit import read_file

OUT = ROOT / 'x1d/patch-distribution/native-camera-transaction/build'
FIXTURE = '/tmp/hbl-ntx-repair2-fixture'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(evidence, name):
    return evidence['files'][name]['sha256']


def bind(evidence):
    assert evidence['passed'] and evidence['hardwareRequests'] == 0 and evidence['sources']
    for name, expected in evidence['sources'].items():
        path = Path(name)
        assert not path.is_absolute() and '..' not in path.parts
        assert digest((ROOT / path).read_bytes()) == expected, 'Source changed: ' + name
    for name in ['camera-transaction', 'fixture-runner', 'fixture-helper']:
        assert digest((OUT / name).read_bytes()) == file_digest(evidence, name), name


def main():
    assert Path.cwd().resolve() == ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read', action='store_true')
    args = parser.parse_args()
    evidence = json.loads((OUT / 'core-validation.json').read_text(encoding='utf-8'))
    bind(evidence)
    assert FIXTURE.encode() in (OUT / 'fixture-runner').read_bytes()
    state_path = OUT / 'target-repair2-run.json'
    channel = Channel()
    if args.read:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        remote = state['remote']
        assert re.fullmatch('/tmp/hbl-ntr-[0-9]{12}', remote)
        assert state['fixtureSha256'] == file_digest(evidence, 'fixture-runner')
    else:
        assert not state_path.exists(), 'Prior dispatch exists; use --read, never redispatch an uncertain operation'
        result = channel.command('if test -e ' + FIXTURE + ' || test -L ' + FIXTURE + ';then echo exists;else echo absent;fi')
        assert result == 'absent', 'Fixed fixture namespace already exists; no automatic cleanup'
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
            for source, name in [('fixture-runner', 'runner'), ('fixture-helper', 'helper')]:
                data = (OUT / source).read_bytes()
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o700
                tar.addfile(info, io.BytesIO(data))
        payload = buffer.getvalue()
        remote = '/tmp/hbl-ntr-' + datetime.now().strftime('%y%m%d%H%M%S')
        state = dict(remote=remote, fixtureRoot=FIXTURE, fixtureSha256=file_digest(evidence, 'fixture-runner'),
                     helperSha256=file_digest(evidence, 'fixture-helper'), transferSha256=digest(payload),
                     productionBinarySha256=file_digest(evidence, 'camera-transaction'), sources=evidence['sources'],
                     dispatchAttempted=False, cameraBusinessRequests=0, realMountRequests=0)
        state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        (OUT / 'target-fixture.tgz').write_bytes(payload)
        upload(channel, remote, payload, 'p.tgz')
        prepared = channel.command('r=' + remote + ';f=' + FIXTURE + ';test ! -e "$f" && test ! -L "$f" && mkdir -m 700 "$f" && tar xzf "$r/p.tgz" -C "$f" && chmod 700 "$f/runner" "$f/helper";echo $?')
        assert prepared == '0', 'RAM fixture preparation failed; no test dispatched'
        state['dispatchAttempted'] = True
        state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        channel.command('r=' + remote + ';(LD_PRELOAD= ' + FIXTURE + '/runner >"$r/out" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &')
    with channel.session():
        for _ in range(55):
            status = channel.command('r=' + remote + ';if test -s "$r/exit";then cat "$r/exit";else echo pending;fi')
            if status != 'pending':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Result unconfirmed; inspect with --read, never redispatch')
        state['exitCode'] = int(status)
        (OUT / 'target-out.txt').write_bytes(read_file(channel, remote, 'out'))
        if channel.command('test -s ' + FIXTURE + '/result.json && echo yes || echo no') == 'yes':
            (OUT / 'target-result.json').write_bytes(read_file(channel, FIXTURE, 'result.json'))
        state['guiServiceAfter'] = channel.command('systemctl is-active victory-gui;true')
    state['transportRequests'] = channel.requests
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    assert state['exitCode'] == 0, 'RAM test failed; retained diagnostic output'
    result = json.loads((OUT / 'target-result.json').read_text(encoding='utf-8'))
    assert result['passed'] and result['cameraBusinessRequests'] == result['realMountRequests'] == result['productionRolesExecuted'] == 0
    assert result['caseCount'] == len(set(result['cases'])) >= 33
    for name in ['reject-write-and-copy-hardlink-target', 'copy-growing-source-limit',
                 'reject-unknown-visible-root', 'readonly-recovery-preserves-last-known-flags']:
        assert name in result['cases']
    assert state['guiServiceAfter'] == 'active'
    bind(evidence)
    result.update(sources=evidence['sources'], productionBinarySha256=file_digest(evidence, 'camera-transaction'),
                  fixtureSha256=file_digest(evidence, 'fixture-runner'), guiServiceAfter=state['guiServiceAfter'],
                  productionInstallationExecuted=False, coldBootValidated=False,
                  target='X1D-50c1.25.0 ARM Linux 3.14.28')
    (OUT / 'target-validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=True, caseCount=result['caseCount'], guiServiceAfter=state['guiServiceAfter'],
                         cameraBusinessRequests=0, realMountRequests=0)))


if __name__ == '__main__':
    main()
