"""离线组装原生控制/较早开机候选，不访问相机，不覆盖现有部署包。"""
import hashlib
import json
from pathlib import Path
import subprocess
D=Path(__file__).resolve().parent
OUT=D/'native-input-candidate'
build=json.loads((OUT/'build.json').read_text())
fast=json.loads((OUT/'resident-page-candidate.json').read_text())
baseline=json.loads((D/'resident-page-candidate.json').read_text())
script=(D/'input-candidate/boot_menu_candidate.sh').read_text()
assert 'PARAMETER_PAGE_READY' in script, 'Expected current two-step baseline'
anchor=script.index('shown=0; toggles=0;')
script=script[:anchor]
# With the earlier service trigger, an allocated handler can precede its map.
# Wait for the existing map root; retain the full range/type/key checks below.
wait_begin=script.index('# Key mapping may be initialized')
wait_end=script.index('cat "/proc/$gui_pid/maps"',wait_begin)
script=script[:wait_begin]+'''# Earlier startup: await handler, map, and root without modifying them.
i=0
while [ "$i" -lt 150 ]; do
    samegui || fail GUI_CHANGED
    [ ! -e /blackbox/x2d-preview.disabled ] && [ ! -e "$d/stop" ] || fail DISABLED
    instance=$(readnum "$gui_pid" "$(add "$base" "35375160")" 8) || instance=0
    early_map=0; early_root=0
    if [ "$instance" != 0 ]; then
        early_map=$(readnum "$gui_pid" "$(add "$instance" "16")" 8) || early_map=0
    fi
    if [ "$early_map" != 0 ]; then
        early_root=$(readnum "$gui_pid" "$(add "$early_map" "16")" 8) || early_root=0
    fi
    [ "$early_root" = 0 ] || break
    sleep 0.1; i=$((i+1))
done
[ "$i" -lt 150 ] || fail KEY_MAP_NOT_READY
'''+script[wait_end:]
script=script.replace('modified=0\n','modified=0; native_pid=0; native_start=0\n',1)
script=script.replace('    trap - EXIT HUP INT TERM\n', '''    trap - EXIT HUP INT TERM
    if [ "$native_pid" != 0 ] && [ "$native_start" != 0 ] && [ -n "$native_start" ] && [ "$(startof "$native_pid")" = "$native_start" ]; then
        kill -TERM "$native_pid" 2>/dev/null || :
        wait "$native_pid" 2>/dev/null || :
    fi
''',1)
script=script.replace('echo READY > "$d/status"','echo NATIVE_STARTING > "$d/status"')
assert script.count('sleep 6\nsamepage || fail PAGE_EXITED')==1
script=script.replace('sleep 6\nsamepage || fail PAGE_EXITED', '''# Wait for the actual hidden window instead of a fixed six-second delay.
i=0
while [ "$i" -lt 100 ]; do
    samepage || fail PAGE_EXITED
    windows=$(readnum "$page_pid" "$(add "$pagebase" "35453024")" 8) || windows=0
    [ "$windows" != 1 ] || break
    sleep 0.05; i=$((i+1))
done
samepage || fail PAGE_EXITED''')
assert baseline['length']==fast['length']==352 and baseline['mailbox']==fast['mailbox']
script=script.replace('"$a-code.bin"','/system/etc/x2d-preview-native-code.bin')
assert script.count(baseline['codeHash'])==2
script=script.replace(baseline['codeHash'],fast['codeHash'])
guard=f'hashok /system/lib64/libx2d_menu_input.so {build["sha256"]} || fail NATIVE_HASH\n'
for dep in build['dependencies']:
    guard+=f'hashok {dep["path"]} {dep["sha256"]} || fail NATIVE_DEPENDENCY_HASH\n'
script=script.replace('# Wait at most one minute',guard+'\n# Wait at most one minute',1)
script+='''# Only one native input controller owns the front-key FD after setup.
exec 3<&-
printf 'gui_pid=%s\\ngui_start=%s\\npage_pid=%s\\npage_start=%s\\nmailbox=%s\\nvisible_address=%s\\nmap_pointer_address=%s\\nmap_pointer=%s\\nkey_address=%s\\nmodifiers_address=%s\\nfunction_address=%s\\n' "$gui_pid" "$gui_start" "$page_pid" "$page_start" "$mailbox" "$visible_address" "$map_pointer_address" "$map_pointer" "$key_address" "$modifiers_address" "$function_address" > "$d/native-state"
X2D_MENU_INPUT_MODE=run LD_PRELOAD=/system/lib64/libx2d_menu_input.so /system/bin/camera-test --version > "$d/native-host.log" 2>&1 &
native_pid=$!
native_start=$(startof "$native_pid")
[ -n "$native_start" ] || fail NATIVE_START_FAILED
printf 'native_pid=%s\\nnative_start=%s\\n' "$native_pid" "$native_start" > "$d/native-process"
i=0
while [ "$i" -lt 1600 ]; do
    [ "$(startof "$native_pid")" = "$native_start" ] || fail NATIVE_START_FAILED
    if grep -q NATIVE_READY "$d/native.log" 2>/dev/null; then break; fi
    sleep 0.05; i=$((i+1))
done
[ "$i" -lt 1600 ] || fail NATIVE_START_TIMEOUT
echo READY_NATIVE > "$d/status"
wait "$native_pid"
native_result=$?
echo NATIVE_EXITED > "$d/status"
exit "$native_result"
'''
(OUT/'boot_menu_native.sh').write_text(script,encoding='ascii',newline='\n')
rc=(D/'x2d-preview-loader.rc').read_text()
assert rc.count('on boot-late')==1
rc=rc.replace('on boot-late','on property:init.svc.camera-gui=running')
# Keep original service class/entry point. This property ordering still needs boot validation.
(OUT/'x2d-preview-loader.rc.candidate').write_text(rc,encoding='ascii',newline='\n')
files=[('libx2d_menu_input.so','/system/lib64/libx2d_menu_input.so'),
       ('resident-code.bin','/system/etc/x2d-preview-native-code.bin'),
       ('boot_menu_native.sh','/system/etc/x2d-preview-loader.sh'),
       ('x2d-preview-loader.rc.candidate','/system/etc/init/x2d-preview-loader.rc')]
subprocess.run(['C:/Program Files/Git/bin/bash.exe','-n',str(OUT/'boot_menu_native.sh')],check=True)
(OUT/'package.json').write_text(json.dumps({'deviceValidated':False,'installed':False,
 'files':[dict(source=s,target=t,sha256=hashlib.sha256((OUT/s).read_bytes()).hexdigest()) for s,t in files],
 'remaining':['native inspect on the actual camera','readiness versus first frame','repeated front-key and half-press tests',
              'hardware timing versus original menu','earlier init trigger boot test','installation/rollback transaction not yet implemented']},indent=2)+'\n')
print('NATIVE_PACKAGE_OFFLINE_ONLY')
