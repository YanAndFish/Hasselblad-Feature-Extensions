"""原厂 GUI 已恢复、尚未进行 RAM 写入时，复用校验通过的文件并只上传 UI 差量。"""
from pathlib import Path
from datetime import datetime, timezone
import base64
import gzip
import hashlib
import io
import json
import shlex
import sys
import tarfile
import time
import build_package
import transfer

OLD=transfer.HERE/'build/package/24380db321141523/package.json'
PREVIOUS='/tmp/hbl-x1d-before-ui-fix'
REMOTE=transfer.REMOTE

def members(path,digest):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('fixed archive')
    result={}
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            build_package.safe(member.name)
            if member.isdir():continue
            if not member.isfile() or member.name in result:raise ValueError('archive members')
            result[member.name]=archive.extractfile(member).read()
    return result

def inputs():
    new,_=build_package.verify();old=json.loads(OLD.read_text(encoding='utf-8'))
    before=members(transfer.ROOT/old['archive'],old['packageSha256'])
    after=members(transfer.ROOT/new['archive'],new['packageSha256'])
    if before.keys()!=after.keys() or old['mainSha256']!=new['mainSha256']:raise ValueError('only existing UI resource replacement allowed')
    changed={name for name in before if before[name]!=after[name]}
    if changed!={'combined-ui.rcc','manifest.sha256'}:raise ValueError('UI-only delta required: '+repr(changed))
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(changed):
            member=tarfile.TarInfo(name);member.size=len(after[name]);member.mode=0o600;member.uid=member.gid=0;member.mtime=0
            archive.addfile(member,io.BytesIO(after[name]))
    delta=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0)
    proof={'oldPackageSha256':old['packageSha256'],'packageSha256':new['packageSha256'],
           'oldManifestSha256':hashlib.sha256(before['manifest.sha256']).hexdigest(),
           'newManifestSha256':hashlib.sha256(after['manifest.sha256']).hexdigest(),
           'deltaSha256':hashlib.sha256(delta).hexdigest(),'bytes':len(delta),'changed':sorted(changed)}
    return proof,delta

def apply_script(proof):
    return '''#!/bin/sh
set -eu
umask 077
r=/tmp/hbl-x1d-combined
q=/tmp/hbl-x1d-before-ui-fix
u=$r/ui-delta
test ! -e "$q"
test ! -L "$q"
test ! -L "$r"
test "$(stat -c %u:%a "$r")" = 0:700
test "$(cat "$r/install-state/owner")" = hbl-combined-v1
test -f "$r/install-state/linux-restored.done"
test ! -e "$r/install-state/ram.started"
test ! -L "$r/install-state/ram.started"
test ! -e "$r/phases/observer.sent"
test ! -e /tmp/hbl-wireless-flash/formal-state/radio-mutated
test ! -e /run/systemd/system/victory-gui.service.d/90-hbl-combined.conf
test ! -e /run/systemd/system/msg2dbus-farm.service.d/90-hbl-combined.conf
systemctl is-active --quiet victory-gui msg2dbus-farm
test "$(sha256sum "$r/manifest.sha256" | cut -d' ' -f1)" = @OLD_MANIFEST@
cd "$r"
sha256sum -c manifest.sha256 >/dev/null
test ! -e "$u/delta.tar.gz"
printf '%b' "$(/usr/bin/od -v -c "$u/delta64" | /bin/sed 's/^[0-7]* *//' | awk -f "$r/d.awk")" > "$u/delta.tar.gz"
test "$(sha256sum "$u/delta.tar.gz" | cut -d' ' -f1)" = @DELTA@
for directory in /tmp/hbl-wireless-flash /tmp/hbl-af-settings;do
    test ! -L "$directory"
    test "$(stat -c %u:%a "$directory")" = 0:700
done
# 原 GUI 已恢复且 RAM 未写入；整份旧事务保留，新的窗口稍后由新 UI 阶段创建。
mv "$r" "$q"
mv /tmp/hbl-wireless-flash "$q/previous-flash-runtime"
mv /tmp/hbl-af-settings "$q/previous-af-runtime"
mkdir -m 700 "$r" "$r/phases"
while read -r digest file;do
    mkdir -p "$(dirname "$r/$file")"
    cp "$q/$file" "$r/$file"
done < "$q/manifest.sha256"
cd "$r"
tar xzf "$q/ui-delta/delta.tar.gz"
test "$(sha256sum manifest.sha256 | cut -d' ' -f1)" = @NEW_MANIFEST@
sha256sum -c manifest.sha256 >/dev/null
sh -n run.sh
printf 'combined-ui-delta-staged\\n'
'''.replace('@OLD_MANIFEST@',proof['oldManifestSha256']).replace('@NEW_MANIFEST@',proof['newManifestSha256']).replace('@DELTA@',proof['deltaSha256'])

