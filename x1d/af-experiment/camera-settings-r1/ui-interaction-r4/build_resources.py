"""只替换冻结 AF RCC 内的 SettingsPage；其他六项逐字保留。"""
import hashlib,importlib.util,io,json,os,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];AF=HERE.parent
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
from PySide6.QtCore import QResource,QFile,QIODevice
def sha(data):return hashlib.sha256(data).hexdigest()
def build():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace required')
    package=AF/'delivery-r3/inputs/af-only.tar.gz'
    if sha(package.read_bytes())!='f325db70de366f52ae3b58b98f8e9fd3e496f353dbab64c6ca4712a49064cc6a':raise ValueError('frozen AF package')
    with tarfile.open(package) as archive:old=archive.extractfile('af-only-ui.rcc').read()
    previous=HERE/'inputs/previous-af-only-ui.rcc';previous.write_bytes(old)
    if not QResource.registerResource(str(previous)):raise ValueError('original resource registration')
    keys=['/main.qml','/settings/scripts/MenuItemSpecificationsWedge.js','/settings/SettingsGeneric.qml','/controlscreen/ControlScreen.qml',
        '/af-settings/AfQuickEntry.qml','/af-settings/AfSettingsHost.qml','/af-settings/SettingsPage.qml']
    originals={}
    for key in keys:
        f=QFile(':'+key)
        if not f.open(QIODevice.OpenModeFlag.ReadOnly):raise ValueError(key)
        originals[key]=bytes(f.readAll());f.close()
    QResource.unregisterResource(str(previous))
    files={k:v.decode('utf-8') for k,v in originals.items()}
    files['/af-settings/SettingsPage.qml']=(HERE/'SettingsPage.qml').read_text(encoding='utf-8')
    spec=importlib.util.spec_from_file_location('r4_resource_writer',ROOT/'x1d/wireless-flash/build.py')
    writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(writer)
    out=HERE/'build/resources';out.mkdir(parents=True,exist_ok=True)
    data=writer.rcc(files);(out/'af-only-ui.rcc').write_bytes(data)
    for key,value in files.items():
        p=out/'qml'/key.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8',newline='\n')
    changed=[k for k,v in files.items() if v.encode()!=originals[k]]
    assert changed==['/af-settings/SettingsPage.qml']
    report={'resourceCount':7,'changed':changed,'rccSha256':sha(data),'previousRccSha256':sha(old),
        'qml':{k:sha(v.encode()) for k,v in files.items()},'originals':{k:sha(v) for k,v in originals.items()},
        'hardwareRequests':0,'sources':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in (Path(__file__),HERE/'SettingsPage.qml',ROOT/'x1d/wireless-flash/build.py',package)}}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
if __name__=='__main__':print(json.dumps(build()))
