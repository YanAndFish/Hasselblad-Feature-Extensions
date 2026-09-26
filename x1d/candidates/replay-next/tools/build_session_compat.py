"""将主任务实机采用的安装修正固化为独立兼容包，不修改旧包或操作设备。"""
from pathlib import Path
import gzip
import hashlib
import io
import json
import tarfile

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
OUT=HERE/'releases/session-compat-r2'
MAP_CHECK='index($0,"(deleted)") && !($2=="rw-s" && NF==7 && $7=="(deleted)" && ($6=="/dev/zero" || (index($6,"/tmp/weston-shared-")==1 && substr($6,20)~/^[A-Za-z0-9]+$/))) {bad=1} END {exit bad}'

UPLOAD=r'''    def upload(self,progress=None):
        if self.staged or self.decodeSent:raise RuntimeError('Upload already sent')
        self.send('replay-create',f'umask 077;test ! -e {REMOTE} && test ! -L {REMOTE} && mkdir -m 700 {REMOTE}')
        for name,body in [('d.awk',DECODER),('decode.sh',HELPER)]:
            for i,start in enumerate(range(0,len(body),70)):
                self.send(name+'-'+str(i),'printf %s '+shlex.quote(body[start:start+70])+(' >' if i==0 else ' >>')+REMOTE+'/'+name)
        got=self.send('helper-hash','sha256sum '+REMOTE+'/decode.sh')
        if got.split()[:1]!=[hashlib.sha256(HELPER.encode()).hexdigest()]:
            self.stopped=True;raise RuntimeError('Helper differs; no upload')
        encoded=base64.b64encode(self.data).decode('ascii');parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
        for i,part in enumerate(parts):
            self.send('replay-chunk-'+str(i),'printf %s '+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/p64')
            if progress and (i+1)%100==0:progress(i+1,len(parts))
        self.decodeSent=True
        self.send('replay-decode',f'r={REMOTE};(sh "$r/decode.sh" >"$r/decode.log" 2>&1) </dev/null >/dev/null 2>&1 &')
        return {'decodeDispatched':True,'chunks':len(parts)}
    def finish_upload(self):
        if not self.decodeSent or self.staged:raise RuntimeError('No pending upload')
        out=self.send('replay-decode-result',f'r={REMOTE};if test -f "$r/decode.exit";then cat "$r/decode.exit";cat "$r/decode.sha";else printf pending;fi')
        if out=='pending':return False
        if out.split()[:2]!=['0',self.report['packageSha256']]:
            self.stopped=True;raise RuntimeError('Decode failed or archive differs; extraction refused')
        out=self.send('replay-extract',f'cd {REMOTE} && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && printf replay-package-verified')
        if out!='replay-package-verified':
            self.stopped=True;raise RuntimeError('Extraction not verified')
        self.staged=True
        return True
'''


def sha(data):return hashlib.sha256(data).hexdigest()


