#!/system/bin/sh
export PATH=/system/bin:/system/xbin:/sbin
d=/tmp/x2d-preview
. "$d/state"
read_start() {
    IFS= read -r stat_line < "/proc/$1/stat" 2>/dev/null || return 1
    stat_tail=${stat_line##*) }
    set -- $stat_tail
    [ "$#" -ge 20 ] || return 1
    shift 19
    process_start=$1
}
samegui() { [ "$gui_pid" != 0 ] && read_start "$gui_pid" && [ "$process_start" = "$gui_start" ]; }
samepage() { [ "$page_pid" != 0 ] && read_start "$page_pid" && [ "$process_start" = "$page_start" ]; }
read_value() {
    dd if="/proc/$1/mem" bs=1 skip="$2" count="$3" 2>/dev/null | od -An -tu"$3" > "$d/read-number"
    read number extra < "$d/read-number" || return 1
    [ -z "$extra" ] || return 1
    case "$number" in ''|*[!0-9]*) return 1;; esac
}
samemap() {
    samegui && read_value "$gui_pid" "$map_pointer_address" 8 && [ "$number" = "$map_pointer" ] &&
    read_value "$gui_pid" "$key_address" 4 && [ "$number" = 70 ] &&
    read_value "$gui_pid" "$modifiers_address" 4 && [ "$number" = 0 ]
}
read_exit_request() {
    exit_request=''
    while IFS= read -r exit_line; do
        case "$exit_line" in *X2D_MENU_EXIT_REQUEST*) exit_request=$exit_line;; esac
    done < "$d/page.log"
}
timing() {
    read timing_now timing_idle < /proc/uptime
    printf '%s %s\n' "$1" "$timing_now" >> "$d/timing.log"
}
get_camera_value() {
    dbus-send --system --print-reply --reply-timeout=1000 \
        --dest=com.hasselblad.camera /camera org.freedesktop.DBus.Properties.Get \
        string:com.hasselblad.camera "string:$1" > "$d/camera-reply" 2>/dev/null || return 1
    while read -r camera_line; do
        set -- $camera_line
        if [ "$#" = 3 ] && [ "$1" = variant ] && [ "$2" = int32 ]; then
            case "$3" in ''|*[!0-9]*) return 1;; esac
            camera_value=$3; return 0
        fi
    done < "$d/camera-reply"
    return 1
}
stamp() { read now unused < /proc/uptime; }
report() { stamp; awk -v name="$1" -v before="$before" -v after="$now" 'BEGIN {printf "%s %.0f ms\n",name,(after-before)*1000}'; }
i=0
while [ "$i" -lt 3 ]; do
 stamp; before=$now
 samegui && samepage || exit 31
 report both_identities
 stamp; before=$now
 get_camera_value live_view_state || exit 32
 report parsed_liveview_query
 stamp; before=$now
 get_camera_value exposure_status || exit 33
 report parsed_exposure_query
 stamp; before=$now
 read_exit_request
 report scan_exit_log
 stamp; before=$now
 read_value "$page_pid" "$visible_address" 1 || exit 34
 report parsed_visibility
 i=$((i+1))
done