def stage():
    proof,delta=inputs();body=apply_script(proof)
    session=transfer.Session('stage-ui-delta')
    (session.directory/'apply.sh').write_text(body,encoding='utf-8',newline='\n')
    (session.directory/'delta.tar.gz').write_bytes(delta)
    state={**proof,'staged':False,'servicesRestarted':False,'farmRequests':0,'shots':0,'flashTrials':0,
           'applySha256':hashlib.sha256(body.encode()).hexdigest(),'previousRemote':PREVIOUS}
    try:
        session.command('new-delta-stage','r='+REMOTE+';test ! -e "$r/ui-delta" && test ! -L "$r/ui-delta" && mkdir -m 700 "$r/ui-delta"')
        for name,data in (('script64',body.encode()),('delta64',delta)):
            encoded=base64.b64encode(data).decode('ascii')
            for index,start in enumerate(range(0,len(encoded),160)):
                session.command(name+'-'+str(index),'printf %s '+shlex.quote(encoded[start:start+160])+(' >' if index==0 else ' >>')+REMOTE+'/ui-delta/'+name)
                if index and index%100==0:print(json.dumps({'stage':name,'chunks':index}),flush=True)
        session.command('decode-delta-helper','r='+REMOTE+';u=$r/ui-delta;printf \'%b\' "$(awk -f "$r/d.awk" "$u/script64")" >"$u/apply.sh"')
        result=session.command('verify-delta-helper','sha256sum '+REMOTE+'/ui-delta/apply.sh')
        if result['output'].split()[0]!=state['applySha256']:raise RuntimeError('helper transfer mismatch')
        # helper 移走整个旧 root，因此退出记录始终写在固定保留目录。
        session.command('apply-once','r='+REMOTE+';u=$r/ui-delta;umask 077;set -C;: >"$u/sent" && (sh "$u/apply.sh" >"$u/log" 2>&1;echo $? >/tmp/hbl-ui-delta.exit) </dev/null >/dev/null 2>&1 &')
        for index in range(90):
            time.sleep(1)
            result=session.command('delta-observe-'+str(index),'q='+PREVIOUS+';if test -f /tmp/hbl-ui-delta.exit;then cat /tmp/hbl-ui-delta.exit;tail -n 1 "$q/ui-delta/log";else printf pending;fi')
            if result['output']!='pending':break
        else:raise RuntimeError('UI delta outcome unknown; no repeat')
        state['outcome']=result['output']
        if result['output'].splitlines()!=['0','combined-ui-delta-staged']:raise RuntimeError('UI delta failed; preserve exact stage')
        state['staged']=True
    finally:
        state.update(session.summary())
        (session.directory/'stage.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(state,ensure_ascii=True),flush=True)

if __name__=='__main__':
    if sys.argv[1:]==['--stage-ui-fix']:stage()
    elif not sys.argv[1:]:
        proof,_=inputs();print(json.dumps({**proof,'hardwareRequests':0}))
    else:raise SystemExit('No action')
