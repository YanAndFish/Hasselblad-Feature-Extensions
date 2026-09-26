#!/system/bin/sh
startof() {
    IFS= read -r stat_line < "/proc/$1/stat" 2>/dev/null || return 1
    stat_tail=${stat_line##*) }
    set -- $stat_tail
    [ "$#" -ge 20 ] || return 1
    shift 19
    printf '%s\n' "$1"
}
readnum() {
    set -- $(dd if="/proc/$1/mem" bs=1 skip="$2" count="$3" 2>/dev/null | od -An -tu"$3")
    [ "$#" = 1 ] || return 1
    case "$1" in ''|*[!0-9]*) return 1;; esac
    printf '%s\n' "$1"
}
timing() {
    read timing_now timing_idle < /proc/uptime
    printf '%s %s\n' "$1" "$timing_now" >> "$d/timing.log"
}
camera_get() {
    camera_reply=$(dbus-send --system --print-reply --reply-timeout=1000 \
        --dest=com.hasselblad.camera /camera org.freedesktop.DBus.Properties.Get \
        string:com.hasselblad.camera "string:$1" 2>/dev/null) || return 1
    set -- $camera_reply
    while [ "$#" -ge 3 ]; do
        if [ "$#" = 3 ] && [ "$1" = variant ] && [ "$2" = int32 ]; then
            case "$3" in ''|*[!0-9]*) return 1;; esac
            printf '%s\n' "$3"; return 0
        fi
        shift
    done
    return 1
}

. /tmp/x2d-preview/state
startof "$page_pid"
readnum "$page_pid" "$visible_address" 1
camera_get live_view_state
camera_get exposure_status
