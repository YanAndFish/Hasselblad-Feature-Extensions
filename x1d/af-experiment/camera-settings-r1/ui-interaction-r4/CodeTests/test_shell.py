"""GUI scripts with isolated service/health/package substitutes; no device calls."""
import json,subprocess,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
SHELL=Path('C:/Program Files/Git/bin/bash.exe')
def run():
    for name in ('common.sh','apply.sh','restore.sh','run.sh'):
        subprocess.run([str(SHELL),'-n',str(HERE/name)],check=True,capture_output=True)
    output=HERE/'CodeTests/output';output.mkdir(exist_ok=True);checks=[]
    with tempfile.TemporaryDirectory(dir=output) as temp:
        for case in ('normal','new-gui-fails','foreign-dropin'):
            folder=Path(temp)/case;folder.mkdir();(folder/'phases').mkdir()
            base=folder/'90.conf';base.write_text('original AF GUI\n')
            (folder/'95-hbl-af-ui-r4.conf').write_bytes((HERE/'95-hbl-af-ui-r4.conf').read_bytes())
            posix=folder.as_posix();posix='/'+posix[0].lower()+posix[2:]
            model='''set -eu
umask 077
d=FIXTURE
gui=$d/90.conf
delta=$d/95.conf
absent(){ [ ! -e "$1" ] && [ ! -L "$1" ]; }
regular(){ [ -f "$1" ] && [ ! -L "$1" ]; }
private(){ [ -d "$1" ]; }
delta_package(){ return 0; }
base_ready(){ [ ! -f "$delta" ]; }
bus_unchanged(){ return 0; }
pid(){ printf 234; }
stop_gui(){ printf '%s\n' stop-gui >> "$d/calls"; }
clear_ui_status(){ :; }
systemctl(){ printf '%s\n' "$*" >> "$d/calls"; }
wait_ready(){ "$1"; }
r4_ready(){ [ CASE != new-gui-fails ]; }
value(){ if [ -f "$d/foreign" ];then printf '%s %s %s' "$gui" "$delta" "$d/99.conf";elif [ -f "$delta" ];then printf '%s %s' "$gui" "$delta";else printf %s "$gui";fi; }
'''.replace('FIXTURE',posix).replace('CASE',case)
            (folder/'common.sh').write_text(model,encoding='utf-8',newline='\n')
            for name in ('apply.sh','restore.sh','run.sh'):
                s=(HERE/name).read_text(encoding='utf-8').replace('/tmp/hbl-af-ui-r4',posix)
                (folder/name).write_text(s,encoding='utf-8',newline='\n')
            def call(action):return subprocess.run([str(SHELL),str(folder/'run.sh'),action],capture_output=True,text=True,encoding='utf-8',timeout=20)
            result=call('apply')
            if case=='new-gui-fails':
                assert result.returncode==65,(result.returncode,result.stdout,result.stderr)
                assert not (folder/'95.conf').exists() and (folder/'failure-restored').exists()
                checks.append('GUI failure restores only original AF GUI')
            else:
                assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
                assert (folder/'95.conf').read_bytes()==(HERE/'95-hbl-af-ui-r4.conf').read_bytes()
                assert call('apply').returncode==61
                if case=='foreign-dropin':
                    (folder/'foreign').write_text('1');result=call('restore');assert result.returncode==66
                    assert (folder/'95.conf').exists();checks.append('foreign later GUI configuration preserved')
                else:
                    result=call('restore');assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
                    assert not (folder/'95.conf').exists();checks.append('install and explicit restore with duplicate guard')
            assert base.read_text()=='original AF GUI\n'
            calls=(folder/'calls').read_text().splitlines()
            assert all('msg2dbus' not in c and c in ('stop-gui','daemon-reload','start victory-gui') for c in calls)
            checks.append('only GUI service actions '+case)
    report={'passed':True,'checks':checks,'hardwareRequests':0,'healthAndPackageChecksMocked':True,'targetShellTested':False}
    (output/'shell.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':run()
