"""运行审查过的独立 RAM 启动器夹具；不执行任何真实相机服务。"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'x1d/patch-distribution'), str(ROOT / 'x1d/tools'), str(ROOT / 'CodeTests')]
from usb_transport import Channel
from installer import upload
from run_ui_native_arm_kit import read_file

BASE = ROOT / 'build/native-camera-launch'
OUT = BASE / 'fixture-bootstrap'
FIXTURE = '/tmp/hbl-nla-bootstrap-fixture'


def main():
    assert Path.cwd().resolve() == ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((OUT / 'fixture-build.json').read_text(encoding='utf-8'))
    assert manifest['passed'] and manifest['fixtureRoot'] == FIXTURE
    for name, digest in manifest['sources'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    runner = (OUT / 'hbl-nla-fixture-runner').read_bytes()
    assert hashlib.sha256(runner).hexdigest() == manifest['runner']['sha256']
    state_path = OUT / 'run.json'
    channel = Channel()
    if args.read:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        remote = state['remote']
        assert re.fullmatch('/tmp/hbl-nlt-[0-9]{12}', remote)
        assert state['fixtureSha256'] == manifest['runner']['sha256']
    else:
        assert not state_path.exists(), 'Prior fixture dispatch recorded; inspect with --read, never redispatch blindly'
        status = channel.command('if test -e ' + FIXTURE + ' || test -L ' + FIXTURE + ';then echo exists;else echo absent;fi')
        assert status == 'absent', 'Fixed fixture namespace already exists; no cleanup or reuse attempted'
        remote = '/tmp/hbl-nlt-' + datetime.now().strftime('%y%m%d%H%M%S')
        state = {'remote': remote, 'fixtureSha256': manifest['runner']['sha256'],
                 'cameraBusinessRequests': 0, 'productionRolesExecuted': 0,
                 'dispatchAttempted': False}
        state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        upload(channel, remote, runner, 'runner')
        channel.command('chmod 700 ' + remote + '/runner')
        state['dispatchAttempted'] = True
        state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        channel.command('r=' + remote + ';(LD_PRELOAD= "$r/runner" >"$r/out" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &')
    with channel.session():
        for _ in range(55):
            status = channel.command('r=' + remote + ';if test -s "$r/exit";then cat "$r/exit";else echo pending;fi')
            if status != 'pending':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Fixture result unconfirmed; inspect with --read, do not redispatch')
        state['exitCode'] = int(status)
        (OUT / 'target-out').write_bytes(read_file(channel, remote, 'out'))
        exists = channel.command('test -s ' + FIXTURE + '/result.json && echo yes || echo no')
        if exists == 'yes':
            (OUT / 'target-result.json').write_bytes(read_file(channel, FIXTURE, 'result.json'))
        state['guiServiceAfter'] = channel.command('systemctl is-active victory-gui;true')
    state['transportRequests'] = channel.requests
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    assert state['exitCode'] == 0, 'Fixture failed; inspect retained bounded output'
    result = json.loads((OUT / 'target-result.json').read_text(encoding='utf-8'))
    assert result['passed'] and result['executedCases'] == result['expectedCases'] == 30
    assert result['cameraBusinessRequests'] == result['productionRolesExecuted'] == 0
    assert result['sources'] == manifest['sources']
    assert result['productionBinarySha256'] == manifest['productionBinarySha256']
    assert state['guiServiceAfter'] == 'active'
    result.update(guiServiceAfter=state['guiServiceAfter'], fixtureSha256=state['fixtureSha256'],
                  realProductionServicesExecuted=False, coldBootValidated=False)
    (BASE / 'target-validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, 'linuxFixtureCases': result['executedCases'],
                      'guiServiceAfter': state['guiServiceAfter'], 'cameraBusinessRequests': 0,
                      'productionRolesExecuted': 0, 'transportRequests': channel.requests}))


if __name__ == '__main__':
    main()
