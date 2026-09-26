"""生成独立菜单加载候选；不修改已交付的蓝绿包，不连接相机。"""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
INPUT_ROUTE = '--input-route' in sys.argv
OUTPUT = D / ('input-candidate' if INPUT_ROUTE else 'menu-candidate')
OUTPUT.mkdir(exist_ok=True)
ROOT = D.parents[2]
sys.path.insert(0, str(ROOT / 'x2d/outputs/4.2.0/temporary-wifi-button/qt-runtime'))
from PySide6.QtCore import QTranslator
from PySide6.QtGui import QGuiApplication

def sha(data): return hashlib.sha256(data).hexdigest()

def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)

app = QGuiApplication([])
translator = QTranslator()
assert translator.load(str(D / 'menu-candidate/assets/camera_zh_CN.qm'))
qml = (D / 'menu-candidate/CustomMainMenu.qml').read_text(encoding='utf-8')
# Do not import the factory KeyFn singleton in --bus none image-test processes.
# Its isFn path enters GuiObjectImpl, whose main-application setup is absent here.
# Standalone Qt keys and touch stay local; half-press is observed by the controller.
from prepare_flash_ui import prepare, NAMES, OUT
prepare()
qml = replace_once(qml, 'import "flash-ui"\n', '')
inline = []
for name in NAMES:
    component = (OUT / (name + '.qml')).read_text(encoding='utf-8')
    component = re.sub(r'^import QtQuick 2\.5\s*', '', component)
    # Inline Qt 6 components keep each original component's private id scope.
    inline.append('    component ' + name + ': ' + component)
qml = replace_once(qml, '    id: root\n', '    id: root\n' + '\n'.join(inline) + '\n')
def translate(match):
    result = translator.translate('MENUS', match[1])
    assert result
    return json.dumps(result, ensure_ascii=False)
qml = re.sub(r'qsTranslate\("MENUS", "([^"]+)"\)', translate, qml)
test_icon = 'data:image/svg+xml;base64,' + base64.b64encode((D / 'menu-candidate/assets/customTest.svg').read_bytes()).decode()
qml = replace_once(qml, 'source: "assets/" + modelData.key + ".svg"',
                   'source: modelData.key === "customTest" ? ' + json.dumps(test_icon) + ' : "qrc:/icons/" + modelData.key + ".svg"')
(OUTPUT / 'x2d-menu-v1-main.qml').write_text(qml, encoding='utf-8', newline='\n')
qml_hash = sha(qml.encode())
gate_hash = sha((D / 'libx2d_menu_gate.so').read_bytes())
script = (D / 'boot_preview_loader.sh').read_text(encoding='ascii')
script = replace_once(script, '# Resident callback is the previously verified independent-preview RAM patch.',
                      '# Custom menu visual candidate. Settings bridge is not connected yet.')
anchor = '# Wait at most one minute for the original GUI and display server.'
script = replace_once(script, anchor,
    f'hashok /system/lib64/libx2d_menu_gate.so {gate_hash} || fail GATE_HASH\n'
    f'hashok /system/etc/x2d-menu-v1-main.qml {qml_hash} || fail MENU_HASH\n\n' + anchor)
script = replace_once(script, '/system/bin/camera-gui -platform wayland-egl --fullscreen --bus none --imagetest -u',
    'X2D_MENU_CHILD=1 LD_PRELOAD=/system/lib64/libx2d_menu_gate.so /system/bin/camera-gui -platform wayland-egl --fullscreen --bus none --imagetest -u')
anchor = 'pagebase=$(hexnum "$pagehex");'
script = replace_once(script, anchor, '''i=0
while [ ! -e "$d/menu-ready" ] && [ "$i" -lt 30 ]; do
    samepage || fail GATE_CHILD_EXITED
    sleep 0.1; i=$((i+1))
done
[ "$(cat "$d/menu-ready" 2>/dev/null)" = READY ] || fail GATE_NOT_READY
''' + anchor)
old_url = b'qrc:/imagetest/qml/imagetest_main.qml'
new_url = b'file:/system/etc/x2d-menu-v1-main.qml'
assert len(old_url) == len(new_url) == 37
url_rva = 0x14e9f37
old_url_hash = sha(old_url + bytes([0]))
new_url_hash = sha(new_url + bytes([0]))
anchor = 'samepage || fail PAGE_CHANGED\n[ "$(memhash "$page_pid" "$cave" 352)"'
script = replace_once(script, anchor, f'''samepage || fail PAGE_CHANGED
url_address=$(add "$pagebase" "{url_rva}")
[ "$(memhash "$page_pid" "$url_address" 38)" = {old_url_hash} ] || fail URL_MISMATCH
printf %s '{new_url.decode()}' > "$d/menu-url"
busybox dd if="$d/menu-url" of="/proc/$page_pid/mem" bs=1 seek="$url_address" count=37 conv=notrunc 2>/dev/null || fail URL_WRITE
[ "$(memhash "$page_pid" "$url_address" 38)" = {new_url_hash} ] || fail URL_VERIFY
[ "$(memhash "$page_pid" "$cave" 352)"''')
script = replace_once(script, 'sleep 6\nsamepage || fail PAGE_EXITED',
                      'printf 1 > "$d/menu-go.tmp"; mv "$d/menu-go.tmp" "$d/menu-go"\nsleep 6\nsamepage || fail PAGE_EXITED')
if INPUT_ROUTE:
    start = script.index('while [ ! -e "$d/stop" ] && [ ! -e /blackbox/x2d-preview.disabled ]; do\n', script.index('shown=0; toggles=0;'))
    end = script.index('echo STOPPED > "$d/status"', start)
    script = script[:start] + (D / 'menu_input_loop.sh').read_text(encoding='ascii') + '\n' + script[end:]
(OUTPUT / 'boot_menu_candidate.sh').write_text(script, encoding='ascii', newline='\n')
manifest = dict(firmware='X2D 100C 4.2.0', deployed=False,
                status='visual candidate; original settings bridge remains unimplemented',
                oldBootLoaderHash=sha((D / 'boot_preview_loader.sh').read_bytes()),
                files=[dict(source='../libx2d_menu_gate.so', target='/system/lib64/libx2d_menu_gate.so', sha256=gate_hash),
                       dict(source='x2d-menu-v1-main.qml', target='/system/etc/x2d-menu-v1-main.qml', sha256=qml_hash),
                       dict(source='boot_menu_candidate.sh', target='/system/etc/x2d-menu-candidate.sh', sha256=sha(script.encode()))])
(OUTPUT / 'package.json').write_text(json.dumps(manifest, indent=2), encoding='ascii')
print(json.dumps(manifest))
