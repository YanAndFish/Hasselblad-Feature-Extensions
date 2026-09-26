"""已有连续引闪版的 QML 手势修正；只更新界面资源并重载 GUI。"""
import gzip
import io
import json
import subprocess
import tarfile
from mechanical_continuous_update import HERE,OUT,sha,stage as stage_common

UPDATE=OUT/'swipe-update'
REMOTE='/tmp/hbl-wireless-flash/u2'

def make():
    old=json.loads((OUT/'installation.json').read_text(encoding='utf-8'))
    new=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    ui=json.loads((HERE/'build/mechanical-ui-test/validation.json').read_text(encoding='utf-8'))
    if not old.get('linuxUpdate',{}).get('installed') or not ui.get('shortSwipe140px') or not ui.get('nestedFactorySwipe'):
        raise RuntimeError('Missing installed baseline or nested short-swipe tests')
    for name,digest in ui['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest: raise RuntimeError('UI evidence changed')
    for name in old['files']:
        if name not in ('ui.rcc','manifest.sha256') and old['files'][name]!=new['files'][name]:
            raise RuntimeError('Unexpected non-QML change')
    with tarfile.open(OUT/'session-package.tar.gz','r:gz') as archive:
        files={n:archive.extractfile(n).read() for n in ('ui.rcc','manifest.sha256')}
    files['apply.sh']=('''#!/bin/sh
set -eu
d=/tmp/hbl-wireless-flash
u="$d/u2"
[ -d "$d" ] && [ ! -L "$d" ] && [ -d "$u" ] && [ ! -L "$u" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] || exit 60
[ ! -e "$u/backup" ] || exit 60
cd "$u"
sha256sum -c update.sha256 >/dev/null
[ "$(sha256sum "$d/ui.rcc"|cut -d' ' -f1)" = @OLD_UI@ ]
[ "$(sha256sum "$d/manifest.sha256"|cut -d' ' -f1)" = @OLD_MANIFEST@ ]
cd "$d"
sha256sum -c manifest.sha256 >/dev/null
systemctl is-active --quiet victory-gui
systemctl is-active --quiet hbl-wireless-worker
mkdir -m 700 "$u/backup"
cp -p "$d/ui.rcc" "$d/manifest.sha256" "$u/backup/"
rollback() {
    result=$?
    trap - 0 1 2 15
    systemctl stop victory-gui || true
    for name in ui.rcc manifest.sha256; do cp -p "$u/backup/$name" "$d/$name.rollback" && mv -f "$d/$name.rollback" "$d/$name"; done
    systemctl start victory-gui || true
    printf 'swipe-update-rolled-back\\n' > "$u/result"
    exit "$result"
}
trap rollback 0
trap 'exit 72' 1 2 15
systemctl stop victory-gui
for name in ui.rcc manifest.sha256; do cp "$u/$name" "$d/$name.next" && mv -f "$d/$name.next" "$d/$name"; done
sha256sum -c manifest.sha256 >/dev/null
rm -f "$d/runtime.status"
systemctl start victory-gui
for n in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    [ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ] && break
done
[ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ]
systemctl is-active --quiet victory-gui
systemctl is-active --quiet hbl-wireless-worker
systemctl is-active --quiet msg2dbus-farm
printf 'short-swipe-page-ready\\n' > "$u/result"
trap - 0 1 2 15
cat "$u/result"
'''.replace('@OLD_UI@',old['files']['ui.rcc']['sha256']).replace('@OLD_MANIFEST@',old['files']['manifest.sha256']['sha256'])).encode('ascii')
    files['update.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    UPDATE.mkdir(exist_ok=True)
    for n,data in files.items(): (UPDATE/n).write_bytes(data)
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','--noprofile','--norc','-n',str(UPDATE/'apply.sh')],check=True,timeout=10)
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for n,data in sorted(files.items()):
            entry=tarfile.TarInfo(n); entry.mode=0o600; entry.size=len(data); entry.mtime=0
            archive.addfile(entry,io.BytesIO(data))
    packed=gzip.compress(raw.getvalue(),mtime=0)
    with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as archive:
        for m in archive: assert m.isfile() and archive.extractfile(m).read()==files[m.name]
    (UPDATE/'update.tar.gz').write_bytes(packed)
    report={'sha256':sha(packed),'bytes':len(packed),'installed':False,'uiTests':ui,'previousFiles':old['files'],'newFiles':new['files']}
    (UPDATE/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'bytes':len(packed),'sha256':sha(packed),'installed':False}

def stage(session): return stage_common(session,UPDATE,REMOTE)

def finish(session,result,errors):
    from datetime import datetime,timezone
    if session.failed or not all(e['matched'] and e['closed'] and e.get('exit_code')==0 for e in session.entries):
        raise RuntimeError('Incomplete update evidence')
    if result['output']!='short-swipe-page-ready\nui-loaded-worker-default-off\n' or errors['output'].strip()!='0':
        raise RuntimeError('UI update not verified')
    path=OUT/'installation.json'; backup=UPDATE/'previous-installation.json'
    if backup.exists(): raise RuntimeError('Already recorded')
    old=path.read_bytes(); backup.write_bytes(old); installed=json.loads(old)
    package=json.loads((OUT/'package-validation.json').read_text(encoding='utf-8'))
    update=json.loads((UPDATE/'manifest.json').read_text(encoding='utf-8'))
    installed['files']=package['files']; installed['packageSha256']=package['packageSha256']
    installed['observedAt']=datetime.now(timezone.utc).isoformat()
    installed['uiCorrection']={'installed':True,'archiveSha256':update['sha256'],'evidence':str(session.output.relative_to(HERE)),
        'requests':sum(e['submitted'] for e in session.entries),'allHandlesClosed':True,'qmlErrorCount':0,
        'entry':'原闪光灯补偿按钮替换为无线引闪入口，保留补偿数值；点击进入第二页。',
        'gesture':'缩短距离门槛，并移除仅用于界面横移的 Camera.inSession 门控；原弹窗门控保留。',
        'userObservation':'用户确认已有界面，并询问能否拔 USB。',
        'swipePhysicallyVerified':False,'farmWrites':0,'afWrites':0,'cameraShotsTriggered':0,'agentFlashTrials':0}
    text=json.dumps(installed,ensure_ascii=False,indent=2)+'\n'
    path.write_text(text,encoding='utf-8'); (HERE/'build/installation.json').write_text(text,encoding='utf-8')
    update['installed']=True; update['installation']=installed['uiCorrection']
    (UPDATE/'installation.json').write_text(json.dumps(update,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    doc=HERE/'MECHANICAL_SYNC_TRIAL.md'; text=doc.read_text(encoding='utf-8')
    start=text.index('当前状态：'); end=text.index('\n\n',start)
    text=text[:start]+'当前状态：连续引闪与按钮入口已临时装入仍在运行的 X1D。用户反馈首版右滑无效，随后要求把原闪光灯补偿按钮直接替换为无线引闪入口；最新按钮版已装入，用户确认已有界面。当前 GUI 日志未发现所检查的语法、引用或类型错误。全部 USB 请求已完成，句柄关闭；用户可拔线独立使用。没有改动 FARM、FPGA、AF 或原闪光补偿数值，物理同步时序尚未测量。'+text[end:]
    text=text.replace('在显示快门、光圈的拍摄参数页向右滑进入无线引闪第二页，向左滑或点“拍摄参数”返回。','在显示快门、光圈的参数页，点击原闪光灯补偿位置的新“无线引闪”按钮进入第二页，点击“拍摄参数”返回。初版右滑实机未生效；最新版本同时缩短手势门槛并去除拍摄会话对横移的门控，但尚未得到实机滑动成功确认。')
    text+='\n本轮后续按钮修正只替换 QML 资源并重载 GUI；worker 和消息接收服务继续运行。用户最后确认已有界面，允许拔除 USB；此后没有追加硬件请求。\n'
    doc.write_text(text,encoding='utf-8')
    return installed['uiCorrection']

if __name__=='__main__':print(make())
