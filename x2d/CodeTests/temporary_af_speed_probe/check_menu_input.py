"""Run the real lifecycle shell functions against camera/window boundaries."""
import json
from pathlib import Path
import subprocess

D = Path(__file__).resolve().parent
out = D / 'input-candidate'
text = (D / 'menu_input_loop.sh').read_text()
functions = text[:text.index('\nwhile [ ! -e "$d/stop"')]
checks = r'''
set -eu
d="$PWD/x2d/CodeTests/temporary_af_speed_probe/input-candidate/mock"
mkdir -p "$d"
shown=0
samegui() { return 0; }
samepage() { return 0; }
cleanup() { echo CLEANUP >> "$d/trace"; }
get_camera_value() { read camera_value < "$d/$1"; }
set_liveview() {
    echo "liveview:$1" >> "$d/trace"
    [ ! -e "$d/fail-command" ] || return 1
    [ ! -e "$d/stall" ] || return 0
    if [ "$1" = true ]; then echo 1 > "$d/live_view_state"
    else echo 0 > "$d/live_view_state"; fi
}
set_page() { echo "page:$1" >> "$d/trace"; }
reset_case() {
    : > "$d/trace"; : > "$d/page.log"; : > "$d/lifecycle.log"
    echo 1 > "$d/live_view_state"; echo 0 > "$d/exposure_status"
    owns_liveview_stop=0; shown=0
    rm -f "$d/fail-command" "$d/stall"
}
reset_case
open_menu
[ "$shown" = 0 ] && [ "$owns_liveview_stop" = 0 ]
[ "$(cat "$d/trace")" = 'liveview:false' ]
open_menu
[ "$shown" = 1 ] && [ "$owns_liveview_stop" = 0 ]
close_menu
[ "$(tail -n 2 "$d/trace")" = "$(printf 'page:show\npage:hide')" ]
! grep -q liveview:true "$d/trace"
reset_case
echo 0 > "$d/live_view_state"
open_menu; close_menu
! grep -q liveview: "$d/trace"
reset_case
echo 2 > "$d/exposure_status"
open_menu
[ "$shown" = 0 ] && [ ! -s "$d/trace" ]
reset_case
echo 3 > "$d/live_view_state"
open_menu
[ "$shown" = 0 ] && [ ! -s "$d/trace" ]
reset_case
touch "$d/fail-command"
open_menu
[ "$shown" = 0 ] && [ "$owns_liveview_stop" = 0 ]
input_cleanup
[ "$(tail -n 1 "$d/trace")" = CLEANUP ]
grep -q page:hide "$d/trace"
reset_case
touch "$d/stall"
open_menu
[ "$shown" = 0 ] && [ "$owns_liveview_stop" = 0 ]
input_cleanup
grep -q page:hide "$d/trace"
reset_case
open_menu
echo 1 > "$d/live_view_state"
restore_liveview
[ "$(grep -c liveview: "$d/trace")" = 1 ]
reset_case
open_menu
input_cleanup
[ "$(tail -n 2 "$d/trace")" = "$(printf 'page:hide\nCLEANUP')" ]
! grep -q liveview:true "$d/trace"
trap - EXIT HUP INT TERM
echo LIFECYCLE_CASES_PASSED
'''
test = out / 'check-lifecycle.sh'
test.write_text(functions + '\n' + checks, newline='\n')
bash = 'C:/Program Files/Git/bin/bash.exe'
subprocess.run([bash, '-n', str(out / 'boot_menu_candidate.sh')], check=True)
subprocess.run([bash, str(test)], check=True)
(out / 'lifecycle-validation.json').write_text(json.dumps({
    'deviceAccesses': 0, 'shellSyntax': True,
    'cases': ['first-press-parameter-only', 'second-press-menu', 'hide-to-parameter-no-resume',
              'already-off-not-resumed', 'busy-skipped', 'transition-skipped',
              'declined-command-keeps-listener', 'stop-timeout-keeps-listener',
              'external-resume-not-repeated', 'cleanup-does-not-undo-intended-parameter-page'],
    'deviceValidated': False}, indent=2))
