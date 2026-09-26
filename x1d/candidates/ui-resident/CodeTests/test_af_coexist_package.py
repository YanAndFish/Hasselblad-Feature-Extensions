"""最终特定 AF r4 共存归档审计；必须已有 AF owner 固定绑定。"""
from pathlib import Path
import hashlib,importlib.util,io,json,sys,tarfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('ui_af_package_audit',HERE/'af-session/package.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def run():
    report,blob=p.verify();binding,r4=p.build.r4_inputs(required=True);af,resources=p.build.inputs();checks=[]
    def check(n,v):
        if not v:raise AssertionError(n)
        checks.append(n)
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        members=archive.getmembers();files={m.name:archive.extractfile(m).read() for m in members}
        check('only plain private payload files',all(m.isfile() and '/' not in m.name and m.uid==m.gid==0 and m.mode in (0o600,0o700) for m in members))
    check('all archived bytes match report',{n:p.digest(v) for n,v in files.items()}==report['files'])
    check('no AF replacement libraries or AF RCC shipped',not any(n in files for n in ('libhbl-af-ui.so','libhbl-af-bus.so','libhbl-af-only.so','af-only-ui.rcc')))
    check('all shell and manifests are Linux LF',all(b'\r' not in v for n,v in files.items() if n.endswith(('.sh','.sha256','.expected'))))
    manifest={n:h for h,n in (line.split() for line in files['manifest.sha256'].decode().splitlines())}
    check('every payload bound by manifest',set(manifest)==set(files)-{'manifest.sha256'} and all(p.digest(files[n])==h for n,h in manifest.items()))
    inherited={n:h for h,n in (line.split() for line in files['inherited.sha256'].decode().splitlines())}
    expected={p.build.OLD+'/'+n:p.digest(v) for n,v in af.items()}
    expected.update({binding['remoteRoot']+'/'+n:p.digest(v) for n,v in r4.items()})
    check('every inherited fixed AF and r4 file bound',inherited==expected)
    check('AF owner r4 dropin bytes retained exactly',files['r4-gui.expected']==binding['guiDropinText'].encode())
    for n,marker in [('af-gui.expected','gui.dropin'),('af-bus.expected','farm.dropin')]:
        check('original f325 configuration '+n,files[n]==p.af_dropin(af['install.sh'],marker))
    check('original AF installation receipt bound',files['af-receipt.expected'].decode().strip()==p.build.AF_PROOF)
    delta=p.build.read_rcc(files['ui-af.rcc'])
    check('actual delta contains exactly four resources',set(delta)=={'/mainmenu/MainScreen.qml','/mainmenu/Menu.qml','/mainmenu/ResidentLoader.qml','/settings/SettingsGeneric.qml'})
    check('AF page is supplied by r4 not replaced in delta','/af-settings/SettingsPage.qml' not in delta and resources['/af-settings/SettingsPage.qml']==p.build.read_rcc(r4['af-only-ui.rcc'])['/af-settings/SettingsPage.qml'])
    check('Generic contains both AF return and resident lifecycle','item.afCloseRequested.connect(subDialog.closeSubDialog)' in delta['/settings/SettingsGeneric.qml'] and 'function residentDeactivate()' in delta['/settings/SettingsGeneric.qml'])
    sys.path.insert(0,str(p.build.CACHE/'python'));from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(files['libhbl-ui-af.so']))
    exports={s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']!='SHN_UNDEF'}
    check('ARM Qt interceptors exported',elf.elfclass==32 and elf['e_machine']=='EM_ARM' and
        {'_Z21qRegisterResourceDataiPKhS0_S0_','_ZN21QQmlApplicationEngine4loadERK4QUrl'}<=exports)
    check('AF r4 QString resource redirect hook not replaced','_ZN9QResource16registerResourceERK7QStringS2_' not in exports)
    afelf=ELFFile(io.BytesIO(af['libhbl-af-only.so']));r4elf=ELFFile(io.BytesIO(r4['libhbl-af-ui.so']))
    def symbols(e):return {s.name for s in e.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']!='SHN_UNDEF'}
    check('both fixed AF load hooks remain present',all('_ZN21QQmlApplicationEngine4loadERK4QUrl' in symbols(e) for e in (afelf,r4elf)))
    check('actual r4 library exports QString redirect','_ZN9QResource16registerResourceERK7QStringS2_' in symbols(r4elf))
    code='\n'.join(files[n].decode() for n in ('common.sh','install.sh','restore.sh','run.sh'))
    actions=[line for line in code.splitlines() if line.strip().startswith('systemctl ') and any(' '+a+' ' in line for a in ('start','stop','restart'))]
    check('only GUI service can be mutated',len(actions)==3 and all(' victory-gui ' in line for line in actions))
    check('rollback only removes owned 99 dropin','rm "$gui"' in files['restore.sh'].decode() and 'rm "$afgui"' not in code and 'rm "$fixgui"' not in code)
    check('final preload and rollback preload match owner contract',report['preload']==p.build.NEW_PRELOAD and report['recoveryPreload']==p.build.OLD_PRELOAD)
    proof={'passed':True,'checks':checks,'packageSha256':report['packageSha256'],'r4ArchiveSha256':binding['archiveSha256'],
        'testSha256':p.build.sha(Path(__file__)),'hardwareRequests':0,'targetValidated':False}
    p.build.save(p.OUT/'package-validation.json',proof)
    print(json.dumps({'passed':True,'checks':len(checks),'packageSha256':report['packageSha256'],'hardwareRequests':0}))
if __name__=='__main__':run()
