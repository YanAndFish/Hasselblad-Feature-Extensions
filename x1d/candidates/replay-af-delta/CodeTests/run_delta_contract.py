"""RCC 内容、动态导出和固定 AF 组合合同；不是目标动态链接器实测。"""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/tools'))
from binary import ArmElf
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
from PySide6.QtCore import QResource,QFile,QIODevice
def sha(b):return hashlib.sha256(b).hexdigest()
def read(path,keys):
    assert QResource.registerResource(str(path));out={}
    for k in keys:
        f=QFile(':'+k);assert f.open(QIODevice.ReadOnly),k;out[k]=bytes(f.readAll());f.close();del f
    assert QResource.unregisterResource(str(path));return out
def run():
    session=HERE/'artifacts/session';af=ROOT/'x1d/af-experiment/camera-settings-r1/delivery-r5/inputs'
    manifest=json.loads((session/'resources.json').read_text());keys=list(manifest['originals'])
    old=read(af/'af-only-ui.rcc',keys);new=read(session/'replay-ui.rcc',keys+['/components/MediaBrowseView.qml'])
    cases=[]
    for k in keys:
        if k!='/main.qml':assert new[k]==old[k];cases.append('unchanged '+k)
    hold=(HERE/'session/hold.qml.inc').read_text(encoding='utf-8')
    assert new['/main.qml'].decode()==old['/main.qml'].decode().rstrip()[:-1]+hold+'\n    property var replayCatalogModel: ContentModel\n}\n'
    cases.append('AF-main-preserved-with-independent-hold-and-reader-binding')
    assert new['/components/MediaBrowseView.qml']==(ROOT/'x1d/candidates/replay-reader/artifacts/session/MediaBrowseView.qml').read_bytes()
    cases.append('reader-component-byte-identical')
    e=ArmElf((session/'libx1d-replay-session.so').read_bytes())
    exported={s.name for s in e.elf.get_section_by_name('.dynsym').iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF'}
    assert exported=={'_ZN9QResource16registerResourceERK7QStringS2_','_ZN21QQmlApplicationEngine4loadERK4QUrl','x1d_replay_session_admit'}
    assert not any('qRegisterResourceData' in n for n in exported);cases.append('one-AF-qRegisterResourceData-hook-retained')
    host=ArmElf((af/'libhbl-af-only.so').read_bytes())
    imports={s.name for s in host.symbols if s['st_shndx']=='SHN_UNDEF'}
    assert '_ZN9QResource16registerResourceERK7QStringS2_' in imports;cases.append('AF-host-uses-interposable-file-resource-import')
    data=(HERE/'artifacts/package-staging/delta.conf').read_text()
    assert data.count('LD_PRELOAD=')==1 and 'libx1d-replay-session.so:/tmp/hbl-x1d-rpa/libx1d-replay-provider.so:/tmp/hbl-x1d-combined/libhbl-af-only.so:/tmp/hbl-x1d-combined/af/libhbl-af-ui.so' in data
    cases.append('explicit-session-provider-AFhost-AFUI-order')
    source=(HERE/'session/session_runtime.cpp').read_text(encoding='utf-8')
    for guard in ['file!=QStringLiteral("/tmp/hbl-x1d-combined/af-only-ui.rcc")','!root.isEmpty()',
                  'X1D_AF_HOST_SHA256','X1D_AF_UI_SHA256','X1D_AF_RCC_SHA256','X1D_SESSION_RCC_SHA256']:
        assert guard in source
    cases.append('source-audit-fixed-file-root-and-hash-guards')
    report={'passed':True,'cameraAccess':False,'targetLoaderExecuted':False,'rccReadback':'host Qt6',
      'cases':cases,'inputRccSha256':sha((af/'af-only-ui.rcc').read_bytes()),
      'moduleSha256':sha(e.data),'rccSha256':sha((session/'replay-ui.rcc').read_bytes()),
      'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'session/session_runtime.cpp']}}
    out=HERE/'artifacts/session-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'delta-contract.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'deltaContractCases':len(cases),'cameraAccess':False}))
if __name__=='__main__':run()
