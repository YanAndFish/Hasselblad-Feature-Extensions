"""只读核对启动修复，不重启或请求相机功能。"""
from pathlib import Path
import json,hashlib,sys,tarfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'x1d/patch-distribution'),str(ROOT/'x1d/tools')]
from usb_transport import Channel
def main():
    out=ROOT/'x1d/patch-distribution/build/startup-repair-20260923-002840'
    with tarfile.open(out/'x1d-authorized-candidate.tgz') as t:
        expected=hashlib.sha256(t.extractfile('files/manifest.sha256').read()).hexdigest()
    c=Channel();r={}
    with c.session():
        for key,cmd in [
          ('boot','cat /proc/sys/kernel/random/boot_id'),
          ('manifest','sha256sum /opt/hbl-af-only-v1/manifest.sha256'),
          ('files','cd /opt/hbl-af-only-v1 && sha256sum -c manifest.sha256 >/dev/null 2>&1;echo $?'),
          ('ready','cat /run/hbl-four-module/boot.ready 2>/dev/null;true'),
          ('failed','cat /run/hbl-four-module/boot-failed 2>/dev/null;true'),
          ('loader','cat /run/hbl-four-module/boot-loader.status 2>/dev/null;true'),
          ('services','systemctl is-active victory-gui msg2dbus-farm configstore jpeg-daemon bodystate-daemon;true'),
          ('root',"awk '$2==\"/\"{v=$4}END{print v}' /proc/mounts"),
          ('backup','ls -A /opt/hbl-authorized-backup 2>/dev/null;true')]:r[key]=c.command(cmd)
    r['bootHash']=hashlib.sha256(r.pop('boot').encode()).hexdigest()
    prior=out/'pre-reboot.json'
    r['newBoot']=prior.exists() and r['bootHash']!=json.loads(prior.read_text())['bootHash']
    r['passed']=r['newBoot'] and r['manifest'].split()[0]==expected and r['files']=='0' and r['ready']=='ready' and not r['failed'] and r['loader'].startswith('state=ready ') and r['services'].splitlines()==['active']*5 and 'ro' in r['root'].split(',') and r['backup'] in ('','boot-id')
    (out/'cold-boot-validation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
if __name__=='__main__':main()
