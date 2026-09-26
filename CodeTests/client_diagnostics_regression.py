"""发行副本的离线失败诊断；不连接相机，不修改原包。"""
from pathlib import Path
import hashlib,json,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    build=ROOT/'x1d/patch-distribution/build'
    out=Path(json.loads((build/'latest-client-diagnostics.json').read_text())['directory'])
    meta=json.loads((out/'native-client-package.json').read_text(encoding='utf-8'))
    original=Path(meta['directory']);tests=out/'diagnostic-cases';tests.mkdir()
    cases=[]
    for mode,wanted,item in [('clean','',''),('missing','FileNotFound','components/installer-native-core.exe'),
            ('changed','Content','components/installer-native-core.exe'),('extra','Unlisted','unexpected.txt'),
            ('missing-signature','FileNotFound','client.sig'),('signature','SignatureSize','client.sig')]:
        d=tests/mode;shutil.copytree(original,d)
        target=d/'components/installer-native-core.exe'
        if mode=='missing':target.unlink()
        if mode=='changed':target.write_bytes(target.read_bytes()+b'test')
        if mode=='extra':(d/'unexpected.txt').write_text('offline test')
        if mode=='missing-signature':(d/'client.sig').unlink()
        if mode=='signature':(d/'client.sig').write_bytes(b'bad')
        r=subprocess.run([str(d/'components/release-guard.exe'),'--client',str(d)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        text=(r.stdout+r.stderr).decode('utf-8')
        assert (r.returncode==0)==(mode=='clean'),(mode,r.returncode,text)
        if wanted:assert 'VERIFY_ERROR='+wanted in text and 'VERIFY_FILE='+item in text,(mode,text)
        cases.append(dict(case=mode,exit=r.returncode,diagnostic=text))
    # Native core still rejects altered clients before any USB operation.
    d=tests/'changed'
    # Use the unmodified signed core, but execute from a tampered directory.
    shutil.copyfile(original/'components/installer-native-core.exe',d/'components/installer-native-core.exe')
    (d/'build-report.json').write_bytes(b'{}')
    r=subprocess.run([str(d/'components/installer-native-core.exe'),'check-package'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    assert r.returncode!=0
    with zipfile.ZipFile(meta['archive']) as z:
        assert z.testzip() is None
        for n in z.namelist():
            if not n.endswith('/'):assert z.read(n)==(original/Path(n).relative_to(original.name)).read_bytes()
    baseline=build/'startup-repair-20260923-002840/x1d-authorized-candidate.tgz'
    assert baseline.read_bytes()==(original/'x1d-authorized-candidate.tgz').read_bytes()
    report=dict(passed=True,hardwareRequests=0,cases=cases,coreRejectsTampering=True,cameraArchiveUnchanged=True,
        zipSha256=hashlib.sha256(Path(meta['archive']).read_bytes()).hexdigest())
    (out/'diagnostic-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(cases),'hardwareRequests':0}))
if __name__=='__main__':main()
