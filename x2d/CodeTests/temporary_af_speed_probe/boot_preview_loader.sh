#!/system/bin/sh
# First-generation X2D 4.2.0 only. Runtime addresses are discovered each boot.
# Resident callback is the previously verified independent-preview RAM patch.
set -u
export PATH=/system/bin:/system/xbin:/sbin
unset LD_PRELOAD X2D_PREVIEW_BOOT
a=/system/etc/x2d-preview
d=/tmp/x2d-preview
inspect=0
if [ "${1:-}" = --inspect ]; then d=/tmp/x2d-preview-inspect; inspect=1; fi
[ ! -e /blackbox/x2d-preview.disabled ] || exit 0
mkdir -m 700 "$d" || exit 10
exec >"$d/loader.log" 2>&1
echo INITIALIZING > "$d/status"
echo $$ > "$d/loader.pid"
gui_pid=0; gui_start=0; page_pid=0; page_start=0; modified=0
# Android mksh arithmetic is 32-bit here; use exact double integers below 2^53.
add() { awk -v a="$1" -v b="$2" 'BEGIN {printf "%.0f\n", a+b}'; }
hexnum() { awk -v h="$1" 'BEGIN {n=0; for(i=1;i<=length(h);i++) n=n*16+index("0123456789abcdef",substr(h,i,1))-1; printf "%.0f\n",n}'; }
startof() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null; }
readnum() {
    n=$(dd if="/proc/$1/mem" bs=1 skip="$2" count="$3" 2>/dev/null | od -An -tu"$3" | tr -d ' \n')
    case "$n" in ''|*[!0-9]*) return 1;; esac
    printf '%s\n' "$n"
}
memhash() { dd if="/proc/$1/mem" bs=1 skip="$2" count="$3" 2>/dev/null | sha256sum | cut -d ' ' -f1; }
samegui() { [ "$gui_pid" != 0 ] && [ "$(startof "$gui_pid")" = "$gui_start" ]; }
samemap() {
    samegui && [ "$(readnum "$gui_pid" "$map_pointer_address" 8)" = "$map_pointer" ] &&
    [ "$(readnum "$gui_pid" "$key_address" 4)" = 70 ] &&
    [ "$(readnum "$gui_pid" "$modifiers_address" 4)" = 0 ]
}
samepage() { [ "$page_pid" != 0 ] && [ -n "$page_start" ] && [ "$(startof "$page_pid")" = "$page_start" ]; }
cleanup() {
    trap - EXIT HUP INT TERM
    if samepage; then kill -TERM "$page_pid" 2>/dev/null || :; fi
    if [ "$modified" = 1 ]; then
        if samemap && [ "$(readnum "$gui_pid" "$function_address" 1)" = 0 ]; then
            busybox dd if="$d/original-byte" of="/proc/$gui_pid/mem" bs=1 seek="$function_address" count=1 conv=notrunc 2>/dev/null
            if [ "$(readnum "$gui_pid" "$function_address" 1)" = "$original_function" ]; then
                echo ORIGINAL_KEY_RESTORED >> "$d/loader.log"
            else echo KEY_RESTORE_FAILED >> "$d/loader.log"; fi
        else echo KEY_RESTORE_SKIPPED_IDENTITY_CHANGED >> "$d/loader.log"; fi
    fi
}
trap cleanup EXIT
trap 'echo STOPPED > "$d/status"; exit 0' HUP INT TERM
fail() { echo "$1" > "$d/status"; exit 20; }
hashok() { [ "$(sha256sum "$1" | cut -d ' ' -f1)" = "$2" ]; }
hashok /system/bin/camera-gui 16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0 || fail UNSUPPORTED_GUI
hashok "$a-code.bin" e26bf2464af29311790c2e767a3b378a1dd99ad74866711a1ec617272257f8fb || fail CODE_HASH
hashok "$a-hook.bin" f90186bfe664b507b6f0c867269d877bee06c69dd874960a8d6d08ed29afa202 || fail HOOK_HASH
hashok "$a-page.png" 8d4de634bebc8268f6f24eec8744592600a9175dc3f0afc27499efa4cec0b928 || fail IMAGE_HASH

# Wait at most one minute for the original GUI and display server.
i=0
while [ "$i" -lt 60 ]; do
    [ ! -e /blackbox/x2d-preview.disabled ] && [ ! -e "$d/stop" ] || fail DISABLED
    candidates=$(pidof camera-gui); set -- $candidates
    if [ "$#" = 1 ] && [ "$(getprop init.svc.camera-gui)" = running ] && [ -S /tmp/wayland-0 ]; then
        gui_pid=$1
        cmd=$(tr '\000' ' ' < "/proc/$gui_pid/cmdline")
        case "$cmd" in *--imagetest*|*--confirmtest*) fail UNEXPECTED_GUI;; esac
        [ "$cmd" = '/system/bin/camera-gui -platform wayland-egl --fullscreen ' ] || fail GUI_COMMAND
        gui_start=$(startof "$gui_pid")
        [ -n "$gui_start" ] && break
    fi
    sleep 1; i=$((i+1))
