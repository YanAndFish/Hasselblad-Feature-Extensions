"""固定格式化入口修复包；只在全部离线证据与源一致时生成。"""
from pathlib import Path
import gzip,hashlib,importlib.util,io,json,sys,tarfile
sys.dont_write_bytecode=True
def load(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
build=load('card_format_pack_build',Path(__file__).with_name('build.py'))
ROOT=build.ROOT;OUT=build.OUT;HERE=build.FIX;FIX=HERE
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def bound(values,root=ROOT):
    for name,h in values.items():
        p=(root/name).resolve()
        if not p.is_relative_to(ROOT) or build.sha(p)!=h:raise ValueError('bound input changed '+name)
def inputs():
    old=load('card_format_parent_package',build.CANDIDATE/'session/package.py');old_report,old_blob=old.verify()
    resource=read(OUT/'resources/manifest.json');native=read(OUT/'native/build.json')
    qml=read(FIX/'build/qml-validation.json');shell=read(OUT/'install-validation.json')
    if not native['compiled'] or not qml['passed'] or not shell['passed'] or qml['mockFormatCalls']!=0:raise ValueError('validation incomplete')
    for v in (resource,native,shell):bound(v['sources'])
    bound(qml['sources'],FIX)
    for case in qml['cases']:
        if build.sha(FIX/case['file'])!=case['sha256']:raise ValueError('qml case changed')
    if build.sha(OUT/'resources/manifest.json')!=native['resourcesManifestSha256']:raise ValueError('native binding')
    for name,meta in native['outputs'].items():
        if build.sha(OUT/'native'/name)!=meta['sha256']:raise ValueError('native payload')
    if build.sha(OUT/'resources/ui-resident.rcc')!=resource['rccSha256']:raise ValueError('resource payload')
    return old_report,old_blob,resource,native,qml,shell
def make():
    old_report,old_blob,resource,native,qml,shell=inputs()
    files={n:(FIX/'session'/n).read_bytes() for n in ('common.sh','install.sh','restore.sh','run.sh')}
    for n in ('libhbl-ui-resident.so','ui-health'):files[n]=(OUT/'native'/n).read_bytes()
    files['ui-resident.rcc']=(OUT/'resources/ui-resident.rcc').read_bytes()
    with tarfile.open(fileobj=io.BytesIO(old_blob)) as a:files['baseline.sha256']=a.extractfile('baseline.sha256').read()
    files['manifest.sha256']=''.join(digest(v)+'  '+n+'\n' for n,v in sorted(files.items())).encode()
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for n,v in sorted(files.items()):
            info=tarfile.TarInfo(n);info.size=len(v);info.mtime=0;info.mode=0o700 if n.endswith('.sh') or n=='ui-health' else 0o600
            archive.addfile(info,io.BytesIO(v))
    blob=gzip.compress(raw.getvalue(),compresslevel=9,mtime=0)
    directory=OUT/'packages'/digest(blob)[:16];directory.mkdir(parents=True,exist_ok=True);path=directory/'ui-format-r1.tar.gz'
    if path.exists() and path.read_bytes()!=blob:raise ValueError('freeze conflict')
    path.write_bytes(blob)
    proof_paths=[Path(__file__),FIX/'delivery.py',OUT/'resources/manifest.json',OUT/'native/build.json',OUT/'install-validation.json',FIX/'build/qml-validation.json',OUT/'source-binding.json']
    report={'kind':'original-gui-text2-role-fix-r1','archive':path.relative_to(ROOT).as_posix(),'packageSha256':digest(blob),'bytes':len(blob),
        'files':{n:digest(v) for n,v in files.items()},'proofs':{p.relative_to(ROOT).as_posix():build.sha(p) for p in proof_paths},
        'oldPackageSha256':old_report['packageSha256'],'rccSha256':resource['rccSha256'],'resources':resource['resources'],
        'remoteRoot':build.REMOTE,'hardwareRequests':0,'targetValidated':False,'installed':False,
        'change':'SettingsGeneric text2 missing/null values become empty string during model append; other QML bytes unchanged',
        'rollback':'remove only owned 90-hbl-ui-resident.conf and return factory GUI; no bus restart'}
    build.save(directory/'package.json',report);build.save(OUT/'current.json',{'report':(directory/'package.json').relative_to(ROOT).as_posix()})
    return report
def verify():
    inputs();report=read(ROOT/read(OUT/'current.json')['report']);bound(report['proofs']);blob=(ROOT/report['archive']).read_bytes()
    if digest(blob)!=report['packageSha256'] or len(blob)!=report['bytes']:raise ValueError('archive changed')
    return report,blob
if __name__=='__main__':
    r=make() if sys.argv[1:]==['--build'] else verify()[0]
    print(json.dumps({k:r[k] for k in ('archive','packageSha256','bytes','targetValidated','hardwareRequests')}))
