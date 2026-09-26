#!/system/bin/sh
# X2D 4.2.0: runtime key-map override and passive, non-exclusive input reader.
set -u
d=/tmp/afmf-resident
. "$d/state.sh"
readnum() { dd if="/proc/$gui_pid/mem" bs=1 skip="$1" count="$2" 2>/dev/null | od -An -tu"$2" | tr -d ' \n'; }
same_gui() { [ "$(awk '{print $22}' /proc/$gui_pid/stat 2>/dev/null)" = "$gui_start" ]; }
same_map() {
    same_gui && [ "$(readnum "$map_pointer_address" 8)" = "$map_pointer" ] &&
        [ "$(readnum "$key_address" 4)" = 70 ] &&
        [ "$(readnum "$modifiers_address" 4)" = 0 ]
}
restore() {
    trap - EXIT HUP INT TERM
    if [ -n "$page_pid" ] && kill -0 "$page_pid" 2>/dev/null; then
        kill -TERM "$page_pid" 2>/dev/null || :
    fi
    if same_map && [ "$(readnum "$function_address" 1)" = 0 ]; then
        busybox dd if="$d/original-byte" of="/proc/$gui_pid/mem" bs=1 seek="$function_address" count=1 conv=notrunc
        [ "$(readnum "$function_address" 1)" = "$original_function" ] && echo RESTORED > "$d/status"
    else
        echo NO_RESTORE_WRITE > "$d/status"
    fi
}
trap 'restore' EXIT
trap 'exit 0' HUP INT TERM
same_map || exit 20
[ "$(readnum "$function_address" 1)" = "$original_function" ] || exit 21
exec 3</dev/input/event6 || exit 22
dd if="/proc/$gui_pid/mem" of="$d/original-byte" bs=1 skip="$function_address" count=1 2>/dev/null || exit 23
busybox dd if=/dev/zero of="/proc/$gui_pid/mem" bs=1 seek="$function_address" count=1 conv=notrunc || exit 24
[ "$(readnum "$function_address" 1)" = 0 ] || exit 25
echo READY > "$d/status"
shown=0
printf "\000" > "$d/hide"
printf "\001" > "$d/show"
export XDG_RUNTIME_DIR=/tmp
export XDG_CACHE_HOME="$d"
export QT_QPA_FONTDIR=/system/lib64/qt/lib/fonts
export QML_DISABLE_DISK_CACHE=1
last_check=-1
while [ ! -e "$d/stop" ]; do
    # Avoid multiple /proc reads for DOWN/SYN/UP/SYN within the same second.
    if [ "$SECONDS" != "$last_check" ]; then
        same_map || exit 26
        [ "$(readnum "$function_address" 1)" = 0 ] || exit 27
        last_check=$SECONDS
    fi
    words=$(timeout 1 dd bs=24 count=1 <&3 2>/dev/null | od -An -tu4)
    set -- $words
    [ "$#" = 6 ] || continue
    # Linux input_event on this ARM64 system: timeval(16), type/code(4), value(4).
    [ "$5" = 2162689 ] || continue
    [ "$6" = 1 ] || continue
    [ "$(awk '{print $22}' /proc/$page_pid/stat 2>/dev/null)" = "$page_start" ] || exit 29
    if [ "$shown" = 0 ]; then next=1; value=show; else next=0; value=hide; fi
    busybox dd if="$d/$value" of="/proc/$page_pid/mem" bs=1 seek="$mailbox" count=1 conv=notrunc 2>/dev/null || exit 30
    shown=$next
    echo "VISIBLE_REQUEST=$shown" >> "$d/events.log"

done
