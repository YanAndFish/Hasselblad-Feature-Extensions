"""固定原厂 QML 的页面生命周期拆分；只生成独立候选，尚不用于装载。"""
from pathlib import Path
import hashlib, json, re, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'x1d/tools'))
from binary import ArmElf, qml_files

def once(text, old, new):
    assert text.count(old) == 1, (old[:100], text.count(old))
    return text.replace(old, new, 1)

def closing(text, start):
    """匹配 QML/JS 花括号，跳过注释与字符串。"""
    assert text[start] == '{'
    depth = 0; i = start
    while i < len(text):
        if text.startswith('//', i):
            j = text.find('\n', i); i = len(text) if j < 0 else j; continue
        if text.startswith('/*', i):
            i = text.index('*/', i+2)+2; continue
        ch = text[i]
        if ch in ('"', "'"):
            quote = ch; i += 1
            while i < len(text):
                if text[i] == '\\': i += 2; continue
                if text[i] == quote: break
                i += 1
        elif ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return i
        i += 1
    raise ValueError('未闭合代码块')

def handler(text, key, replacement):
    start = text.index(key); brace = text.index('{', start)
    end = closing(text, brace)
    return text[:start] + replacement + text[end+1:]

def gate_blocks(text, pattern, guard):
    edits = []
    for m in re.finditer(pattern, text):
        brace = text.index('{', m.start(), m.end())
        edits.append((brace+1, '\n' + ' ' * 12 + guard))
    for pos, value in reversed(edits): text = text[:pos] + value + text[pos:]
    return text

