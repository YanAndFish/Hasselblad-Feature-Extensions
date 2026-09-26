#!/system/bin/sh
export PATH=/system/bin:/system/xbin:/sbin
d=/tmp/x2d-preview
. "$d/state"
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
stamp() { read now unused < /proc/uptime; }
report() { stamp; awk -v name="$1" -v before="$before" -v after="$now" 'BEGIN {printf "%s %.0f ms\n",name,(after-before)*1000}'; }
i=0
while [ "$i" -lt 3 ]; do
 stamp; before=$now
 [ "$(startof "$gui_pid")" = "$gui_start" ] && [ "$(startof "$page_pid")" = "$page_start" ] || exit 31
 report both_identities
 stamp; before=$now
 current=$(camera_get live_view_state)
 report parsed_liveview_query
 stamp; before=$now
 exposure=$(camera_get exposure_status)
 report parsed_exposure_query
 stamp; before=$now
 last_exit=$(grep X2D_MENU_EXIT_REQUEST "$d/page.log" | tail -n 1)
 report scan_exit_log
 stamp; before=$now
 visible=$(readnum "$page_pid" "$visible_address" 1)
 report parsed_visibility
 i=$((i+1))
done