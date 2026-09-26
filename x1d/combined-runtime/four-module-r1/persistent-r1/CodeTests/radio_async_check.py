"""真实 sh + 异步驱动替身；不连接相机。"""
from pathlib import Path
import hashlib,json,os,subprocess,time,tarfile
HERE=Path(__file__).resolve().parent;WORK=HERE.parent
SHELL=Path('C:/Program Files/Git/bin/sh.exe');OUT=HERE/'radio-async'/str(time.time_ns())
def posix(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def put(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def run(case,legacy=False):
    root=OUT/case
    for n in ('bin','d/formal-state','sys','original'): (root/n).mkdir(parents=True,exist_ok=True)
    put(root/'d/formal-state/owner','formal-linux-install-v1')
    put(root/'sys/path','/factory-search');put(root/'sys/module','')
    put(root/'original/fw','fixture')
    if legacy:
        with tarfile.open(WORK.parents[3]/'x1d/wireless-flash/build/formal-flash-package/stable-success-20260912T125921Z/session-package.tar.gz') as archive:
            script=archive.extractfile('formal-prepare-radio.sh').read().decode('utf-8')
    else:script=(WORK/'boot-prepare-radio.sh').read_text(encoding='utf-8')
    for a,b in [('/tmp/hbl-wireless-flash',posix(root/'d')),('/sys/module/firmware_class/parameters/path',posix(root/'sys/path')),('/sys/module/brcmfmac/parameters/firmware_path',posix(root/'sys/module')),('/lib/firmware/test/brcm/brcmfmac4356-pcie.bin',posix(root/'original/fw')),('/usr/bin/wl',posix(root/'bin/wl'))]:script=script.replace(a,b)
    put(root/'run.sh',script)
    put(root/'bin/id','#!/bin/sh\necho 0\n');put(root/'bin/stat','#!/bin/sh\necho 0:700\n')
    put(root/'bin/dd','#!/bin/sh\nexit 0\n')
    put(root/'bin/sha256sum','''#!/bin/sh
case "$1" in
-c)exit 0;;
*/original/fw)echo e5eb76a8b333e402b213843e2e93ff771615adcbc05ca7113d04ef0951555159;;
*)echo 86d10d4131bcaa90dd0781545cec918ab10e56fd3d808c2dc85a019ee9edba98;;esac
''')
    put(root/'bin/systemctl','#!/bin/sh\n[ "$1" != show ] || printf "LoadState=loaded\\nActiveState=inactive\\n"\n')
    put(root/'bin/rmmod','#!/bin/sh\necho unload >>"$R/events"\n')
    put(root/'bin/modprobe','#!/bin/sh\necho queued >>"$R/events"\nprintf pending >"$R/pending"\n')
    put(root/'bin/sleep','#!/bin/sh\nexit 0\n')
    put(root/'bin/wl','''#!/bin/sh
echo "wl $*" >>"$R/events"
if [ -f "$R/pending" ];then
    n=$(cat "$R/count" 2>/dev/null || echo 0);n=$((n+1));echo "$n" >"$R/count"
    if [ "$1" = ver ] && [ "$n" -lt 3 ];then exit 1;fi
    [ "$CASE" != never-ready ] || exit 1
    # 实际打开文件发生在 modprobe 返回之后，使用此时的搜索路径。
    if [ "$(cat "$R/sys/path")" = "$R/d" ];then echo 0x5854 >"$R/marker";else echo 0xcb11 >"$R/marker";fi
    rm "$R/pending"
fi
case "$1" in
ver)exit 0;;
band)[ "$CASE" != config-failed ] || exit 1;;
phyreg)
 if [ "$2" = 0 ];then
  if [ "$CASE" = bad-marker ];then echo 0xcb11;else cat "$R/marker";fi
 else
  if [ "$CASE" = busy ];then echo 0x0001;else echo 0x0000;fi
 fi;;
esac
exit 0
''')
    env=dict(os.environ,R=posix(root),CASE=case)
    done=subprocess.run([str(SHELL),'-c','PATH="$1:$PATH";export PATH;exec sh "$2"','check',posix(root/'bin'),posix(root/'run.sh')],env=env,capture_output=True,text=True,timeout=30)
    events=(root/'events').read_text().splitlines()
    assert events.count('queued')==events.count('unload')==1
    assert (root/'sys/path').read_text()=='/factory-search'
    if case=='normal':
        assert done.returncode==0,(done.stdout,done.stderr)
        assert (root/'d/formal-state/radio-prepared').exists()
        assert (root/'d/formal-state/radio-prepare.status').read_text()=='phase=ready exit=0\n'
        assert events.count('wl ver')==3
    else:
        assert done.returncode==86,(case,done.returncode,done.stderr)
        assert not (root/'d/formal-state/radio-prepared').exists()
        if not legacy:
            expected={'never-ready':'wait-driver','config-failed':'configure-band','bad-marker':'verify-marker','busy':'verify-idle'}[case]
            assert (root/'d/formal-state/radio-prepare.status').read_text()==f'phase={expected} exit=86\n'
    if legacy:assert (root/'marker').read_text().strip()=='0xcb11'
    return {'case':case,'exit':done.returncode,'oneDriverLoad':True,'searchRestored':True}
results=[run('legacy-race',True)]+[run(c) for c in ('normal','never-ready','config-failed','bad-marker','busy')]
proof={'passed':True,'hardwareRequests':0,'scriptSha256':hashlib.sha256((WORK/'boot-prepare-radio.sh').read_bytes()).hexdigest(),'cases':results}
(HERE/'radio-async-validation.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(json.dumps(proof))