done
[ "$i" -lt 60 ] || fail GUI_NOT_READY
cat "/proc/$gui_pid/maps" > "$d/gui.maps"
basehex=$(awk '$2=="r-xp" && $3=="00000000" && $NF=="/system/bin/camera-gui" {split($1,v,"-");print v[1]}' "$d/gui.maps")
case "$basehex" in ''|*[!0-9a-f]*) fail GUI_BASE;; esac
base=$(hexnum "$basehex")
rw() {
    awk -v a="$1" -v size="$2" '
    function hx(h, n,i) {n=0;for(i=1;i<=length(h);i++)n=n*16+index("0123456789abcdef",substr(h,i,1))-1;return n}
    $2=="rw-p" {split($1,r,"-");if(a>=hx(r[1]) && a+size<=hx(r[2]))ok=1}
    END {exit !ok}' "$d/gui.maps"
}
# Key mapping may be initialized after the GUI service reports running.
i=0
while [ "$i" -lt 30 ]; do
    instance=$(readnum "$gui_pid" "$(add "$base" "35375160")" 8) || fail INSTANCE_READ
    if [ "$instance" != 0 ]; then break; fi
    sleep 1; i=$((i+1))
done
cat "/proc/$gui_pid/maps" > "$d/gui.maps"
rw "$instance" 32 || fail INSTANCE_RANGE
[ "$(readnum "$gui_pid" "$instance" 8)" = "$(add "$base" "34428448")" ] || fail KEY_HANDLER_TYPE
map_pointer_address=$(add "$instance" "16")
map_pointer=$(readnum "$gui_pid" "$map_pointer_address" 8) || fail MAP_READ
rw "$map_pointer" 24 || fail MAP_RANGE
node=$(readnum "$gui_pid" "$(add "$map_pointer" "16")" 8) || fail ROOT_READ
i=0; found=0
while [ "$i" -lt 16 ] && [ "$node" != 0 ]; do
    rw "$node" 40 || fail NODE_RANGE
    key=$(readnum "$gui_pid" "$(add "$node" "28")" 4) || fail KEY_READ
    if [ "$key" = 70 ]; then found=1; break; fi
    if [ "$key" -lt 70 ]; then offset=8; else offset=0; fi
    node=$(readnum "$gui_pid" "$(add "$node" "$offset")" 8) || fail NEXT_READ
    i=$((i+1))
done
[ "$found" = 1 ] || fail FRONT_KEY_NOT_FOUND
key_address=$(add "$node" "28"); function_address=$(add "$node" "32"); modifiers_address=$(add "$node" "36")
[ "$(readnum "$gui_pid" "$modifiers_address" 4)" = 0 ] || fail KEY_MODIFIERS
original_function=$(readnum "$gui_pid" "$function_address" 4) || fail FUNCTION_READ
[ "$original_function" -le 43 ] || fail UNKNOWN_FUNCTION

