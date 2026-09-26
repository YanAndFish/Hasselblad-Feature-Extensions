"""恢复已安装实测过的七节点、三开关完整包；不使用双 IRQ 或 FPGA 装载器。"""
import base64
import hashlib
import io
import json
from pathlib import Path
import shlex
import tarfile
import time
import mechanical_sync_loader as capture
from mechanical_hw_ready_transfer import DECODER

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-options-candidate'
INSTALLED_PACKAGE_SHA='04863977b74d71103bbdc110ed993cd2009b84577f916958912b2380eca3d424'

def package():
    assert Path.cwd().resolve()==ROOT
    previous=json.loads((OUT/'install-20260911T153113Z/installation.json').read_text(encoding='utf-8'))
    manifest=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    data=(OUT/'session-package.tar.gz').read_bytes()
    assert hashlib.sha256(data).hexdigest()==manifest['packageSha256']==previous['packageSha256']==INSTALLED_PACKAGE_SHA
    assert len(data)==manifest['packageBytes'] and manifest['files']==previous['files']
    assert previous['installed'] and previous['sevenSourcesRetained'] and previous['targetQtChecksPassed']
    assert previous['farmPayloadSha256']==capture.PAYLOAD_SHA and capture.offline_ready()
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        members=archive.getmembers()
        assert len({m.name for m in members})==len(members) and {m.name for m in members}==set(manifest['files'])
        for member in members:
            assert member.isfile() and not member.name.startswith('/') and '..' not in member.name.split('/')
            raw=archive.extractfile(member).read();expected=manifest['files'][member.name]
            assert len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256']
    return manifest,data

def stage(session,loader):
    assert not session.failed and not loader.io.failed and loader.io.closed
    assert loader.record.get('installed') and loader.record.get('armed') is False
    assert loader.record['payload_sha256']==capture.PAYLOAD_SHA
    manifest,data=package()
    session.command('create-previous-version-stage','test ! -e /tmp/hbl-wireless-flash && mkdir -m 700 /tmp/hbl-wireless-flash')
    for index,start in enumerate(range(0,len(DECODER),90)):
        session.command('previous-decoder-'+str(index),'printf %s '+shlex.quote(DECODER[start:start+90])+(' >' if index==0 else ' >>')+'/tmp/hbl-wireless-flash/d.awk')
    encoded=base64.b64encode(data).decode('ascii');parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
    for index,part in enumerate(parts):
        session.command('previous-package-'+str(index),'printf %s '+shlex.quote(part)+(' >' if index==0 else ' >>')+'/tmp/hbl-wireless-flash/p64')
        if (index+1)%100==0:print('previous package chunks',index+1,'/',len(parts),flush=True)
    session.command('previous-decode-dispatched','d=/tmp/hbl-wireless-flash;(printf \'%b\' "$(awk -f "$d/d.awk" "$d/p64")" >"$d/session.tar.gz";sha256sum "$d/session.tar.gz" >"$d/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(120):
        time.sleep(1)
        result=session.command('verify-previous-archive-'+str(attempt),'d=/tmp/hbl-wireless-flash;if test -f "$d/decode.sha"; then cat "$d/decode.sha"; else printf pending; fi')
        if result['output']!='pending':break
    else:raise RuntimeError('Decode pending; do not dispatch again')
    assert result['output'].split()[0]==manifest['packageSha256'],'Archive mismatch; no extraction'
    result=session.command('extract-previous-and-verify','cd /tmp/hbl-wireless-flash && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && printf previous-package-verified')
    assert result['output']=='previous-package-verified'
    return {'packageVerified':True,'chunks':len(parts),'bytes':len(data),'packageSha256':manifest['packageSha256']}

def mock():
    from types import SimpleNamespace
    from unittest.mock import patch
    manifest,_=package()
    loader=SimpleNamespace(io=SimpleNamespace(failed=False,closed=True),record=dict(installed=True,armed=False,payload_sha256=capture.PAYLOAD_SHA))
    class Session:
        failed=False
        def __init__(self):self.commands=[]
        def command(self,label,command):
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command
            self.commands.append((label,command))
            value=manifest['packageSha256']+'  session.tar.gz\n' if label.startswith('verify-previous-archive-') else 'previous-package-verified' if label=='extract-previous-and-verify' else ''
            return {'output':value}
    session=Session()
    with patch.object(time,'sleep',lambda seconds:None):result=stage(session,loader)
    assert sum(label=='previous-decode-dispatched' for label,_ in session.commands)==1
    report=dict(passed=True,hardwareRequests=0,commands=len(session.commands),maxCommandBytes=max(len(c.encode('ascii')) for _,c in session.commands),decodeDispatches=1,previousPackageSha256=result['packageSha256'],
        sourceHashes={str(Path(__file__).relative_to(HERE)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    (OUT/'reinstall-transfer-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':print(json.dumps(mock()))
