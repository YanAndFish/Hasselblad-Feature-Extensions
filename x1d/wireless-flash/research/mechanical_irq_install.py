"""已验证 FPGA 与未武装采集之后的两来源临时包传输；不自动启动或发射。"""
import base64
import hashlib
import io
import json
from pathlib import Path
import shlex
import tarfile
import time
from mechanical_hw_ready_transfer import DECODER

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'

def package():
    assert Path.cwd().resolve()==ROOT
    manifest=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    data=(OUT/'session-package.tar.gz').read_bytes()
    assert manifest['passed'] and manifest['sources']==[2,3] and manifest['messageVersion']==2 and manifest['bridgeVersion']==4
    assert len(data)==manifest['packageBytes'] and hashlib.sha256(data).hexdigest()==manifest['packageSha256']
    clients=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    wire=json.loads((OUT/'irq-wire-validation.json').read_text(encoding='utf-8'))
    ui=json.loads((OUT/'ui-build.json').read_text(encoding='utf-8'))
    assert clients['passed'] and wire['passed'] and ui['built']
    for report in (manifest,clients,wire):
        for name,digest in report.get('sourceHashes',{}).items():
            assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
    assert hashlib.sha256((HERE/'research/build_mechanical_irq_ui.py').read_bytes()).hexdigest()==ui['sourceSha256']
    assert manifest['files']['ui.rcc']['sha256']==ui['rccSha256']
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        members=archive.getmembers()
        assert len({m.name for m in members})==len(members)
        assert {m.name for m in members}==set(manifest['files'])
        for member in members:
            assert member.isfile() and not member.name.startswith('/') and '..' not in member.name.split('/')
            raw=archive.extractfile(member).read();expected=manifest['files'][member.name]
            assert len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256']
    return manifest,data

def stage(session,capture):
    assert not session.failed and not capture.io.failed and capture.io.closed
    assert all(capture.record.get(k) for k in ('fpga_configured','installed','irq_configuration_installed'))
    assert capture.record.get('armed') is False
    manifest,data=package()
    session.command('create-irq-linux-stage','test ! -e /tmp/hbl-wireless-flash && mkdir -m 700 /tmp/hbl-wireless-flash')
    for index,start in enumerate(range(0,len(DECODER),90)):
        session.command('irq-decoder-'+str(index),'printf %s '+shlex.quote(DECODER[start:start+90])+(' >' if index==0 else ' >>')+'/tmp/hbl-wireless-flash/d.awk')
    encoded=base64.b64encode(data).decode('ascii');parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
    for index,part in enumerate(parts):
        session.command('irq-package-'+str(index),'printf %s '+shlex.quote(part)+(' >' if index==0 else ' >>')+'/tmp/hbl-wireless-flash/p64')
        if (index+1)%100==0:print('irq package chunks',index+1,'/',len(parts),flush=True)
    session.command('irq-decode-dispatched','d=/tmp/hbl-wireless-flash;(printf \'%b\' "$(awk -f "$d/d.awk" "$d/p64")" >"$d/session.tar.gz";sha256sum "$d/session.tar.gz" >"$d/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(120):
        time.sleep(1)
        result=session.command('verify-irq-archive-'+str(attempt),'d=/tmp/hbl-wireless-flash;if test -f "$d/decode.sha"; then cat "$d/decode.sha"; else printf pending; fi')
        if result['output']!='pending':break
    else:raise RuntimeError('Decode pending; do not dispatch again')
    assert result['output'].split()[0]==manifest['packageSha256'],'Uploaded archive mismatch; no extraction'
    result=session.command('extract-irq-and-verify','cd /tmp/hbl-wireless-flash && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && printf irq-package-verified')
    assert result['output']=='irq-package-verified'
    return {'packageVerified':True,'chunks':len(parts),'bytes':len(data),'packageSha256':manifest['packageSha256']}

def mock():
    from types import SimpleNamespace
    from unittest.mock import patch
    manifest,_=package()
    capture=SimpleNamespace(io=SimpleNamespace(failed=False,closed=True),record=dict(fpga_configured=True,installed=True,irq_configuration_installed=True,armed=False))
    class Session:
        failed=False
        def __init__(self,bad_hash=False):self.commands=[];self.bad_hash=bad_hash
        def command(self,label,command):
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command
            self.commands.append((label,command))
            result=(('bad' if self.bad_hash else manifest['packageSha256'])+'  session.tar.gz\n') if label.startswith('verify-irq-archive-') else 'irq-package-verified' if label=='extract-irq-and-verify' else ''
            return {'output':result}
    with patch.object(time,'sleep',lambda seconds:None):
        session=Session();stage(session,capture)
        assert sum(label=='irq-decode-dispatched' for label,_ in session.commands)==1
        bad=Session(True)
        try:stage(bad,capture)
        except AssertionError:pass
        else:raise AssertionError('Changed archive accepted')
        assert not any(label=='extract-irq-and-verify' for label,_ in bad.commands)
        early=Session();capture.record['fpga_configured']=False
        try:stage(early,capture)
        except AssertionError:pass
        else:raise AssertionError('Missing FPGA evidence accepted')
        assert not early.commands
    report={'passed':True,'hardwareRequests':0,'commands':len(session.commands),'maxCommandBytes':max(len(c.encode('ascii')) for _,c in session.commands),'decodeDispatches':1,'wrongArchiveNotExtracted':True,'missingFpgaEvidenceRejectedBeforeCommand':True,
            'sourceHashes':{str(Path(__file__).relative_to(HERE)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    (OUT/'irq-transfer-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':print(json.dumps(mock()))
