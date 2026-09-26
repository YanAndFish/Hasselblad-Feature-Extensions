"""运行真实持久文件事务；挂载、服务、权限元数据与健康为替身。"""
from pathlib import Path
import hashlib,io,json,os,re,subprocess,tarfile,time
HERE=Path(__file__).resolve().parents[1]
SHELL='C:/Program Files/Git/bin/sh.exe'
def write(p,t):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t,encoding='utf-8',newline='\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mp(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
    out=HERE/'build/persistence-tests'/str(time.time_ns());out.mkdir(parents=True)
    report=json.loads((HERE/'build/current.json').read_text())
    assert report['packageSha256']=='1e2171827553e3846abe15c5cfe21e75a97a4234cff34ade8cd0ebdbfb7455b6'
    checks=[]
    for mode in ('success-remove','copy-fail','drop-fail','mount-ro-fail','mount-rw-denied','foreign-existing','modified-uninstall'):
        case=out/mode;case.mkdir();payload=case/'payload';payload.mkdir();bin=case/'bin';bin.mkdir();fs=case/'fs';fs.mkdir()
        def adapt(text):
            for p in ('opt','etc','run','proc'):
                text=text.replace('/'+p+'/',mp(fs/p)+'/')
            text=text.replace('/lib/systemd/',mp(fs/'lib/systemd')+'/')
            text=text.replace('parent=/opt','parent='+mp(fs/'opt')).replace('proc=/proc','proc='+mp(fs/'proc'))
            return text
        with tarfile.open(report['archive'],'r:gz') as tf:
            for member in tf.getmembers():
                data=tf.extractfile(member).read()
                if member.name.endswith(('.sh','.conf')):data=adapt(data.decode()).encode()
                (payload/member.name).write_bytes(data)
        write(payload/'health','#!/bin/sh\nprintf "ui-health-ready pid=101 system=4 power=1\\n"\n')
        write(payload/'baseline.sha256',sha(payload/'button.rcc')+'  '+mp(payload/'button.rcc')+'\n')
        members=[p for p in payload.iterdir() if p.name!='manifest.sha256'];assert len(members)==9
        write(payload/'manifest.sha256',''.join(sha(p)+'  '+p.name+'\n' for p in sorted(members)))
        text=adapt((HERE/'persist.sh').read_text(encoding='utf-8'))
        text=re.sub(r'^expected_manifest=.*$', 'expected_manifest='+sha(payload/'manifest.sha256'),text,flags=re.M)
        text=re.sub(r'^rootflags\(\) \{.*?\}$','rootflags() { cat "$CASE/root.flags"; }',text,flags=re.M)
        write(payload/'persist.sh',text)
        write(case/'root.flags','ro,relatime\n');write(fs/'proc/101/environ','')
        (fs/'etc/systemd/system').mkdir(parents=True)
        write(bin/'id','#!/bin/sh\nprintf "0\\n"\n')
        write(bin/'stat','#!/bin/sh\ncase "$2" in %u:%h) printf "0:1\\n";; %u:%a) printf "0:700\\n";; *) exit 1;;esac\n')
        write(bin/'mkdir','#!/bin/sh\nif [ "${1:-}" = -m ];then shift 2;fi\nexec /usr/bin/mkdir "$@"\n')
        write(bin/'chmod','#!/bin/sh\nexit 0\n')
        write(bin/'sync','#!/bin/sh\nexit 0\n')
        write(bin/'df','#!/bin/sh\nprintf "Filesystem blocks used available capacity path\\nroot 20000 1000 19000 5%% /\\n"\n')
        write(bin/'mount','''#!/bin/sh
echo "$*" >> "$CASE/mounts"
case "$2" in
remount,rw) if [ "$MODE" = mount-rw-denied ];then exit 1;fi;echo rw,relatime > "$CASE/root.flags";;
remount,ro) if [ "$MODE" = mount-ro-fail ] && [ ! -e "$CASE/ro-failed" ];then echo 1 > "$CASE/ro-failed";exit 1;fi;echo ro,relatime > "$CASE/root.flags";;
*) exit 1;;esac
''')
        write(bin/'cp','''#!/bin/sh
if [ "$MODE" = copy-fail ];then case "$1" in */button.rcc) exit 1;;esac;fi
exec /usr/bin/cp "$@"
''')
        write(bin/'mv','''#!/bin/sh
if [ "$MODE" = drop-fail ];then case "$1" in */91-hbl-wifi-probe.conf.new) exit 1;;esac;fi
exec /usr/bin/mv "$@"
''')
        write(bin/'systemctl','''#!/bin/sh
case "$1" in
show)
case "$3" in
MainPID) echo MainPID=101;;
FragmentPath) printf 'FragmentPath=%s/fs/lib/systemd/system/%s.service\n' "$CASE" "$4";;
DropInPaths) echo DropInPaths=;;
Environment) echo Environment=;;
esac;;
is-active) exit 0;;
*) echo unexpected > "$CASE/service-mutation";exit 1;;esac
''')
        dest=fs/'opt/hbl-wifi-probe-v1';drop=fs/'etc/systemd/system/victory-gui.service.d/91-hbl-wifi-probe.conf'
        if mode=='foreign-existing':write(dest/'foreign','keep')
        env=dict(os.environ,CASE=mp(case),MODE=mode,TEST_BIN=mp(bin))
        def invoke(action):return subprocess.run([SHELL,'-c','export PATH="$TEST_BIN:$PATH";exec sh "$@"','harness',(payload/'persist.sh').as_posix(),action],env=env,capture_output=True,text=True,timeout=20)
        result=invoke('install')
        assert (case/'root.flags').read_text().startswith('ro'),(mode,result.stdout,result.stderr)
        assert not (case/'service-mutation').exists(),mode
        if mode in ('success-remove','modified-uninstall'):
            assert result.returncode==0 and drop.read_bytes()==(payload/'gui.conf').read_bytes(),(mode,result.stdout,result.stderr)
            assert all((dest/p.name).read_bytes()==p.read_bytes() for p in payload.iterdir()),mode
            status=invoke('status');assert status.returncode==0,(status.stdout,status.stderr)
            if mode=='modified-uninstall':
                write(dest/'button.rcc','foreign-modification');before=(case/'mounts').read_text();result=invoke('remove')
                assert result.returncode!=0 and drop.exists() and (dest/'button.rcc').read_text()=='foreign-modification' and before==(case/'mounts').read_text()
            else:
                result=invoke('remove');assert result.returncode==0 and not dest.exists() and not drop.exists(),(result.stdout,result.stderr)
                assert (case/'root.flags').read_text().startswith('ro')
        elif mode=='foreign-existing':
            assert result.returncode!=0 and not (case/'mounts').exists() and (dest/'foreign').read_text()=='keep'
        else:
            assert result.returncode!=0 and not dest.exists() and not drop.exists(),(mode,result.stdout,result.stderr)
            if mode=='mount-rw-denied':assert (case/'mounts').read_text().splitlines()==['-o remount,rw /']
        checks.append(mode)
    proof={'passed':True,'checks':checks,'sources':{'persist.sh':sha(HERE/'persist.sh')},'packageSha256':report['packageSha256'],'actual':'persist.sh file install/status/remove and rollback logic','mocked':['mount and root mount flags','systemctl','UID/stat/mkdir modes','health','injected copy and rename failures'],'hardwareRequests':0}
    write(HERE/'build/persistence-validation.json',json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks)}))
if __name__=='__main__':main()
