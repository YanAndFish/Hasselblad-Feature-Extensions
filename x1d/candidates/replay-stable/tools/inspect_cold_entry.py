"""固定 1.25.0 的首次回放静态证据；不运行 GUI，不访问设备或照片。"""
from pathlib import Path
import hashlib
import json
import sys
import tarfile

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'x1d/tools'))
from binary import ArmElf, BASELINE, CACHE, qml_files


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run():
    out = HERE / 'artifacts/cold-entry'
    out.mkdir(parents=True, exist_ok=True)
    gui = ArmElf.load('usr/bin/victory-gui')
    assert sha(gui.data) == 'd29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
    qml = qml_files(gui)
    specs = {
        '/common/TouchWindow.qml': [(348,378),(716,755),(1810,1843)],
        '/liveview/EVFWindow.qml': [(243,269)],
        '/components/MediaBrowseView.qml': [(63,77),(407,434),(1558,1608),(1622,1644),(2188,2196)],
        '/browseview/MediaListViewImageDelegate.qml': [(59,74)],
        '/settings/Photo.qml': [(8,25)],
    }
    sources = {}
    snippets = []

    def capture(name, data, ranges):
        sources[name] = sha(data)
        lines = data.decode().splitlines()
        snippets.append('\n[' + name + '] sha256=' + sources[name])
        for first,last in ranges:
            snippets.extend(f'{i+1}: {lines[i]}' for i in range(first-1,min(last,len(lines))))

    for name,ranges in specs.items():
        capture(name,qml[name].encode(),ranges)
    qt = CACHE / 'qt-public/qtdeclarative-opensource-src-5.5.1.tar.xz'
    assert sha(qt.read_bytes()) == '5fd14eefb83fff36fb17681693a70868f6aaf6138603d799c16466a094b26791'
    with tarfile.open(qt) as archive:
        for suffix,ranges in {
            'items/qquickloader.cpp':[(325,364)],
            'util/qquickpixmapcache.cpp':[(425,432),(538,545),(565,592),(646,658),(696,705),(1340,1347),(1374,1376)],
            'scenegraph/util/qsgtexture.cpp':[(600,810)],
        }.items():
            name='qtdeclarative-opensource-src-5.5.1/src/quick/'+suffix
            capture(name,archive.extractfile(name).read(),ranges)
    native=HERE/'native'
    provider=(native/'replay_provider.cpp').read_text(encoding='utf-8')
    runtime=(native/'replay_runtime.cpp').read_text(encoding='utf-8')
    checks={
        'lcdPageInitiallyInactive': 'active:false' in qml['/common/TouchWindow.qml'].split('id: media_browse_loader',1)[1].split('source:',1)[0],
        'lcdActivatesOnBrowse': 'target: media_browse_loader; active: !GlobalStateInfo.evfActive' in qml['/common/TouchWindow.qml'],
        'evfPageCreatedOnActivation': 'setSource("qrc:///components/MediaBrowseView.qml", {"usedInEVF": true' in qml['/liveview/EVFWindow.qml'],
        'photoPixmapCacheDisabledByFactoryQml': 'cache: false' in qml['/settings/Photo.qml'],
        'providerRegistrationAtFixedStartupCall': any(name=='_ZN10QQmlEngine16addImageProviderERK7QStringP21QQmlImageProviderBase' for _,_,name in gui.direct_calls(0x26e7c,4)),
        'twoSeparateStaticRuntimeChecks': provider.count('static const bool enabled = X1D::runtimeMatches("victory-gui");')==2,
        'pixmapRuntimeCheckPrecedesUrlFilter': provider.rfind('static const bool enabled = X1D::runtimeMatches("victory-gui");') < provider.index('if (enabled && url.scheme()'),
        'cacheLookupAfterSourceAndPrefixValidation': provider.index('X1D::sameSource(source, record)') < provider.index('headerMatches(header, record, &info)') < provider.index('previews.get(key, &cached)'),
        'codecApiBoundLazilyOnce': 'static const XjCodec api = []()' in runtime,
    }
    assert all(checks.values()), checks
    files=['usr/bin/victory-gui','usr/lib/libappscommon.so.1.0.0',
           'usr/lib/libQt5Core.so.5.5.1','usr/lib/libQt5DBus.so.5.5.1',
           'usr/lib/libturbojpeg.so.0.1.0','usr/lib/libQt5Gui.so.5.5.1',
           'usr/lib/libQt5Quick.so.5.5.1','usr/lib/libQt5Qml.so.5.5.1']
    evidence='\n'.join(snippets)+'\n\n[provider registration and constructor]\n'+gui.disassembly(0x26e48,0x40)+'\n'+gui.disassembly(0x459e8,0x58)+'\n'
    (out/'excerpts.txt').write_text(evidence,encoding='utf-8')
    report={
        'kind':'static-cold-entry-analysis-not-target-profile','firmware':'X1D-50c 1.25.0',
        'cameraAccess':False,'photoAccess':False,'currentPackageModified':False,
        'currentArchiveSha256':sha((HERE/'artifacts/session-package/session.tar.gz').read_bytes()),
        'guiSha256':sha(gui.data),'qtArchiveSha256':sha(qt.read_bytes()),
        'checks':checks,'fixedInputHashes':sources,
        'runtimeCheckInputBytesPerSuccessfulPass':sum((BASELINE/name).stat().st_size for name in files),
        'runtimeCheckAtFirstReplayProven':False,'firstReplayLatencyFixed':False,
        'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),native/'replay_provider.cpp',native/'replay_runtime.cpp',native/'ready_refresh.cpp',HERE/'tools/build_session.py']},
        'excerptsSha256':sha((out/'excerpts.txt').read_bytes()),
    }
    assert report['currentArchiveSha256']=='4ff2a1981ecf52546b0f743ea6eb6622a8aceac8db968c03262496a44c439a78'
    (out/'analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'staticChecks':len(checks),'cameraAccess':False,'currentPackageModified':False}))


if __name__=='__main__':
    run()
