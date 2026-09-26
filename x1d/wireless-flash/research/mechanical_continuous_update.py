"""仅更新已装 GMS1 的 Linux worker、界面和资源；不触碰 FARM 或 AF。"""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
from mechanical_sync_transfer import DECODER

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-sync-candidate'
UPDATE=OUT/'continuous-update'
REMOTE='/tmp/hbl-wireless-flash/u1'
NAMES=('wireless-worker','libhbl-wireless.so','ui.rcc','manifest.sha256')

def sha(data): return hashlib.sha256(data).hexdigest()

def make():
    assert Path.cwd().resolve()==HERE.parents[1]
    old=json.loads((OUT/'installation.json').read_text(encoding='utf-8'))
    new=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    ui=json.loads((HERE/'build/mechanical-ui-test/validation.json').read_text(encoding='utf-8'))
    if not old.get('installed') or not ui.get('passed'): raise RuntimeError('Missing baseline or UI checks')
    for name,digest in ui['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest: raise RuntimeError('UI evidence changed')
    if old['farmPayloadSha256']!=new['farmPayloadSha256']: raise RuntimeError('FARM payload changed')
    for name in old['files']:
        if name not in NAMES and old['files'][name]!=new['files'][name]:
            raise RuntimeError('Unexpected change outside Linux update: '+name)
    files={}
    with tarfile.open(OUT/'session-package.tar.gz','r:gz') as archive:
        for name in NAMES: files[name]=archive.extractfile(name).read()
    checks='\n'.join('[ "$(sha256sum "$d/'+name+'" | cut -d\' \' -f1)" = '+old['files'][name]['sha256']+' ] || exit 62' for name in NAMES)
    checks+='\n[ "$(sha256sum "$d/libhbl-mechanical-observer.so" | cut -d\' \' -f1)" = '+old['files']['libhbl-mechanical-observer.so']['sha256']+' ] || exit 62'
    files['apply.sh']=('''#!/bin/sh
set -eu
d=/tmp/hbl-wireless-flash
u="$d/u1"
[ -d "$d" ] && [ ! -L "$d" ] && [ -d "$u" ] && [ ! -L "$u" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] || exit 60
[ ! -e "$u/backup" ] || exit 60
cd "$u"
sha256sum -c update.sha256 >/dev/null || exit 61
@CHECKS@
for service in victory-gui msg2dbus-farm hbl-wireless-worker; do
    systemctl is-active --quiet "$service" || exit 63
done
grep -Eq '^stage=(ready|forwarded) error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status" || exit 63
chmod 700 "$u/wireless-worker"
"$u/wireless-worker" --check-slots || exit 64
mkdir -m 700 "$u/backup"
for name in wireless-worker libhbl-wireless.so ui.rcc manifest.sha256; do cp -p "$d/$name" "$u/backup/$name"; done
for name in diagnostics mechanical-samples; do [ ! -f "$d/$name" ] || cp "$d/$name" "$u/backup/$name"; done
rollback() {
    result=$?
    trap - 0 1 2 15
    systemctl stop hbl-wireless-worker victory-gui || true
    for name in wireless-worker libhbl-wireless.so ui.rcc manifest.sha256; do
        cp -p "$u/backup/$name" "$d/$name.rollback" && mv -f "$d/$name.rollback" "$d/$name"
    done
    systemctl start hbl-wireless-worker && systemctl restart msg2dbus-farm && systemctl start victory-gui || true
    printf 'update-rolled-back\\n' > "$u/result"
    exit "$result"
}
trap rollback 0
trap 'exit 72' 1 2 15
systemctl stop hbl-wireless-worker
systemctl stop victory-gui
for name in wireless-worker libhbl-wireless.so ui.rcc manifest.sha256; do
    cp "$u/$name" "$d/$name.next" && mv -f "$d/$name.next" "$d/$name"
done
chmod 700 "$d/wireless-worker"
cd "$d"
sha256sum -c manifest.sha256 >/dev/null
rm -f "$d/runtime.status" "$d/worker.status"
systemctl start hbl-wireless-worker
# 原 observer 的 datagram connect 绑定旧 worker socket，必须重新连接新实例。
systemctl restart msg2dbus-farm
systemctl start victory-gui
for n in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    [ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ] && break
done
[ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ]
[ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ]
systemctl is-active --quiet hbl-wireless-worker
systemctl is-active --quiet victory-gui
systemctl is-active --quiet msg2dbus-farm
grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status"
grep -q 'on=0 ' "$d/diagnostics"
printf 'continuous-swipe-page-ready-default-off\\n' > "$u/result"
trap - 0 1 2 15
cat "$u/result"
'''.replace('@CHECKS@',checks)).encode('utf-8')
    files['update.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    UPDATE.mkdir(exist_ok=True)
    for name,data in files.items(): (UPDATE/name).write_bytes(data)
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','--noprofile','--norc','-n',str(UPDATE/'apply.sh')],check=True,timeout=10)
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            entry=tarfile.TarInfo(name); entry.mode=0o600; entry.size=len(data); entry.mtime=0
            archive.addfile(entry,io.BytesIO(data))
    packed=gzip.compress(raw.getvalue(),mtime=0)
    with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as archive:
        assert {m.name for m in archive}==set(files)
        for m in archive:
            assert m.isfile() and archive.extractfile(m).read()==files[m.name]
    (UPDATE/'update.tar.gz').write_bytes(packed)
    report={'sha256':sha(packed),'bytes':len(packed),'files':{n:sha(d) for n,d in files.items()},
            'previousFiles':old['files'],'newFiles':new['files'],'farmPayloadUnchanged':True,
            'agentFlashTrials':0,'cameraShotsTriggered':0,'uiTests':ui,'installed':False}
    (UPDATE/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:report[k] for k in ('sha256','bytes','farmPayloadUnchanged','installed')}

def stage(session,update=UPDATE,remote=REMOTE):
    if update.parent!=OUT or remote not in (REMOTE,'/tmp/hbl-wireless-flash/u2','/tmp/hbl-wireless-flash/fast1','/tmp/hbl-wireless-flash/minimal1'):
        raise RuntimeError('Unknown owned update location')
    report=json.loads((update/'manifest.json').read_text(encoding='utf-8'))
    payload=(update/'update.tar.gz').read_bytes()
    if sha(payload)!=report['sha256']: raise RuntimeError('Update changed')
    session.command('create-update-stage','test ! -e '+remote+' && mkdir -m 700 '+remote)
    for i,start in enumerate(range(0,len(DECODER),90)):
        session.command('update-decoder-'+str(i),'printf %s '+shlex.quote(DECODER[start:start+90])+(' >' if i==0 else ' >>')+remote+'/d')
    encoded=base64.b64encode(payload).decode('ascii')
    parts=[encoded[i:i+160] for i in range(0,len(encoded),160)]
    for i,part in enumerate(parts):
        session.command('update-part-'+str(i),'printf %s '+shlex.quote(part)+(' >' if i==0 else ' >>')+remote+'/p')
        if (i+1)%100==0: print('update chunks',i+1,'/',len(parts),flush=True)
    r=session.command('decode-update','u='+remote+';printf \'%b\' "$(awk -f "$u/d" "$u/p")" >"$u/update.tar.gz";sha256sum "$u/update.tar.gz"',timeout_ms=45000)
    if r['output'].split()[0]!=report['sha256']: raise RuntimeError('Update upload mismatch')
    r=session.command('extract-update','cd '+remote+' && tar xzf update.tar.gz && sha256sum -c update.sha256 >/dev/null && printf update-verified')
    if r['output']!='update-verified': raise RuntimeError('Update members mismatch')
    print(json.dumps({'uploaded':True,'chunks':len(parts),'bytes':len(payload)}),flush=True)

def finish(session,result,health,values,qml):
    from datetime import datetime,timezone
    if session.failed or not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in session.entries):
        raise RuntimeError('Incomplete command evidence')
    if 'continuous-swipe-page-ready-default-off\n' not in result['output'] or 'qt-receiver-check=3 hardware-requests=0' not in result['output']:
        raise RuntimeError('Update did not finish')
    if 'ui-loaded-worker-default-off\n' not in health['output'] or 'stage=ready error=0 ' not in health['output'] or ' observe=1 output=1 ' not in health['output']:
        raise RuntimeError('Updated chain not ready')
    if qml['output'].strip()!='0': raise RuntimeError('QML errors')
    state={k:int(v) for k,v in (part.split('=',1) for part in values['output'].split())}
    if state.get('on')!=0 or state.get('sent')!=0 or state.get('event')!=1 or state.get('fail')!=0:
        raise RuntimeError('Initial update state unexpected')
    path=OUT/'installation.json'; backup=UPDATE/'previous-installation.json'
    if backup.exists(): raise RuntimeError('Already recorded')
    old=path.read_bytes(); backup.write_bytes(old)
    installed=json.loads(old)
    package=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    report=json.loads((UPDATE/'manifest.json').read_text(encoding='utf-8'))
    installed['files']=package['files']; installed['packageSha256']=package['packageSha256']
    installed['observedAt']=datetime.now(timezone.utc).isoformat()
    installed['kind']='resident-mechanical-fpga-gms1-continuous-control-screen-page'
    installed['workerState']=state; installed['observerHealth']=health
    installed['userRetestPending']=True
    installed['priorUserObservation']='用户反馈原七项均能触发；原单次准备流程操作繁琐。'
    installed['linuxUpdate']={'installed':True,'archiveSha256':report['sha256'],
        'evidence':str(session.output.relative_to(HERE)),'requests':sum(e['submitted'] for e in session.entries),
        'allHandlesClosed':True,'result':result,'health':health,'qmlErrorCount':0,'targetQtPageCompilation':True,
        'newPage':'拍摄参数页右滑第二页，左滑或按钮返回',
        'automaticMode':'保持开启，每个匹配普通请求最多一次；修改信号和延迟保持开启',
        'farmWrites':0,'afWrites':0,'cameraShotsTriggered':0,'agentFlashTrials':0}
    text=json.dumps(installed,ensure_ascii=False,indent=2)+'\n'
    path.write_text(text,encoding='utf-8'); (HERE/'build/installation.json').write_text(text,encoding='utf-8')
    report['installed']=True; report['installation']=installed['linuxUpdate']
    (UPDATE/'installation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    doc=HERE/'MECHANICAL_SYNC_TRIAL.md'; text=doc.read_text(encoding='utf-8')
    start=text.index('当前状态：'); end=text.index('\n\n',start)
    text=text[:start]+'当前状态：连续引闪与拍摄参数页右滑第二页已临时更新到仍在运行的 X1D。机内 Qt 页面编译检查、接收程序检查、三个服务运行及当前 GUI 日志检查均通过。没有重启相机，没有改动 FARM、FPGA 或 AF。更新后默认关闭，用户只需开启一次；新的连续拍摄与实机滑屏体验等待用户复测。此前用户反馈原七项均能触发，不代表已测得物理时序。'+text[end:]
    text=text.replace('## 连续引闪与第二页更新（待装入）','## 连续引闪与第二页更新（已装入）')
    text=text.replace('机内实际加载验证待本轮装入后执行。','本轮机内实际加载及四份 QML 的编译检查已通过，当前 GUI 日志未发现所检查的语法、引用或类型错误。')
    doc.write_text(text,encoding='utf-8')
    return installed['linuxUpdate']

if __name__=='__main__': print(make())