def page(text):
    text = handler(text, '    Component.onCompleted: {', '    Component.onCompleted: residentConstructed = true')
    text = handler(text, '    Component.onDestruction: {', '    Component.onDestruction: residentLeave()')
    text = handler(text, '        Component.onCompleted: {\n            ContentModel.currentWorkingDirChanged',
        '        // currentWorkingDirChanged 由页面会话 Connections 管理。')
    text = once(text, '    property alias model: media_grid.model', '    property var model: SortedContentModel')
    text = text.replace('media_grid.model', 'root.model')
    text = once(text, '        target: parent\n        property: "preventControlScreenSwipe"', '        target: root.residentSessionActive && !root.usedInEVF ? parent : null\n        property: "preventControlScreenSwipe"')
    text = re.sub(r'(?<![.\w])model\.(source|listSize)', r'root.model.\1', text)
    text = once(text, '        model: SortedContentModel', '        model: root.residentSessionActive ? root.model : null')
    text = once(text, '        model: root.model\n        anchors.fill: parent', '        model: root.residentSessionActive ? root.model : null\n        anchors.fill: parent')
    text = once(text, '    focus: true\n    state:', '    focus: residentSessionActive\n    enabled: residentSessionActive\n    visible: residentSessionActive\n    state:')
    text = once(text, '    state: (root.model.source.pathType === ContentModel.PATH_TYPE_FILES) && (root.model.listSize > 0) ? "list" : "grid"',
        '    state: "resident_idle"')
    # 所有原页事件块在静默/退出阶段不执行；索引在模型挂接阶段另行同步。
    text = gate_blocks(text, r'(?:\bKeys\.)?\bon[A-Z]\w*\s*:\s*\{', 'if (!root.residentSessionActive) return;')
    text = text.replace('onCurrentIndexChanged: {\n            if (!root.residentSessionActive) return;',
                        'onCurrentIndexChanged: {\n            if (!root.residentSessionActive || root.residentActivating || !root.residentImagesEnabled) return;')
    text = text.replace('onStateChanged: {\n            if (!root.residentSessionActive) return;',
                        'onStateChanged: {\n            if (!root.residentSessionActive || !root.residentImagesEnabled) return;')
    # 一行事件包含 console 多行调用时不改变其语法；日志无状态副作用。
    text = re.sub(r'^(\s*(?:Keys\.)?on[A-Z]\w*\s*:) ([^\n{]+)$',
        lambda m: m[0] if m[2].lstrip().startswith(('console.', '//')) else m[1]+' { if (root.residentSessionActive) { '+m[2]+' } }', text, flags=re.M)
    text = gate_blocks(text, r'\bfunction\s+\w+\([^)]*\)\s*\{', 'if (!root.residentSessionActive) return;')
    text = gate_blocks(text, r'\bscript\s*:\s*\{', 'if (!root.residentSessionActive) return;')
    # 断开 Connections 的信号来源，避免预建期观察或迟到回复驱动状态。
    blocks = []
    for m in re.finditer(r'\bConnections\s*\{', text):
        end = closing(text, text.index('{', m.start()))
        block = text[m.start():end+1]
        block = re.sub(r'^(\s*target:) ([^\n]+)$', r'\1 root.residentSessionActive ? (\2) : null', block, count=1, flags=re.M)
        blocks.append((m.start(), end+1, block))
    for a,b,value in reversed(blocks): text = text[:a]+value+text[b:]
    # 原页顶级自动状态必须在呈现时才生效。
    state_start = text.index('    states: [', text.index('    onStateChanged:'))
    suffix = text[state_start:]
    auto = []
    for state in ['list', 'grid', 'video_playback']:
        match = re.search(r'name: "'+state+r'"\n\s*when: ([^\n]+)', suffix)
        assert match
        condition = match[1]; auto.append('('+condition+') ? "'+state+'" : ')
        suffix = suffix[:match.start(1)]+'root.residentSessionActive && !root.residentActivating && root.residentAutomaticState === "'+state+'"'+suffix[match.end(1):]
    text = text[:state_start] + suffix
    text = once(text, '    property var model: SortedContentModel', '    property var model: SortedContentModel\n    readonly property string residentAutomaticState: '+''.join(auto)+'""')
    text = once(text, '        running: configstore.OverExposureWarning', '        running: root.residentSessionActive && configstore.OverExposureWarning')
    text = once(text, '        alwaysRunToEnd: true', '        alwaysRunToEnd: false')
    text = once(text, '                source: (media_grid.visible && (fileType === ContentModel.Image || fileType === ContentModel.Video)) ? image : grid_img.source',
        '                source: root.residentImagesEnabled && grid_delegate.residentEpoch === root.residentEpoch && media_grid.visible && (fileType === ContentModel.Image || fileType === ContentModel.Video) ? image : ""')
    text = once(text, '            id: grid_delegate', '            id: grid_delegate\n            property int residentEpoch: root.residentEpoch\n            Component.onCompleted: residentEpoch = root.residentEpoch')
    text = once(text, '                id: grid_img', '                id: grid_img\n                lifecycleCurrent: root.residentImagesEnabled && grid_delegate.residentEpoch === root.residentEpoch')
    text = once(text, '            Photo {', '            ResidentBrowsePhoto {')
    text = once(text, '                    id: list_delegate_loader',
        '                    id: list_delegate_loader\n                    property int residentEpoch: root.residentEpoch\n                    Component.onCompleted: residentEpoch = root.residentEpoch\n                    active: root.residentImagesEnabled && residentEpoch === root.residentEpoch')
    # Loader 子作用域包含所有照片/视频结果转发。旧 delegate 即使延迟销毁也不能转发到新会话。
    a = text.index('                Loader {', text.index('    ListView {'))
    b = closing(text, text.index('{', a))
    block = text[a:b+1].replace('if (!root.residentSessionActive) return;', 'if (!root.residentSessionActive || list_delegate_loader.residentEpoch !== root.residentEpoch) return;')
    block = block.replace('target: root.residentSessionActive ?', 'target: root.residentSessionActive && list_delegate_loader.residentEpoch === root.residentEpoch ?')
    block = block.replace('list_delegate_loader.item.loadImage =', 'if (list_delegate_loader.status === Loader.Ready && list_delegate_loader.item) list_delegate_loader.item.loadImage =')
    text = text[:a]+block+text[b+1:]
    for name in ['flick_img', 'flick_fullimg']:
        text = once(text, '                id: '+name, '                id: '+name+'\n                cache: false')
    text = once(text, '    VideoOverlay {', '    ResidentVideoOverlay {\n        lifecycleCurrent: root.residentImagesEnabled')
    text = once(text, '            VideoControl.setVideoPlaybackState(true, fileName, size)', '            root.residentVideoRequested = true\n            VideoControl.setVideoPlaybackState(true, fileName, size)')
    text = once(text, '                    VideoControl.setVideoPlaybackState(false, video_overlay.fileName, 0)', '                    root.residentVideoRequested = false\n                    VideoControl.setVideoPlaybackState(false, video_overlay.fileName, 0)')
    code = (HERE/'qml/page-lifecycle.inc').read_text(encoding='utf-8')
    return once(text, '    id: root', '    id: root\n'+code)

def photo(text):
    text = once(text, '    id: img', '    id: img\n    property bool lifecycleCurrent: false')
    text = once(text, '        target: ContentModel', '        target: img.lifecycleCurrent ? ContentModel : null')
    return once(text, '        property variant src: img', '        property variant src: img.lifecycleCurrent ? img : null')

def touch(text):
    start = text.rindex('        Loader {', 0, text.index('            id: media_browse_loader'))
    end = closing(text, text.index('{', start))
    block = text[start:end+1]
    block = once(block, '            active:false', '            active: true\n            property bool presented: false')
    block = once(block, '            visible: active', '            visible: presented')
    block = handler(block, '            onStatusChanged: {', '''            function residentPresent() {
                if (!item) return
                if (presented) {
                    item.residentEnter(isInstantPreview, false, -1)
                    root.browseIn9View = item.is9ViewActive
                    if (item.hasLoadedCurrent) root.notifyCurrentImageLoaded()
                    if (mediaBrowseDeleteOnLoad) {
                        mediaBrowseDeleteOnLoad = false
                        item.deleteImage()
                    }
                } else {
                    item.residentLeave()
                }
            }
            onPresentedChanged: residentPresent()
            onIsInstantPreviewChanged: {
                if (presented && item) item.isInstantPreview = isInstantPreview
            }
            onLoaded: {
                item.isIn9View.connect(browse9ViewChanged)
                if (root.simulation) item.simulation = true
                idle_detect.onTouchEvent.connect(item.hideInstantAVTV)
                residentPresent()
            }''')
    text = text[:start]+block+text[end+1:]
    text = text.replace('media_browse_loader.active', 'media_browse_loader.presented')
    text = re.sub(r'(PropertyChanges \{ target: media_browse_loader;[^\n]*?)\bactive:',r'\1presented:',text)
    text = once(text, '        target: media_browse_loader.item', '        target: media_browse_loader.presented ? media_browse_loader.item : null')
    return text

