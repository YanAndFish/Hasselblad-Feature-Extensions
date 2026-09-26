#!/system/bin/sh
set -eu
d=/tmp/x2d-preview
[ "$(cat "$d/status")" = READY ]
[ ! -e "$d/native-state" ] && [ ! -e "$d/native-inspect.log" ]
fail() { echo "$1"; exit 20; }
add() { awk -v a="$1" -v b="$2" 'BEGIN {printf "%.0f\n", a+b}'; }
hexnum() { awk -v h="$1" 'BEGIN {n=0; for(i=1;i<=length(h);i++) n=n*16+index("0123456789abcdef",substr(h,i,1))-1; printf "%.0f\n",n}'; }
startof() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null; }
readnum() {
    n=$(dd if="/proc/$1/mem" bs=1 skip="$2" count="$3" 2>/dev/null | od -An -tu"$3" | tr -d ' \n')
    case "$n" in ''|*[!0-9]*) return 1;; esac
    printf '%s\n' "$n"
}
memhash() { dd if="/proc/$1/mem" bs=1 skip="$2" count="$3" 2>/dev/null | sha256sum | cut -d ' ' -f1; }

for key in gui_pid gui_start page_pid page_start mailbox visible_address; do
 value=$(sed -n "s/^$key=//p" "$d/state")
 case "$value" in ''|*[!0-9]*) exit 40;; esac
 eval "$key=$value"
done
[ "$(startof "$gui_pid")" = "$gui_start" ] && [ "$(startof "$page_pid")" = "$page_start" ]
basehex=$(awk '$2=="r-xp" && $3=="00000000" && $NF=="/system/bin/camera-gui" {split($1,v,"-");print v[1]}' "$d/gui.maps")
case "$basehex" in ''|*[!0-9a-f]*) exit 41;; esac
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


[ "$original_function" = 0 ] || fail FRONT_NOT_OWNED
(set -C; : > "$d/native-state")
printf 'gui_pid=%s\ngui_start=%s\npage_pid=%s\npage_start=%s\nmailbox=%s\nvisible_address=%s\nmap_pointer_address=%s\nmap_pointer=%s\nkey_address=%s\nmodifiers_address=%s\nfunction_address=%s\n' "$gui_pid" "$gui_start" "$page_pid" "$page_start" "$mailbox" "$visible_address" "$map_pointer_address" "$map_pointer" "$key_address" "$modifiers_address" "$function_address" > "$d/native-state"
X2D_MENU_INPUT_MODE=inspect LD_PRELOAD=/system/lib64/libx2d_menu_input.so /system/bin/camera-test --version
cat "$d/native-inspect.log"
