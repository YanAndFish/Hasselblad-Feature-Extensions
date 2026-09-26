"""离线资源/拒绝覆盖/Qt5.5 API 存在性检查，不构建组合包。"""
from pathlib import Path
import hashlib,json,sys,tarfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE/'tools'))
import transform

def run():
    original=transform.qml_files(transform.ArmElf.load('usr/bin/victory-gui'))
    snapshot=dict(original);output=transform.transform_all(original);checks=[]
    def check(name,v):assert v,name;checks.append(name)
    changed={k for k,v in output.items() if original.get(k)!=v}
    expected={'/components/MediaBrowseView.qml','/common/TouchWindow.qml','/liveview/EVFWindow.qml',
        '/browseview/MediaListViewImageDelegate.qml','/browseview/MediaListViewVideoDelegate.qml',
        '/settings/ResidentBrowsePhoto.qml','/browseview/ResidentVideoOverlay.qml'}
    check('只变更约定七资源',changed==expected)
    check('输入字典和其他原厂资源保持不变',original==snapshot and all(output[k]==v for k,v in original.items() if k not in changed))
    def refuses(data):
        try:transform.transform_all(data)
        except (ValueError,AssertionError):return True
        return False
    check('重复变换拒绝',refuses(output))
    for p in ['/settings/ResidentBrowsePhoto.qml','/browseview/ResidentVideoOverlay.qml']:
        altered=dict(original);altered[p]='foreign'
        check('已有资源拒绝覆盖 '+p,refuses(altered))
    for p,token in [('/common/TouchWindow.qml','id: media_browse_loader'),('/liveview/EVFWindow.qml','id: preView'),('/components/MediaBrowseView.qml','property alias model: media_grid.model')]:
        altered=dict(original);altered[p]=altered[p].replace(token,'unsupported_anchor',1)
        # 锚点不匹配必须显式失败；不落盘部分资源。
        try:transform.transform_all(altered);failed=False
        except (ValueError,AssertionError):failed=True
        check('关键锚点漂移拒绝 '+p,failed)
    check('两个窗口不再使用旧active表示呈现','media_browse_loader.active' not in output['/common/TouchWindow.qml'] and 'preView.active' not in output['/liveview/EVFWindow.qml'])
    archive=ROOT/'.research-cache/x1d-1.25.0/qt-public/qtdeclarative-opensource-src-5.5.1.tar.xz'
    signatures={
        'src/qml/types/qqmlconnections_p.h':['Q_PROPERTY(QObject *target','setTarget'],
        'src/quick/items/qquickloader_p.h':['Q_PROPERTY(bool active','Q_PROPERTY(bool asynchronous'],
        'src/quick/items/qquickimagebase_p.h':['Q_PROPERTY(bool cache','Q_PROPERTY(QUrl source'],
        'src/quick/items/qquickloader.cpp':['object->deleteLater()'],
        'src/quick/items/qquickimagebase.cpp':['d->pix.clear(this)']}
    with tarfile.open(archive) as tar:
        for path,terms in signatures.items():
            text=tar.extractfile('qtdeclarative-opensource-src-5.5.1/'+path).read().decode()
            check('Qt5.5源码接口 '+path,all(t in text for t in terms))
    rows=[]
    for key in sorted(changed):
        data=output[key].encode();old=original.get(key,'').encode()
        rows.append({'path':key,'kind':'modified' if key in original else 'added','originalBytes':len(old),'candidateBytes':len(data),'deltaBytes':len(data)-len(old),'sha256':hashlib.sha256(data).hexdigest()})
    report={'passed':True,'checks':checks,'resources':rows,'qmlUtf8Bytes':sum(r['candidateBytes'] for r in rows),'qmlDeltaBytes':sum(r['deltaBytes'] for r in rows),
        'cameraRequests':0,'combinedPackageBuilt':False,'targetQtExecuted':False,'targetRamBytes':None,'qtArchiveSha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (HERE/'artifacts/contract.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'qmlUtf8Bytes':report['qmlUtf8Bytes'],'qmlDeltaBytes':report['qmlDeltaBytes'],'combinedPackageBuilt':False}))
if __name__=='__main__':run()