def run():
    original=(HERE/'artifacts/session-package/session.tar.gz').read_bytes()
    assert sha(original)=='4ff2a1981ecf52546b0f743ea6eb6622a8aceac8db968c03262496a44c439a78'
    with tarfile.open(fileobj=io.BytesIO(original),mode='r:gz') as archive:
        members=archive.getmembers()
        assert len(members)==14 and all(m.isfile() and m.mode==0o700 for m in members)
        files={m.name:archive.extractfile(m).read() for m in members}
    previous=dict(files)
    head,tail=files['common.sh'].decode().split('baseline_check() {',1)
    assert tail.count('[A-Za-z0-9_.\\/-]')==1
    common=head+'baseline_check() {'+tail.replace('[A-Za-z0-9_.\\/-]','[A-Za-z0-9_.+\\/-]',1)
    old='! grep -q \'(deleted)\' "/proc/$p/maps"'
    assert common.count(old)==1
    common=common.replace(old,"awk '"+MAP_CHECK+"' \"/proc/$p/maps\"",1)
    files['common.sh']=common.encode()
    assert sha(files['common.sh'])=='f3532bf3b3a0194c60b96c5b1681fd72009a848d73f3f4ad8a1ffd98b2dcf26a'
    files['manifest.sha256']=''.join(sha(value)+'  '+name+'\n' for name,value in sorted(files.items()) if name!='manifest.sha256').encode()
    changed=[name for name in files if files[name]!=previous[name]]
    assert sorted(changed)==['common.sh','manifest.sha256']
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,value in sorted(files.items()):
            m=tarfile.TarInfo(name);m.size=len(value);m.mode=0o700;m.uid=m.gid=m.mtime=0
            archive.addfile(m,io.BytesIO(value))
    data=gzip.compress(raw.getvalue(),mtime=0)
    assert sha(data)=='cd11f9988b86d5018ea02f92819b34a1b7e0568b234f696f2e7cf29f63162108'
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'session.tar.gz').write_bytes(data)
    for name in ('common.sh','manifest.sha256'): (OUT/name).write_bytes(files[name])
    source=HERE/'tools/transfer_session.py'
    code=source.read_text(encoding='utf-8')
    code=code.replace("OUT=HERE/'artifacts/session-package'","OUT=Path(__file__).resolve().parent",1)
    start=code.index('    def upload(');end=code.index('    def dispatch(',start)
    code=code[:start]+UPLOAD+code[end:]
    helper=';'.join(['set -eu','r=/tmp/hbl-x1d-rp',
        '''trap 'c=$?;echo "$c" >"$r/decode.next";mv "$r/decode.next" "$r/decode.exit"' 0''',
        'test ! -e "$r/session.tar.gz"',
        '''printf '%b' "$(/usr/bin/od -v -c "$r/p64" | /bin/sed 's/^[0-7]* *//' | awk -f "$r/d.awk")" >"$r/session.tar.gz"''',
        'sha256sum "$r/session.tar.gz" >"$r/sha.next"','mv "$r/sha.next" "$r/decode.sha"'])
    code=code.replace('\nclass Transfer:', '\nHELPER='+repr(helper)+'\n\nclass Transfer:',1)
    (OUT/'transfer.py').write_text(code,encoding='utf-8',newline='\n')
    # 不导入设备会话代码；仅复制已完成的记录作为历史来源。
    evidence=ROOT/'x1d/combined-runtime/build/sessions/replay-only-install-20260912T164641312762Z/installation.json'
    ev=evidence.read_bytes();record=json.loads(ev)
    assert record['completed'] and record['allHandlesClosed'] and record['packageSha256']==sha(data)
    assert record['uiResult']['exit_code']==record['enableResult']['exit_code']==0
    (OUT/'installation-evidence.json').write_bytes(ev)
    report={'schemaVersion':1,'firmwareSource':'X1D-50c 1.25.0','packageReadyForDelegatedLoad':False,
        'release':'session-compat-r2','packageSha256':sha(data),'packageBytes':len(data),
        'files':{name:sha(value) for name,value in sorted(files.items())},'baseArchiveSha256':sha(original),
        'changedTargetFiles':sorted(changed),'baselineChecks':74,'remoteRoot':'/tmp/hbl-x1d-rp',
        'transferChunks':(4*((len(data)+2)//3)+175)//176,'transferSha256':sha(code.encode()),
        'matchingFileSetLoadedByMain':True,'fullArchiveTransferOnTargetValidated':False,
        'targetFunctionalValidated':False,'targetLatencyValidated':False,'cameraAccessByThisTask':False,
        'installationEvidenceSha256':sha(ev),'installationEvidenceSource':evidence.relative_to(ROOT).as_posix(),
        'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),source]}}
    (OUT/'package.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'built':True,'archiveSha256':sha(data),'bytes':len(data),'cameraAccess':False}))


if __name__=='__main__':run()
