"""独立页面提前创建；保持原生热路径及原厂 GUI 服务不变。"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
D=Path(__file__).resolve().parent
N=D/'native-input-candidate'
O=D/'native-early-boot-candidate'
O.mkdir(exist_ok=True)
s=(N/'boot_menu_native.sh').read_text()
# Only the dependency-wait loop changes cadence; keep its one-minute bound.
wait_a=s.index('# Wait at most one minute')
wait_b=s.index('cat "/proc/$gui_pid/maps"',wait_a)
wait=s[wait_a:wait_b].replace('"$i" -lt 60','"$i" -lt 600').replace('sleep 1;','sleep 0.1;')
s=s[:wait_a]+wait+s[wait_b:]
begin=s.index('# Earlier startup:')
end=s.index('if [ "$inspect" = 1 ]; then',begin)
mapping=s[begin:end]
s=s[:begin]+'''resolve_front() {
'''+mapping+'''}
'''+s[end:]
s=s.replace('if [ "$inspect" = 1 ]; then\n', 'if [ "$inspect" = 1 ]; then\n    resolve_front\n',1)
assert s.count('\nsamemap && [ "$(readnum')==1
s=s.replace('\nsamemap && [ "$(readnum','\nphase HIDDEN_WINDOW_READY\nresolve_front\nphase FRONT_MAP_READY\nsamemap && [ "$(readnum',1)
s=s.replace('echo INITIALIZING > "$d/status"', '''phase() { read -r boot_time boot_idle < /proc/uptime; printf '%s %s\\n' "$boot_time" "$1" >> "$d/boot-timing.log"; }
phase LOADER_ENTER
echo INITIALIZING > "$d/status"''',1)
s=s.replace('# Wait at most one minute','phase FILES_VERIFIED\n# Wait at most one minute',1)
s=s.replace('[ "$i" -lt 600 ] || fail GUI_NOT_READY','[ "$i" -lt 600 ] || fail GUI_NOT_READY\nphase ORIGINAL_GUI_IDENTIFIED',1)
s=s.replace('page_pid=$!; page_start=', 'page_pid=$!; phase PAGE_SPAWNED; page_start=',1)
s=s.replace('[ "$(cat "$d/menu-ready" 2>/dev/null)" = READY ] || fail GATE_NOT_READY','[ "$(cat "$d/menu-ready" 2>/dev/null)" = READY ] || fail GATE_NOT_READY\nphase PAGE_GATE_READY',1)
s=s.replace('printf 1 > "$d/menu-go.tmp"','phase PAGE_PATCH_READY\nprintf 1 > "$d/menu-go.tmp"',1)
s=s.replace('echo READY_NATIVE > "$d/status"','echo READY_NATIVE > "$d/status"\nphase INPUT_READY',1)
# Use the same boot event as original camera-gui, not a queued property trigger.
rc=(N/'x2d-preview-loader.rc.candidate').read_text().replace('on property:init.svc.camera-gui=running','on post-fs')
(O/'boot_menu_early.sh').write_text(s,encoding='ascii',newline='\n')
(O/'x2d-preview-loader.rc').write_text(rc,encoding='ascii',newline='\n')
subprocess.run(['C:/Program Files/Git/bin/bash.exe','-n',str(O/'boot_menu_early.sh')],check=True)
# Ordering and inspect contract checks; full boot timing remains hardware work.
assert s.index('phase PAGE_SPAWNED')<s.index('phase HIDDEN_WINDOW_READY')<s.index('\nresolve_front\nphase FRONT_MAP_READY')
assert 'if [ "$inspect" = 1 ]; then\n    resolve_front' in s
assert s.index('exit 0\nfi\n\n# Preview process')<s.index('phase PAGE_SPAWNED')
files=[dict(source='boot_menu_early.sh',target='/system/etc/x2d-preview-loader.sh',old='46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb'),dict(source='x2d-preview-loader.rc',target='/system/etc/init/x2d-preview-loader.rc',old='d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc')]
for f in files:f['sha256']=hashlib.sha256((O/f['source']).read_bytes()).hexdigest()
(O/'package.json').write_text(json.dumps({'files':files,'bootValidated':False,'sourceFirmware':'X2D 100C 4.2.0','behavior':'create hidden page before waiting for original key mapping'},indent=2)+'\n')
changes={
 '059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721': files[0]['old'],
 '8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67': files[1]['old'],
 files[0]['old']:files[0]['sha256'], files[1]['old']:files[1]['sha256'],
 '/blackbox/x2d-native-stage':'/blackbox/x2d-early-menu-stage',
 'boot_menu_native.sh':'boot_menu_early.sh',
 'x2d-preview-loader.rc.candidate':'x2d-preview-loader.rc',
 '.before-native-input':'.before-early-menu',
 'NATIVE_ACTIVATE_OK':'EARLY_MENU_INSTALLED',
 'NATIVE_ROLLBACK_OK':'EARLY_MENU_ROLLED_BACK',
}
for before,after in [('native-activate.sh','early-install.sh'),('native-rollback.sh','early-rollback.sh')]:
    body=(N/before).read_text()
    body=re.sub('|'.join(re.escape(k) for k in changes),lambda m:changes[m[0]],body)
    (O/after).write_text(body,encoding='ascii',newline='\n')
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','-n',str(O/after)],check=True)
print('EARLY_BOOT_BUILT_NOT_INSTALLED')
