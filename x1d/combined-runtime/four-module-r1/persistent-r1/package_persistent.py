"""生成独立持久包；构建证据与运行资产绑定，不执行设备操作。"""
from pathlib import Path
import hashlib,io,json,re,sys,tarfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=HERE/'build/persistent-package'
def sha(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    transaction=read(HERE/'CodeTests/persistent-transaction-validation.json')
    coordinator=read(HERE/'CodeTests/boot-coordinate-validation.json')
    if not transaction['passed'] or transaction['scriptSha256']!=sha((HERE/'install.sh').read_bytes()):raise RuntimeError('installation transaction evidence')
    if not coordinator['passed']:raise RuntimeError('coordinator evidence')
    for n,h in coordinator['scripts'].items():
        if sha((HERE/n).read_bytes())!=h:raise RuntimeError('coordinator script changed')
    proof=read(HERE/'build/boot-model/validation.json')
    if not proof['passed'] or proof['hardwareRequests'] or proof['cppIndependentLinksMatched']!=3:raise RuntimeError('loader evidence')
    for n,h in proof['sources'].items():
        if sha((HERE/n).read_bytes())!=h:raise RuntimeError('loader evidence changed '+n)
    build=read(HERE/'build/formal-flash-program/client-build.json')
    for n,h in build['sourceHashes'].items():
        if sha((HERE/n).read_bytes())!=h:raise RuntimeError('client source changed '+n)
    gui=read(HERE/'build/native/build.json')
    for n,h in gui['sources'].items():
        if sha((ROOT/n).read_bytes())!=h:raise RuntimeError('GUI source changed '+n)
    base=ROOT/'x1d/wireless-flash/build/formal-flash-package/stable-success-20260912T125921Z/session-package.tar.gz'
    data=base.read_bytes()
    if sha(data)!='d7e06ad983915f77c1ffe87893457703f5b8ec6d6e706ff028590536f71feef9':raise RuntimeError('base source')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as t:
        old={m.name:t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
    for line in old['manifest.sha256'].decode().splitlines():
        h,n=line.split()
        if sha(old[n])!=h:raise RuntimeError('base member')
    runtime={n:b for n,b in old.items() if n in ('formal-prepare-radio.sh','formal-hold.check') or n.startswith('delta/')}
    radio=(HERE/'boot-prepare-radio.sh').read_bytes()
    radio_proof=read(HERE/'CodeTests/radio-async-validation.json')
    if not radio_proof['passed'] or radio_proof['scriptSha256']!=sha(radio):raise RuntimeError('radio async evidence')
    runtime['formal-prepare-radio.sh']=radio
    # wait-r5保留的未调用旧辅助文件；当前协调器不再使用通知等待。
    retired=HERE/'build/wait-revert-r5/persistent-package'
    retired_manifest=read(HERE/'build/wait-revert-r5/persistent-package.json')
    wait_binary=(retired/'runtime/boot-wait').read_bytes()
    if sha(wait_binary)!=retired_manifest['files']['runtime/boot-wait'] or 'boot-wait' in (HERE/'boot-coordinate.sh').read_text(encoding='utf-8'):raise RuntimeError('retired wait helper unexpectedly active')
    runtime['boot-wait']=wait_binary
    batch=read(HERE/'build/batch-model/validation.json')
    adapter=read(HERE/'build/batch-model/adapter-build.json')
    arm=read(HERE/'build/batch-model/adapter-arm-validation.json')
    if not batch['passed'] or not arm['passed'] or not arm.get('originalFarmLengthFilterExecuted') or arm['adapterSha256']!=adapter['sha256']:raise RuntimeError('batch evidence')
    if 'first-upload-included=1' not in batch['model']:raise RuntimeError('missing adapter lifecycle evidence')
    for n,h in dict(batch['sources'],**adapter['sourceHashes']).items():
        if sha((HERE/n).read_bytes())!=h:raise RuntimeError('batch source changed '+n)
    if sha((HERE/'build/batch-model/adapter.bin').read_bytes())!=adapter['sha256']:raise RuntimeError('adapter image changed')
    for n in ('libhbl-formal-observer.so','formal-sync-hook-check','formal-client-check','formal-system-check','formal-netlink-probe','persistent-check'):
        b=(HERE/'build/formal-flash-program'/n).read_bytes()
        if sha(b)!=build['outputs'][n]['sha256']:raise RuntimeError('native output')
        runtime[n]=b
    lib=(HERE/'build/native/libhbl-four-module.so').read_bytes()
    rcc=(HERE/'build/combined-ui.rcc').read_bytes()
    if sha(lib)!=gui['librarySha256'] or sha(rcc)!=gui['rccSha256']:raise RuntimeError('GUI output')
    runtime['libhbl-formal.so']=lib;runtime['formal-ui.rcc']=rcc
    runtime['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(runtime.items())).encode()
    files={'runtime/'+n:b for n,b in runtime.items() if n!='formal-ui.rcc'}
    files['combined-ui.rcc']=rcc
    for n in ('boot-common.sh','boot-farm.sh','boot-gui.sh','boot-coordinate.sh','install.sh'):
        files[n]=(HERE/n).read_bytes().replace(b'\r\n',b'\n')
    files['gui.conf']=b'[Service]\nExecStart=\nExecStart=/bin/sh /opt/hbl-four-module-v1/boot-gui.sh\nRestart=no\nUMask=0077\n'
    files['farm.conf']=b'[Service]\nExecStart=\nExecStart=/bin/sh /opt/hbl-four-module-v1/boot-farm.sh\nRestart=no\nUMask=0077\n'
    baseline=ROOT/'.research-cache/x1d-1.25.0/baseline'
    bound=['usr/bin/victory-gui','usr/bin/msg2dbus','usr/lib/libappscommon.so.1.0.0',
           'lib/systemd/system/victory-gui.service','lib/systemd/system/msg2dbus-farm.service','lib/systemd/system/media-data.mount',
           'lib/firmware/test/brcm/brcmfmac4356-pcie.bin']
    baseline_rows=[]
    for n in bound:
        if (baseline/n).is_file():digest=sha((baseline/n).read_bytes())
        else:
            text=old['formal-install.sh'].decode()+old['formal-prepare-radio.sh'].decode()
            pattern=r'sha256sum /'+re.escape(n)+r'[^\n]+ = ([0-9a-f]{64}) '
            found=re.findall(pattern,text)
            if len(found)!=1:raise RuntimeError('missing bound baseline identity '+n)
            digest=found[0]
        baseline_rows.append(digest+'  /'+n+'\n')
    files['baseline.sha256']=''.join(baseline_rows).encode()
    files['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    OUT.mkdir(parents=True,exist_ok=True)
    duplicate=OUT/'runtime/formal-ui.rcc'
    if duplicate.is_file() and duplicate.read_bytes()==rcc:duplicate.unlink()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as t:
        for n,b in sorted(files.items()):
            p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o600;t.addfile(m,io.BytesIO(b))
    archive=stream.getvalue();(HERE/'build/persistent-package.tgz').write_bytes(archive)
    report={'archiveSha256':sha(archive),'archiveBytes':len(archive),'manifestSha256':sha(files['manifest.sha256']),
            'files':{n:sha(b) for n,b in files.items()},'installed':False,'hardwareRequests':0,'coldBootVerified':False}
    (HERE/'build/persistent-package.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='files'}))
if __name__=='__main__':main()
