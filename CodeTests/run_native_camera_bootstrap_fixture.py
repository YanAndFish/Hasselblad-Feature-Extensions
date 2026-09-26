"""运行原生启动协调器的独立 RAM 后端测试；不派发任何生产服务。"""
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

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'x1d/patch-distribution'),str(ROOT/'x1d/tools'),str(ROOT/'CodeTests')]
from usb_transport import Channel
from installer import upload
from run_ui_native_arm_kit import read_file

OUT=ROOT/'x1d/patch-distribution/native-camera-bootstrap/build'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bind(evidence):
    assert evidence['passed'] and evidence['hardwareRequests']==0
    assert evidence['sources']
    for name,digest in evidence['sources'].items():
        relative=Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert sha((ROOT/relative).read_bytes())==digest, 'Source changed after fixture build: '+name
    for name in ['camera-bootstrap','backend-test','test.tgz']:
        assert sha((OUT/name).read_bytes())==evidence['files'][name], name


def main():
    assert Path.cwd().resolve()==ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read',action='store_true')
    args=parser.parse_args()
    evidence=json.loads((OUT/'core-validation.json').read_text(encoding='utf-8'))
    bind(evidence)
    data=(OUT/'test.tgz').read_bytes()
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        members=archive.getmembers()
        assert len(members)==1 and members[0].name=='runner' and members[0].isfile()
        assert sha(archive.extractfile(members[0]).read())==evidence['files']['backend-test']
    state_path=OUT/'target-run.json'
    channel=Channel()
    if args.read:
        state=json.loads(state_path.read_text(encoding='utf-8'))
        remote=state['remote']
        assert re.fullmatch('/tmp/hbl-nbt-[0-9]{12}',remote)
        assert state['fixtureSha256']==evidence['files']['backend-test']
    else:
        assert not state_path.exists(), 'Prior dispatch recorded; inspect with --read, never repeat an uncertain run'
        remote='/tmp/hbl-nbt-'+datetime.now().strftime('%y%m%d%H%M%S')
        state={'remote':remote,'fixtureSha256':evidence['files']['backend-test'],
               'productionBinarySha256':evidence['files']['camera-bootstrap'],
               'dispatchAttempted':False,'cameraBusinessRequests':0,'productionRolesExecuted':0,
               'sources':evidence['sources']}
        state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
        upload(channel,remote,data,'p.tgz')
        prepared=channel.command('r='+remote+';tar xzf "$r/p.tgz" -C "$r" && chmod 700 "$r/runner";echo $?')
        assert prepared=='0', 'Fixture preparation failed; no test dispatched'
        state['dispatchAttempted']=True
        state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
        channel.command('r='+remote+';(LD_PRELOAD= "$r/runner" "$r" >"$r/out" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &')
    with channel.session():
        for _ in range(55):
            status=channel.command('r='+remote+';if test -s "$r/exit";then cat "$r/exit";else echo pending;fi')
            if status!='pending':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Fixture result unconfirmed; inspect with --read, do not redispatch')
        state['exitCode']=int(status)
        (OUT/'target-out.txt').write_bytes(read_file(channel,remote,'out'))
        if channel.command('test -s '+remote+'/result.json && echo yes || echo no')=='yes':
            (OUT/'target-result.json').write_bytes(read_file(channel,remote,'result.json'))
        state['guiServiceAfter']=channel.command('systemctl is-active victory-gui;true')
    state['transportRequests']=channel.requests
    state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
    assert state['exitCode']==0, 'Fixture failed; inspect retained bounded output'
    result=json.loads((OUT/'target-result.json').read_text(encoding='utf-8'))
    assert result['passed'] and result['cameraBusinessRequests']==0 and result['assertions']>=25
    assert state['guiServiceAfter']=='active'
    bind(evidence)
    result.update(sources=evidence['sources'],productionBinarySha256=evidence['files']['camera-bootstrap'],
                  fixtureSha256=evidence['files']['backend-test'],guiServiceAfter=state['guiServiceAfter'],
                  realProductionServicesExecuted=False,productionRolesExecuted=0,coldBootValidated=False,
                  hardwareMountOperations=0,target='X1D-50c1.25.0 ARM Linux 3.14.28')
    (OUT/'target-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'assertions':result['assertions'],'guiServiceAfter':state['guiServiceAfter'],
                      'cameraBusinessRequests':0,'productionRolesExecuted':0,'transportRequests':channel.requests}))


if __name__=='__main__':
    main()
