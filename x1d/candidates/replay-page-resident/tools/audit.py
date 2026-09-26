"""固定 1.25.0 QRC 与 Qt5.5.1 生命周期证据，仅写本独立候选。"""
from pathlib import Path
import hashlib, json, sys, tarfile
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'x1d/tools'))
from binary import ArmElf, qml_files, CACHE

def sha(data): return hashlib.sha256(data).hexdigest()
def excerpt(text, terms):
    lines = text.splitlines(); indices = set()
    for i, line in enumerate(lines):
        if any(term in line for term in terms):
            indices.update(range(max(0, i-2), min(len(lines), i+9)))
    return '\n'.join(f'{i+1}: {lines[i]}' for i in sorted(indices))

def run():
    gui = ArmElf.load('usr/bin/victory-gui'); qml = qml_files(gui)
    out = HERE / 'artifacts'; out.mkdir(exist_ok=True)
    selected = {
        '/common/TouchWindow.qml': ['id: media_browse_loader', 'target: media_browse_loader'],
        '/liveview/EVFWindow.qml': ['id: preView', 'onActiveChanged:', 'onLoaded:', 'target: preView'],
        '/components/MediaBrowseView.qml': ['Component.onCompleted:', 'target: ContentModel', 'getAckAddedImage', 'property alias model:',
            'model: SortedContentModel', 'source: (media_grid.visible', 'id: flick_img', 'id: flick_fullimg', 'id: list_delegate_loader',
            'onCurrentIndexChanged:', 'Component.onDestruction:', 'target: BodySync', 'from: "zooming"', 'onPrepareScaling:', 'onScaled:'],
        '/browseview/MediaListViewImageDelegate.qml': ['source: list_delegate.loadImage', 'histogramData'],
        '/settings/Photo.qml': ['cache: false', 'property variant src: img']}
    hashes = {}
    for path, terms in selected.items():
        data = qml[path]; hashes[path] = sha(data.encode())
        (out / (Path(path).stem + '-excerpts.txt')).write_text(excerpt(data, terms) + '\n', encoding='utf-8')
    qt = CACHE / 'qt-public/qtdeclarative-opensource-src-5.5.1.tar.xz'
    qtfiles = {}; texts = []
    with tarfile.open(qt) as archive:
        for suffix, terms in {
            'src/quick/items/qquickloader.cpp': ['void QQuickLoader::setActive', 'd->object->deleteLater'],
            'src/quick/items/qquickimagebase.cpp': ['if (d->url.isEmpty())', 'options |= QQuickPixmap::Cache'],
            'src/quick/util/qquickpixmapcache.cpp': ['provider->requestTexture(', 'if (!cancelled.contains(runningJob))', 'If Cache is disabled'],
            'src/quick/items/qquickimage.cpp': ['delete node', 'textureFactory()', 'setTexture']}.items():
            name = 'qtdeclarative-opensource-src-5.5.1/' + suffix
            data = archive.extractfile(name).read(); qtfiles[name] = sha(data)
            texts.append(name + '\n' + excerpt(data.decode(), terms))
    (out / 'qt-5.5.1-excerpts.txt').write_text('\n\n'.join(texts) + '\n', encoding='utf-8')
    # 原厂 TextureFactory/Texture 的虚表地址与清理链，未执行目标代码。
    assert gui.word(0x2186fc) == 0x47290 and gui.word(0x218768) == 0x47638
    free_name = (0x7dfdc + gui.word(0x7e1b4)) & 0xffffffff
    assert gui.read(free_name,10) == b'FreeBuffer'
    texture_ranges=[(0x47290,0x150),(0x47550,0x2c),(0x47638,0x1a4),(0x478fc,0x70),(0x7de44,0x368)]
    (out/'original-texture-lifetime.txt').write_text('\n\n'.join(gui.disassembly(a,n) for a,n in texture_ranges)+'\n',encoding='utf-8')
    report = {'firmware': 'X1D-50c 1.25.0', 'guiSha256': sha(gui.data), 'qmlSha256': hashes,
        'qtArchiveSha256': sha(qt.read_bytes()), 'qtSourceSha256': qtfiles,
        'cameraRequests': 0, 'productionQmlCandidateImplemented': True, 'targetQt55Executed':False, 'targetGpuExecuted':False,
        'status': '原厂完整页面与LCD/EVF Loader离线候选已实现；不是可安装交付',
        'nativeStatic':{'factoryDestructor':'0x47290','textureDestructor':'0x47638','referenceIncrement':'0x47914','sharedRelease':'0x7de44','storageMethod':'FreeBuffer','glDeleteRequiresCurrentContext':True},
        'sources': {p.relative_to(HERE).as_posix(): sha(p.read_bytes()) for p in [Path(__file__), HERE/'qml/ResidentPhotoSurface.qml', HERE/'CodeTests/test_lifecycle.py',HERE/'qml/page-lifecycle.inc',HERE/'tools/transform.py',HERE/'CodeTests/test_original_page.py']}}
    (out / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'guiSha256':report['guiSha256'], 'sources':len(hashes), 'cameraRequests':0}))

if __name__ == '__main__': run()
