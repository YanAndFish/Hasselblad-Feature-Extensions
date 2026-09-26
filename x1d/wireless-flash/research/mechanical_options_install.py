"""绑定纯记录旧包的两开关增量传输；单次解码、失败会话不复用。"""
import base64
from datetime import datetime,timezone
import hashlib,json,shlex,time
from pathlib import Path
from mechanical_hw_ready_transfer import DECODER

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-options-candidate'
STAGE='/tmp/hbl-wireless-flash/options1'

def package():
    m=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    data=(OUT/'update/update.tar.gz').read_bytes()
    assert hashlib.sha256(data).hexdigest()==m['updateSha256'] and len(data)==m['updateBytes']
    c=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    v=json.loads((OUT/'options-validation.json').read_text(encoding='utf-8'))
    assert c['passed'] and v['passed']
    for name,digest in c['sourceHashes'].items(): assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
    return m,data

def stage(session):
    m,data=package()
    session.command('create-options-stage','test ! -e '+STAGE+' && mkdir -m 700 '+STAGE)
    for index,start in enumerate(range(0,len(DECODER),90)):
        session.command('options-decoder-'+str(index),'printf %s '+shlex.quote(DECODER[start:start+90])+(' >' if index==0 else ' >>')+STAGE+'/d.awk')
    encoded=base64.b64encode(data).decode('ascii')
    parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
    for index,part in enumerate(parts):
        session.command('options-package-'+str(index),'printf %s '+shlex.quote(part)+(' >' if index==0 else ' >>')+STAGE+'/p64')
        if (index+1)%100==0: print('options package chunks',index+1,'/',len(parts),flush=True)
    session.command('options-decode-dispatched','d='+STAGE+';(printf \'%b\' "$(awk -f "$d/d.awk" "$d/p64")" >"$d/update.tar.gz";sha256sum "$d/update.tar.gz" >"$d/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(120):
        time.sleep(1)
        r=session.command('verify-options-archive-'+str(attempt),'d='+STAGE+';if test -f "$d/decode.sha"; then cat "$d/decode.sha"; else printf pending; fi')
        if r['output']!='pending': break
    else: raise RuntimeError('Decode pending; do not dispatch again')
    assert r['output'].split()[0]==m['updateSha256'],'Uploaded archive mismatch'
    r=session.command('extract-options-and-verify','cd '+STAGE+' && tar xzf update.tar.gz && sha256sum -c update.sha256 >/dev/null && printf options-package-verified')
    assert r['output']=='options-package-verified'
    print('options archive verified',len(parts),len(data),flush=True)

def mock():
    m,_=package()
    class Mock:
        def __init__(self): self.commands=[]
        def command(self,label,command):
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command
            self.commands.append((label,command))
            output=m['updateSha256']+'  update.tar.gz\n' if label.startswith('verify-options-archive-') else 'options-package-verified' if label=='extract-options-and-verify' else ''
            return {'output':output}
    session=Mock(); old=time.sleep
    try:
        time.sleep=lambda n:None
        stage(session)
    finally: time.sleep=old
    assert sum(label=='options-decode-dispatched' for label,_ in session.commands)==1
    report={'passed':True,'commands':len(session.commands),'maxCommandBytes':max(len(c.encode('ascii')) for _,c in session.commands),'decodeDispatches':1,'hardwareRequests':0}
    (OUT/'transfer-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

def finish(session,loader,farm_request_start,farm_write_start,checks,marker,runtime,qml,mode_on,owner_on,mode_off,owner_off):
    m,_=package()
    assert not session.failed and all(e.get('matched') and e.get('closed') and e.get('exit_code')==0 for e in session.entries)
    assert sum(e['label']=='options-decode-dispatched' for e in session.entries)==1
    assert any(e['label']=='extract-options-and-verify' and e['output']=='options-package-verified' for e in session.entries)
    assert any(e['label'].startswith('verify-options-archive-') and e.get('output','').split()[0]==m['updateSha256'] for e in session.entries if e.get('output') and e['label'].startswith('verify-options-archive-'))
    assert marker['output']=='normal-driver-marker=0x5851\n'
    assert runtime['output']=='ui-loaded-worker-default-off\nactive\nactive\nactive\n'
    assert qml['output'].strip()=='0'
    for expected in ('sync-hook-selftest: own=5 forwarded=272 status=1 hardware=0','qt-receiver-check=3 hardware-requests=0','timerfd-check=3 units=us hardware-requests=0','options-delivery-check=6 hardware-requests=0'):
        assert expected in checks['output'],expected
    assert mode_on['output']=='process-mode=1 ready-default-off\n'
    assert mode_off['output']=='process-mode=0 ready-default-off\n'
    def owner(result,mode):
        lines=result['output'].strip().splitlines()
        assert len(lines)==2 and lines[0].startswith('same-process='+str(mode)+' pid=')
        worker_pid=int(lines[0].split('pid=')[1]); farm_pid=int(lines[1].split('=')[1])
        assert worker_pid>0 and farm_pid>0 and ((worker_pid==farm_pid)==bool(mode))
    owner(owner_on,1); owner(owner_off,0)
    assert loader.io.closed and not loader.io.failed and loader.io.writes==farm_write_start
    assert loader.record['installed'] and loader.record['armed']
    folder=OUT/('install-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')); folder.mkdir()
    index=HERE/'build/mechanical-sync-candidate/installation.json'
    (folder/'previous-installation.json').write_bytes(index.read_bytes())
    (folder/'farm-baseline-recovery.json').write_bytes(loader.path.read_bytes())
    evidence=folder/'verified-linux-session.json'
    evidence.write_text(json.dumps({'failed':False,'entries':session.entries},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'kind':'resident-mechanical-preparation-and-process-options','installed':True,'observedAt':datetime.now(timezone.utc).isoformat(),
            'installationMode':'verified-pure-timing-upgrade-with-existing-farm-hooks','packageSha256':m['packageSha256'],
            'updateSha256':m['updateSha256'],'files':m['files'],'firmwareSha256':m['firmwareSha256'],'farmPayloadSha256':m['farmPayloadSha256'],
            'linuxEvidence':str(evidence.relative_to(HERE)),'farmRecoveryRecord':str(loader.path.relative_to(HERE)),
            'farmVerificationRequests':loader.io.requests-farm_request_start,'farmWritesThisUpdate':0,
            'linuxRequests':len(session.entries),'allUsbHandlesClosed':True,'cameraShotsTriggered':0,'agentFlashTrials':0,
            'targetQtChecksPassed':True,'targetSameProcessStarted':True,'targetSeparateProcessRestored':True,
            'sameProcessPidEqualityVerified':True,'defaultAutomaticOff':True,'defaultPerShot':False,'defaultSameProcess':False,
            'sameProcessCrossThreadDelivery':'bounded Qt event queue','sevenSourcesRetained':True,'timingRecordRetained':True,
            'compensationImplemented':False,'newHardwareInterruptImplemented':False,'flashPowerParameterTransmissionImplemented':False,
            'physicalFlashTimingVerified':False,'physicalReadyRetentionVerified':False,'physicalEmissionDuringPrepareVerified':False,
            'afSpeeds':loader.record['af_speeds']}
    for path in (folder/'installation.json',OUT/'installation.json',index,HERE/'build/installation.json'):
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    doc=HERE/'research/MECHANICAL_OPTIONS.md'
    text=doc.read_text(encoding='utf-8')
    text=text.replace('当前状态：离线构建与验证通过，正在装入相机；本文不能作为安装成功证据。实际安装结果以本候选的 `installation.json` 为准。',
                      '当前状态：两个开关已装入相机。机内非发射检查通过，同一程序模式与独立程序模式都已实际启动并核对进程归属；最终回到独立程序模式，自动引闪默认关闭。物理时序与同步稳定性等待用户试拍。安装证据见本候选 `installation.json`。')
    doc.write_text(text,encoding='utf-8')
    return {'installed':True,'sameProcessVerified':True,'separateProcessRestored':True,'farmWrites':0,'closed':True}

if __name__=='__main__': print(mock())
