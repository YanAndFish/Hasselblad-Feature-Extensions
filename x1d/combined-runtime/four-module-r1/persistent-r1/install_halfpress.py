"""安装已校验临时包；不重启、不触发拍摄。"""
from pathlib import Path
import sys,json,time,hashlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;O=P/'build/halfpress-ui'
sys.path.insert(0,str(P.parent));import session
p=json.loads((O/'package.json').read_text());stage=json.loads((O/'staging.json').read_text())
assert stage['result']['packageSha256']==p['packageSha256']
assert hashlib.sha256((O/'install.tgz').read_bytes()).hexdigest()==p['packageSha256']
s=session.Session('halfpress-install');remote='/tmp/hbl-halfpress-b2'
r=s.command('archive','sha256sum '+remote+'/combined.tar.gz')
assert r['output'].split()[0]==p['packageSha256']
s.command('install-once','r='+remote+';test ! -e "$r/result" && (sh "$r/repair.sh" >"$r/log" 2>&1;echo $? >"$r/result") </dev/null >/dev/null 2>&1 &')
for i in range(60):
    time.sleep(1)
    result=s.command('result-'+str(i),'r='+remote+';if test -f "$r/result";then cat "$r/result";tail -n 1 "$r/log";else printf pending;fi')['output'].strip()
    if result!='pending':break
assert result.splitlines()==['0','af-production-installed-awaiting-restart'],result
actual=s.command('installed-manifest','sha256sum /opt/hbl-af-only-v1/manifest.sha256')['output'].split()[0]
assert actual==p['newManifest']
r=s.command('verify-files','cd /opt/hbl-af-only-v1 && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null && printf verified')
assert r['output']=='verified'
r=s.command('root-ro',"awk '$2==\"/\" && $3==\"ext4\" && $4~/(^|,)ro(,|$)/ {yes=1} END {if(yes)print \"readonly\";exit !yes}' /proc/mounts")
assert r['output'].strip()=='readonly'
r=s.command('core-services','systemctl is-active victory-gui msg2dbus-farm camera-daemon')
assert r['output'].split()==['active']*3
record=dict(installed=True,rebooted=False,rootReadOnly=True,filesVerified=True,servicesActive=True,newManifest=actual,session=s.summary(),manualAcceptancePending=True)
(O/'installation.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record))
