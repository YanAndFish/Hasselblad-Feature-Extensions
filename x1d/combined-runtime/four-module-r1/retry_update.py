"""已确认 UI 回滚后的固定差量更新；保留失败目录，默认只构建和离线验证。"""
from pathlib import Path
import base64,hashlib,io,json,shlex,subprocess,sys,tarfile,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import session
OUT=HERE/'build/retry-update'
REMOTE='/tmp/hbl-four-module-stage'
def sha(b):return hashlib.sha256(b).hexdigest()
def build():
    p,data=session.verify();old=json.loads((HERE/'build/attempt1/package.json').read_text())
    changed={n:(HERE/'build/package'/n).read_bytes() for n,h in p['files'].items() if old['files'].get(n)!=h}
    assert set(changed)=={'flash/formal-install.sh','flash/libhbl-formal.so','flash/manifest.sha256','manifest.sha256'}
    script='''#!/bin/sh
set -eu
umask 077
r=/tmp/hbl-four-module-stage
d=/tmp/hbl-wireless-flash
u=/run/hbl-four-module
cd "$r"
[ "$(sha256sum manifest.sha256 | cut -d' ' -f1)" = @OLD@ ]
sha256sum -c manifest.sha256 >/dev/null
[ "$(cat "$d/formal-install.status")" = formal-install-failed-original-linux-restored ]
[ "$(cat "$d/formal-restore.status")" = original-linux-services-and-radio-restored ]
[ -f "$d/formal-state/restore-complete" ] && [ ! -e "$d/formal-state/radio-mutated" ] && [ ! -e "$d/formal-state/install-complete" ]
[ ! -e /run/systemd/system/victory-gui.service.d/80-hbl-formal-flash.conf ]
[ ! -e /run/systemd/system/msg2dbus-farm.service.d/80-hbl-formal-flash.conf ]
[ ! -L "$d" ] && [ ! -L "$u" ] && [ -d "$d" ] && [ -d "$u" ]
[ ! -e failed-flash ] && [ ! -L failed-flash ] && [ ! -e failed-runtime ] && [ ! -L failed-runtime ]
for service in victory-gui msg2dbus-farm; do
 systemctl is-active --quiet "$service"
 pid=$(systemctl show -p MainPID "$service" | cut -d= -f2)
 case "$pid" in ''|0|*[!0-9]*) exit 63;; esac
 if grep -q /tmp/hbl-wireless-flash/ "/proc/$pid/maps"; then exit 63; fi
done
cd update
sha256sum -c update.sha256 >/dev/null
cp flash/formal-install.sh flash/libhbl-formal.so flash/manifest.sha256 "$r/flash/"
cp manifest.sha256 "$r/manifest.sha256"
cd "$r"
sha256sum -c manifest.sha256 >/dev/null
mv "$d" "$r/failed-flash"
mv "$u" "$r/failed-runtime"
sh run.sh bootstrap
'''.replace('@OLD@',old['files']['manifest.sha256'])
    changed['apply.sh']=script.encode()
    changed['update.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(changed.items())).encode()
    OUT.mkdir(parents=True,exist_ok=True)
    for n,b in changed.items():
        q=OUT/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as t:
        for n,b in sorted(changed.items()):
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o700 if n.endswith('.sh') else 0o600;t.addfile(m,io.BytesIO(b))
    data=buf.getvalue();(OUT/'update.tar.gz').write_bytes(data)
    report={'sha256':sha(data),'bytes':len(data),'newPackageSha256':p['packageSha256'],'files':{n:sha(b) for n,b in changed.items()}}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report,data
def transfer(s,report,data,pause=time.sleep):
    assert sha(data)==report['sha256']
    s.command('update-fresh','test ! -e '+REMOTE+'/u64 && test ! -e '+REMOTE+'/update && test ! -e '+REMOTE+'/update.tar.gz')
    encoded=base64.b64encode(data).decode()
    parts=[encoded[i:i+172] for i in range(0,len(encoded),172)]
    for i,part in enumerate(parts):
        s.command('update-chunk-'+str(i),"printf '%s\\n' "+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/u64')
        if (i+1)%100==0:print(json.dumps({'updateChunks':i+1,'total':len(parts)}),flush=True)
    s.command('update-decode-once','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/u64")" >"$r/update.tar.gz";sha256sum "$r/update.tar.gz" >"$r/update.sha") </dev/null >/dev/null 2>&1 &')
    for i in range(60):
        pause(1)
        r=s.command('update-observe','r='+REMOTE+';if test -f "$r/update.sha";then cat "$r/update.sha";else printf pending;fi')
        if r['output']!='pending':break
    else:raise RuntimeError('update decoder pending; no repeat')
    if r['output'].split()[0]!=report['sha256']:raise ValueError('update archive mismatch')
    s.command('extract-update','cd '+REMOTE+' && mkdir -m 700 update && tar xzf update.tar.gz -C update && cd update && sha256sum -c update.sha256 >/dev/null && sh -n apply.sh')
def offline():
    report,data=build()
    encoded=base64.b64encode(data).decode()
    (OUT/'u64').write_text('\n'.join(encoded[i:i+172] for i in range(0,len(encoded),172))+'\n',encoding='ascii')
    (OUT/'d.awk').write_text(session.transport.DECODER,encoding='ascii')
    shell='C:/Program Files/Git/bin/sh.exe'
    r=subprocess.run([shell,'-c','printf \'%b\' "$(awk -f d.awk u64)" > decoded.tar.gz'],cwd=OUT,capture_output=True,timeout=30)
    assert r.returncode==0 and sha((OUT/'decoded.tar.gz').read_bytes())==report['sha256']
    assert subprocess.run([shell,'-n',str(OUT/'apply.sh')],capture_output=True).returncode==0
    class Model:
        def command(self,label,command,timeout_ms=15000):
            assert len(command.encode())<=231 and '\n' not in command,(label,len(command))
            return {'output':report['sha256']+' archive' if label=='update-observe' else ''}
    transfer(Model(),report,data,lambda _:None)
    proof={'passed':True,'sha256':report['sha256'],'lineDecoderRoundTrip':True,'allCommandsBounded':True,'hardwareRequests':0}
    (OUT/'validation.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
def live():
    report=json.loads((OUT/'report.json').read_text());proof=json.loads((OUT/'validation.json').read_text());data=(OUT/'update.tar.gz').read_bytes()
    assert proof['passed'] and proof['sha256']==report['sha256'] and sha(data)==report['sha256']
    s=session.Session('retry-update');transfer(s,report,data)
    r=s.command('apply-update-once','sh '+REMOTE+'/update/apply.sh')
    assert r['output']=='four-module-bootstrap-verified',r
    print(json.dumps({'updated':True,'session':s.summary()}))
if __name__=='__main__':
    if sys.argv[1:]==['--apply']:live()
    elif not sys.argv[1:]:print(json.dumps(offline()))
    else:raise SystemExit('unsupported args')