def evf(text):
    start = text.rindex('        Loader {', 0, text.index('            id: preView'))
    end = closing(text, text.index('{', start)); block = text[start:end+1]
    block = once(block, '            active: false', '            active: true\n            property bool presented: false\n            source: "qrc:///components/MediaBrowseView.qml"')
    block = once(block, '            visible: active', '            visible: presented')
    block = handler(block, '            onActiveChanged: {', '''            function residentPresent() {
                if (presented) {
                    if (!item) return
                    focus = true
                    item.residentEnter(false, true, startIndex)
                    if (startTimer) {
                        startTimer = false
                        evfPreviewTimer.restart()
                    }
                } else {
                    if (item) item.residentLeave()
                    showPreview = false
                    evfPreviewTimer.stop()
                    scope.forceActiveFocus()
                }
            }
            onPresentedChanged: residentPresent()''')
    block = handler(block, '            onLoaded: {', '            onLoaded: { if (presented) residentPresent() }')
    block = once(block, '                target: preView.item', '                target: preView.presented ? preView.item : null')
    text = text[:start]+block+text[end+1:]
    text = text.replace('preView.active', 'preView.presented')
    text = re.sub(r'(PropertyChanges \{ target: preView;[^\n]*?)\bactive:',r'\1presented:',text)
    return text

def transform_all(original):
    for added in ['/settings/ResidentBrowsePhoto.qml', '/browseview/ResidentVideoOverlay.qml']:
        if added in original:
            raise ValueError('资源已存在，拒绝覆盖或重复变换: '+added)
    output = dict(original)
    output['/components/MediaBrowseView.qml'] = page(original['/components/MediaBrowseView.qml'])
    output['/settings/ResidentBrowsePhoto.qml'] = photo(original['/settings/Photo.qml'])
    d = once(original['/browseview/MediaListViewImageDelegate.qml'], '    Photo {', '    ResidentBrowsePhoto {')
    d = once(d, '        id: list_img', '        id: list_img\n        lifecycleCurrent: root.residentImagesEnabled && list_delegate_loader.residentEpoch === root.residentEpoch')
    d = once(d, '        source: list_delegate.loadImage ? image : ""', '        source: lifecycleCurrent && list_delegate.loadImage ? image : ""')
    output['/browseview/MediaListViewImageDelegate.qml'] = d
    video = once(original['/browseview/VideoOverlay.qml'], '    id: video_overlay', '    id: video_overlay\n    property bool lifecycleCurrent: false')
    video = once(video, '    Photo {', '    ResidentBrowsePhoto {\n        lifecycleCurrent: video_overlay.lifecycleCurrent')
    video = once(video, '        source: video_overlay.loadImage ? image : ""', '        source: lifecycleCurrent && video_overlay.loadImage ? image : ""')
    output['/browseview/ResidentVideoOverlay.qml'] = video
    delegate = once(original['/browseview/MediaListViewVideoDelegate.qml'], '    VideoOverlay {', '    ResidentVideoOverlay {\n        lifecycleCurrent: root.residentImagesEnabled && list_delegate_loader.residentEpoch === root.residentEpoch')
    delegate = once(delegate, '        target: configstore', '        target: root.residentSessionActive && list_delegate_loader.residentEpoch === root.residentEpoch ? configstore : null')
    output['/browseview/MediaListViewVideoDelegate.qml'] = delegate
    output['/common/TouchWindow.qml'] = touch(original['/common/TouchWindow.qml'])
    output['/liveview/EVFWindow.qml'] = evf(original['/liveview/EVFWindow.qml'])
    return output

def run():
    gui = ArmElf.load('usr/bin/victory-gui')
    assert hashlib.sha256(gui.data).hexdigest() == 'd29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
    original = qml_files(gui); output = transform_all(original)
    directory = HERE/'build/overlay'; directory.mkdir(parents=True, exist_ok=True)
    changed = {}
    for path, text in output.items():
        if path in original and original[path] == text: continue
        p = directory/path.lstrip('/'); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8', newline='\n')
        changed[path] = hashlib.sha256(text.encode()).hexdigest()
    (HERE/'artifacts/transform.json').write_text(json.dumps({'changed':changed,'cameraRequests':0,'installable':False}, indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'changed':list(changed),'installable':False}))
    return output

if __name__ == '__main__': run()
