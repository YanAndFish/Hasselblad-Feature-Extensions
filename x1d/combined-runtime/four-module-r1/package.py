"""固定成功引闪包与本次唯一 GUI 库组成 RAM 包；仅生成本目录文件。"""
from pathlib import Path
import hashlib, io, json, tarfile, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FLASH=ROOT/'x1d/wireless-flash'
OUT=HERE/'build/package'
UI_READY='ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1'
REPLAY_READY='replay-page-ready-resources7-components7-pages2'
def sha(b):return hashlib.sha256(b).hexdigest()
def once(s,a,b):
    if s.count(a)!=1:raise ValueError('integration anchor drift')
    return s.replace(a,b,1)
def build():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    base=FLASH/'build/formal-flash-package/stable-success-20260912T125921Z/session-package.tar.gz'
    data=base.read_bytes()
    if sha(data)!='d7e06ad983915f77c1ffe87893457703f5b8ec6d6e706ff028590536f71feef9':raise ValueError('fixed flash package')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as t:
        files={}
        for m in t.getmembers():
            if not m.isfile() or m.name.startswith('/') or '..' in Path(m.name).parts or m.name in files:raise ValueError('archive member')
            files[m.name]=t.extractfile(m).read()
    for line in files.pop('manifest.sha256').decode().splitlines():
        digest,name=line.split()
        if sha(files[name])!=digest:raise ValueError('source manifest')
    native=json.loads((HERE/'build/native/build.json').read_text())
    rcc=(HERE/'build/combined-ui.rcc').read_bytes();lib=(HERE/'build/native/libhbl-four-module.so').read_bytes()
    if sha(lib)!=native['librarySha256'] or sha(rcc)!=native['rccSha256']:raise ValueError('native identity')
    files['libhbl-formal.so']=lib;files['formal-ui.rcc']=rcc
    correction=json.loads((HERE/'mechanical-start-hold/correction.json').read_text())
    observer=(HERE/'mechanical-start-hold/build/formal-flash-program/libhbl-formal-observer.so').read_bytes()
    if not correction['compiled'] or correction['sourceId']!=2 or sha(observer)!=correction['observerSha256']:
        raise ValueError('mechanical correction identity')
    files['libhbl-formal-observer.so']=observer
    install=files['formal-install.sh'].decode()
    anchor='    grep -q \'/tmp/hbl-wireless-flash/libhbl-formal.so\' "/proc/$p/maps" || return 1'
    install=once(install,anchor,anchor+'\n    [ "$(cat /run/hbl-four-module/ui.status)" = "'+UI_READY+' pid=$p" ] || return 1\n    [ "$(cat /run/hbl-four-module/replay.status)" = "'+REPLAY_READY+' pid=$p" ] || return 1')
    install=once(install,'for n in 1 2 3 4 5 6 7 8 9 10; do gui_ready 2>/dev/null && break; sleep 1; done','n=0; while [ "$n" -lt 100 ]; do gui_ready 2>/dev/null && break; n=$((n+1)); sleep 1; done')
    files['formal-install.sh']=install.encode()
    files['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    bundle={'flash/'+n:b for n,b in files.items()}
    bundle['runtime/combined-ui.rcc']=rcc
    bundle['run.sh']=b'''#!/bin/sh
set -eu
umask 077
r=/tmp/hbl-four-module-stage
d=/tmp/hbl-wireless-flash
u=/run/hbl-four-module
[ "$#" = 1 ] && [ "$1" = bootstrap ] || exit 59
[ "$(id -u)" = 0 ] || exit 60
[ -d "$r" ] && [ ! -L "$r" ] && [ "$(stat -c '%u:%a' "$r")" = 0:700 ] || exit 60
cd "$r"
sha256sum -c manifest.sha256 >/dev/null
[ ! -e "$d" ] && [ ! -L "$d" ] && [ ! -e "$u" ] && [ ! -L "$u" ] || exit 61
mkdir -m 700 "$d" "$u"
cp -R flash/. "$d/"
cp runtime/combined-ui.rcc "$u/combined-ui.rcc"
chmod 600 "$u/combined-ui.rcc"
cd "$d"
sha256sum -c manifest.sha256 >/dev/null
cmp formal-ui.rcc "$u/combined-ui.rcc"
printf four-module-bootstrap-verified
'''
    bundle['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(bundle.items())).encode()
    OUT.mkdir(parents=True,exist_ok=True)
    for n,b in bundle.items():
        p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as t:
        for n,b in sorted(bundle.items()):
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o700 if n.endswith('.sh') or n.endswith('-check') or n.endswith('-probe') else 0o600
            t.addfile(m,io.BytesIO(b))
    archive=stream.getvalue();(HERE/'build/combined.tar.gz').write_bytes(archive)
    report={'packageSha256':sha(archive),'bytes':len(archive),'files':{n:sha(b) for n,b in bundle.items()},'preservesExistingAF':True,'temporaryOnly':True,'hardwareRequests':0}
    (HERE/'build/package.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':print(json.dumps(build()))
