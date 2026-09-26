"""核验最终实际归档、ARM 导出、摘要成员及本地原厂基线映射。"""
from pathlib import Path
import hashlib,importlib.util,io,json,subprocess,sys,tarfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('ui_fixed_session_package',HERE/'session/package.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def run():
    assert Path.cwd().resolve()==ROOT
    report,blob=p.verify();checks=[]
    def check(n,v):
        if not v:raise AssertionError(n)
        checks.append(n)
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        members=archive.getmembers();files={v.name:archive.extractfile(v).read() for v in members}
        check('exact nine regular archive files',len(members)==9 and all(v.isfile() and '/' not in v.name and v.uid==v.gid==0 for v in members))
        check('private modes and executable entrypoints',all(v.mode==(0o700 if v.name.endswith('.sh') or v.name=='ui-health' else 0o600) for v in members))
    check('every archive digest matches delivery manifest',{n:p.digest(v) for n,v in files.items()}==report['files'])
    manifest={n:h for h,n in (line.split() for line in files['manifest.sha256'].decode().splitlines())}
    check('manifest binds exactly eight payload files',set(manifest)==set(files)-{'manifest.sha256'} and all(p.digest(files[n])==h for n,h in manifest.items()))
    check('fixed RCC byte identity',p.digest(files['ui-resident.rcc'])==p.build.RCC_SHA)
    check('Linux scripts and manifests have LF line endings',all(b'\r' not in files[n] for n in files if n.endswith(('.sh','.sha256'))))
    sys.path.insert(0,str(p.build.CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(files['libhbl-ui-resident.so']))
    symbols={s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']!='SHN_UNDEF'}
    check('actual ARM library exports both Qt interposition symbols',elf.elfclass==32 and elf['e_machine']=='EM_ARM' and
        {'_Z21qRegisterResourceDataiPKhS0_S0_','_ZN21QQmlApplicationEngine4loadERK4QUrl'}<=symbols)
    shell='\n'.join(files[n].decode() for n in ('common.sh','install.sh','restore.sh','run.sh'))
    service_actions=[line.strip() for line in shell.splitlines() if line.strip().startswith('systemctl ') and any(' '+n+' ' in line for n in ('start','stop','restart'))]
    check('all actual service mutation commands target GUI',len(service_actions)==3 and all(' victory-gui ' in line for line in service_actions))
    lines=[]
    for line in files['baseline.sha256'].decode().splitlines():
        h,name=line.split();path=p.build.BASELINE/name.lstrip('/')
        if name=='/usr/bin/msg2dbus':path=p.build.CACHE/'usb-diagnostic-inputs/usr/bin/msg2dbus'
        check('baseline source '+name,p.build.sha(path)==h)
        lines.append(h+'  '+path.as_posix())
    check('libstdc++ path preserved',any('libstdc++' in line for line in lines))
    directory=HERE/'build/session/package-audit';directory.mkdir(parents=True,exist_ok=True)
    manifest_path=directory/'local-baseline.sha256';manifest_path.write_bytes(('\n'.join(lines)+'\n').encode('ascii'))
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe','-c','sha256sum -c "$1"','package-audit',str(manifest_path)],capture_output=True,text=True,timeout=60)
    check('actual sha256sum accepts all mapped baseline paths including plus',result.returncode==0)
    proof={'passed':True,'checks':checks,'packageSha256':report['packageSha256'],'packageReportSha256':p.build.sha(ROOT/p.read(p.OUT/'current.json')['report']),
        'testSha256':p.build.sha(Path(__file__)),'hardwareRequests':0,'targetValidated':False}
    p.build.save(HERE/'build/session/package-validation.json',proof)
    print(json.dumps({'passed':True,'checks':len(checks),'packageSha256':report['packageSha256'],'hardwareRequests':0}))
if __name__=='__main__':run()