input=''; count=0
for namefile in /sys/class/input/event*/device/name; do
    [ "$(cat "$namefile" 2>/dev/null)" = gui_buttons ] || continue
    ev=${namefile%/device/name}; ev=${ev##*/}
    input=/dev/input/$ev; count=$((count+1))
done
[ "$count" = 1 ] && [ -c "$input" ] || fail INPUT_IDENTITY
exec 3<"$input" || fail INPUT_OPEN
if [ "$inspect" = 1 ]; then
    printf 'gui_pid=%s\noriginal_function=%s\ninput=%s\n' "$gui_pid" "$original_function" "$input" > "$d/state"
    echo INSPECT_OK_NO_CAMERA_MEMORY_WRITES > "$d/status"
    exit 0
fi

# Preview process is our child, not the original camera-gui instance.
export XDG_RUNTIME_DIR=/tmp XDG_CACHE_HOME="$d" QT_QPA_FONTDIR=/system/lib64/qt/lib/fonts QML_DISABLE_DISK_CACHE=1
/system/bin/camera-gui -platform wayland-egl --fullscreen --bus none --imagetest -u "file:$a-page.png" -o 2147483647 -e 2147483646 --timeout 5 > "$d/page.log" 2>&1 &
page_pid=$!; page_start=$(startof "$page_pid")
[ "$page_pid" != "$gui_pid" ] && [ -n "$page_start" ] || fail PAGE_IDENTITY
i=0; pagehex=''
while [ "$i" -lt 20 ]; do
    pagehex=$(awk '$2=="r-xp" && $3=="00000000" && $NF=="/system/bin/camera-gui" {split($1,v,"-");print v[1]}' "/proc/$page_pid/maps" 2>/dev/null)
    [ -z "$pagehex" ] || break
    sleep 0.1; i=$((i+1))
done
case "$pagehex" in ''|*[!0-9a-f]*) fail PAGE_BASE;; esac
pagebase=$(hexnum "$pagehex"); cave=$(add "$pagebase" "11368136"); hook=$(add "$pagebase" "3358656"); mailbox=$(add "$cave" "272")
samepage || fail PAGE_CHANGED
[ "$(memhash "$page_pid" "$cave" 352)" = 51ebe767ad7affbaf9a81554dbe7102a42ee2d947816affa87d752acfe8e4e5d ] || fail CAVE_MISMATCH
[ "$(memhash "$page_pid" "$hook" 4)" = 33ce45a15dc26f7dee75be44659cb5353eccb51d6abed44d4cb74ab294a61b6a ] || fail PAGE_HOOK_MISMATCH
busybox dd if="$a-code.bin" of="/proc/$page_pid/mem" bs=1 seek="$cave" count=352 conv=notrunc 2>/dev/null || fail CODE_WRITE
[ "$(memhash "$page_pid" "$cave" 352)" = e26bf2464af29311790c2e767a3b378a1dd99ad74866711a1ec617272257f8fb ] || fail CODE_VERIFY
busybox dd if="$a-hook.bin" of="/proc/$page_pid/mem" bs=1 seek="$hook" count=4 conv=notrunc 2>/dev/null || fail HOOK_WRITE
[ "$(memhash "$page_pid" "$hook" 4)" = f90186bfe664b507b6f0c867269d877bee06c69dd874960a8d6d08ed29afa202 ] || fail HOOK_VERIFY
sleep 6
samepage || fail PAGE_EXITED
[ "$(readnum "$page_pid" "$(add "$pagebase" "35453024")" 8)" = 1 ] || fail WINDOW_COUNT
array=$(readnum "$page_pid" "$(add "$pagebase" "35453016")" 8) || fail WINDOW_ARRAY
window=$(readnum "$page_pid" "$array" 8) || fail WINDOW_READ
private=$(readnum "$page_pid" "$(add "$window" "8")" 8) || fail WINDOW_PRIVATE
visible_address=$(add "$private" "144")
[ "$(readnum "$page_pid" "$visible_address" 1)" = 0 ] || fail PRELOAD_NOT_HIDDEN
samemap && [ "$(readnum "$gui_pid" "$function_address" 4)" = "$original_function" ] || fail MAP_CHANGED
dd if="/proc/$gui_pid/mem" of="$d/original-byte" bs=1 skip="$function_address" count=1 2>/dev/null || fail BACKUP_FAILED
modified=1
busybox dd if=/dev/zero of="/proc/$gui_pid/mem" bs=1 seek="$function_address" count=1 conv=notrunc 2>/dev/null || fail KEY_WRITE
[ "$(readnum "$gui_pid" "$function_address" 1)" = 0 ] || fail KEY_VERIFY
printf '\000' > "$d/hide"; printf '\001' > "$d/show"
printf 'gui_pid=%s\ngui_start=%s\npage_pid=%s\npage_start=%s\nmailbox=%s\nvisible_address=%s\ninput=%s\noriginal_function=%s\n' "$gui_pid" "$gui_start" "$page_pid" "$page_start" "$mailbox" "$visible_address" "$input" "$original_function" > "$d/state"
echo READY > "$d/status"
shown=0; toggles=0; last_check=-1
while [ ! -e "$d/stop" ] && [ ! -e /blackbox/x2d-preview.disabled ]; do
    if [ "$SECONDS" != "$last_check" ]; then
        samemap && samepage || fail PROCESS_OR_MAPPING_CHANGED
        [ "$(readnum "$gui_pid" "$function_address" 1)" = 0 ] || fail BINDING_CHANGED
        last_check=$SECONDS
    fi
    words=$(timeout 1 dd bs=24 count=1 <&3 2>/dev/null | od -An -tu4); set -- $words
    [ "$#" = 6 ] || continue
    [ "$5" = 2162689 ] && [ "$6" = 1 ] || continue
    samepage || fail PAGE_CHANGED
    if [ "$shown" = 0 ]; then next=1; value=show; else next=0; value=hide; fi
    busybox dd if="$d/$value" of="/proc/$page_pid/mem" bs=1 seek="$mailbox" count=1 conv=notrunc 2>/dev/null || fail TOGGLE_WRITE
    shown=$next; toggles=$((toggles+1))
    printf 'visible_request=%s\ntoggles=%s\n' "$shown" "$toggles" > "$d/events"
done
echo STOPPED > "$d/status"
exit 0
