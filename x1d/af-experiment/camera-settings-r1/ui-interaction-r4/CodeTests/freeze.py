"""收敛已执行的必要检查，绑定 GUI-only 交付文件。"""
import hashlib,io,json,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE));import gui_package
def main():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace required')
    qml=gui_package.read(HERE/'CodeTests/output/qml.json');shell=gui_package.read(HERE/'CodeTests/output/shell.json')
    resource=gui_package.read(HERE/'build/resources/manifest.json');native=gui_package.read(HERE/'linux-build/client-build.json')
    assert qml['passed'] and qml['checks']==132 and qml['rccSha256']==gui_package.sha(HERE/'build/resources/af-only-ui.rcc')
    assert shell['passed'] and len(shell['checks'])==6
    assert resource['changed']==['/af-settings/SettingsPage.qml'] and resource['resourceCount']==7
    for name,digest in native['sourceHashes'].items():assert gui_package.sha(HERE/name)==digest,name
    for name,digest in resource['sources'].items():assert gui_package.sha(ROOT/name)==digest,name
    for name,entry in native['outputs'].items():assert gui_package.sha(HERE/'linux-build'/name)==entry['sha256']
    subprocess.run([str(HERE/'CodeTests/output/flow.exe')],check=True,timeout=10)
    sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
    from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO((HERE/'linux-build/libhbl-af-ui.so').read_bytes()))
    definitions={s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']!='SHN_UNDEF'}
    assert {'_ZN9QResource16registerResourceERK7QStringS2_','_ZN21QQmlApplicationEngine4loadERK4QUrl'}<=definitions
    package=gui_package.make()
    paths=[p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.cpp','.h','.qml','.sh','.conf')]
    paths += [p for p in (HERE/'CodeTests').iterdir() if p.is_file()]
    paths += [HERE/'CodeTests/output'/n for n in ('qml.json','shell.json','flow.exe')]
    paths += [HERE/'build/resources/manifest.json',HERE/'build/resources/af-only-ui.rcc',HERE/'linux-build/client-build.json',HERE/'linux-build/libhbl-af-ui.so']
    paths += [HERE/'build/package/package.json',HERE/'build/package/af-ui-r4.tar.gz']
    paths += [(HERE/name).resolve() for name in native['sourceHashes']]
    paths += [ROOT/name for name in resource['sources']]
    paths += [HERE.parent/'delivery-r3/validation.json',HERE.parent/'delivery-r3/inputs/package.json']
    report={'passed':True,'revision':'af-ui-interaction-r4','hardwareRequests':0,'physicalGuiVerified':False,
        'qmlPointerChecks':132,'shellLifecycleChecks':6,'sharedCppFlowAndReplyChecks':True,
        'qtTestVersion':qml['qtVersion'],'targetQt55RuntimeTested':False,'afRamChanged':False,'busChanged':False,
        'packageSha256':package['packageSha256'],'sources':{p.relative_to(ROOT).as_posix():gui_package.sha(p) for p in set(paths)}}
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    gui_package.verify()
    print(json.dumps({'passed':True,'package':package,'validationSha256':gui_package.sha(HERE/'validation.json')}))
if __name__=='__main__':main()
