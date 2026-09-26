# Sourced by our own loader after its identity/hash checks and READY setup.
# Fixed 4.2.0 menu lifecycle: use the same live-view method as the factory QML.
# No persistent camera settings, focus, exposure or RF commands.
owns_liveview_stop=0
last_exit=''
# Hot-path process checks use shell builtins, retaining PID/start-time guards.
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
set_liveview() {
    dbus-send --system --print-reply --reply-timeout=1000 \
        --dest=com.hasselblad.camera /camera com.hasselblad.camera.set_live_view \
        "boolean:$1" >> "$d/lifecycle.log" 2>&1
}
set_page() {
    samepage || { echo PAGE_IDENTITY_LOST >> "$d/lifecycle.log"; return 1; }
    busybox dd if="$d/$1" of="/proc/$page_pid/mem" bs=1 seek="$mailbox" count=1 conv=notrunc 2>/dev/null || { echo PAGE_WRITE_FAILED >> "$d/lifecycle.log"; return 1; }
    want=0; [ "$1" = hide ] || want=1
    tries=0
    while [ "$tries" -lt 200 ]; do
        samepage || { echo PAGE_EXITED_WAITING >> "$d/lifecycle.log"; return 1; }
        read_value "$page_pid" "$visible_address" 1 || return 1
        actual=$number
        if [ "$actual" = "$want" ]; then
            printf 'PAGE_ACK want=%s polls=%s\n' "$want" "$tries" >> "$d/lifecycle.log"
            return 0
        fi
        sleep 0.01; tries=$((tries+1))
    done
    printf 'PAGE_TIMEOUT want=%s actual=%s mailbox=%s\n' "$want" "$actual" "$(readnum "$page_pid" "$mailbox" 1)" >> "$d/lifecycle.log"
    return 1
}
restore_liveview() {
    if [ "$owns_liveview_stop" = 1 ] && samegui; then
        get_camera_value live_view_state || return 1
        current=$camera_value
        case "$current" in 0|1|2|3|4) ;; *) return 1;; esac
        if [ "$current" = 0 ]; then set_liveview true || return 1; fi
        owns_liveview_stop=0
    fi
}
close_menu() {
    timing CLOSE_BEGIN
    # Front key now cycles control page <-> custom menu. Half-press owns liveview.
    set_page hide || return 1
    shown=0
    owns_liveview_stop=0
    timing CLOSE_DONE
    echo MENU_HIDDEN_TO_PARAMETER_PAGE >> "$d/lifecycle.log"
}
cover_menu() {
    set_page show || return 1
    shown=1
    # This host does not reliably deliver frameSwapped to the QML logger.
    # Visibility acknowledgement is sufficient; never block input on a log line.
    return 0
}
open_menu() {
    timing OPEN_BEGIN
    samegui && samepage || return 1
    get_camera_value live_view_state || return 1
    current=$camera_value
    case "$current" in 0|1) ;; *) echo OPEN_SKIPPED_TRANSITION >> "$d/lifecycle.log"; return 0;; esac
    get_camera_value exposure_status || return 1
    exposure=$camera_value
    case "$exposure" in 0|512) ;; *) echo OPEN_SKIPPED_CAMERA_BUSY >> "$d/lifecycle.log"; return 0;; esac
    if [ "$current" = 1 ]; then
        # First front-key press intentionally ends on the factory parameter page.
        # No custom surface is shown, and no future automatic resume is requested.
        owns_liveview_stop=1
        if ! set_liveview false; then
            echo PARAMETER_REQUEST_DECLINED_RECHECK >> "$d/lifecycle.log"
        fi
        tries=0
        while [ "$tries" -lt 15 ]; do
            get_camera_value live_view_state || return 1
            current=$camera_value
            [ "$current" != 0 ] || break
            case "$current" in 1|4) ;; *) owns_liveview_stop=0; return 0;; esac
            sleep 0.05; tries=$((tries+1))
        done
        owns_liveview_stop=0
        if [ "$current" = 0 ]; then
            echo PARAMETER_PAGE_READY >> "$d/lifecycle.log"
        else echo PARAMETER_PAGE_NOT_READY >> "$d/lifecycle.log"; fi
        timing PARAMETER_REQUEST_DONE
        return 0
    fi
    owns_liveview_stop=0
    read_exit_request; last_exit=$exit_request
    cover_menu || return 1
    timing VISIBLE_ACK
    echo MENU_SHOWN_LIVEVIEW_OFF >> "$d/lifecycle.log"
    timing OPEN_DONE
}
input_cleanup() {
    trap - EXIT HUP INT TERM
    if samepage; then set_page hide || :; fi
    restore_liveview || echo LIVEVIEW_RESTORE_FAILED >> "$d/lifecycle.log"
    cleanup
}
trap input_cleanup EXIT
trap 'echo STOPPED > "$d/status"; exit 0' HUP INT TERM
while [ ! -e "$d/stop" ] && [ ! -e /blackbox/x2d-preview.disabled ]; do
    if [ "$SECONDS" != "$last_check" ]; then
        samemap && samepage || fail PROCESS_OR_MAPPING_CHANGED
        read_value "$gui_pid" "$function_address" 1 && [ "$number" = 0 ] || fail BINDING_CHANGED
        last_check=$SECONDS
    fi
    # Private, one-shot installation checks use the identical lifecycle path.
    if [ -e "$d/request-show" ]; then
        rm -f "$d/request-show"
        [ "$shown" = 1 ] || open_menu || fail INPUT_OPEN_FAILED
    fi
    if [ -e "$d/request-hide" ]; then
        rm -f "$d/request-hide"
        [ "$shown" = 0 ] || close_menu || fail INPUT_CLOSE_FAILED
    fi
    if [ "$shown" = 1 ]; then
        get_camera_value live_view_state || fail INPUT_STATE_UNAVAILABLE
        current=$camera_value
        case "$current" in
            0) ;;
            1|2|3)
                # Original half-press/service transition wins. Do not restart AF.
                owns_liveview_stop=0
                set_page hide || fail INPUT_HIDE_FAILED
                shown=0
                echo ORIGINAL_LIVEVIEW_RESUMED >> "$d/lifecycle.log"
                ;;
            *) fail INPUT_STATE_UNAVAILABLE;;
        esac
        read_exit_request
        if [ "$shown" = 1 ] && [ "$exit_request" != "$last_exit" ]; then
            last_exit=$exit_request
            close_menu || fail INPUT_CLOSE_FAILED
        fi
    fi
    # Keep half-press exit responsive even when no front-key events arrive.
    timeout 0.1 dd bs=24 count=1 <&3 2>/dev/null | busybox od -An -tu4 -w24 > "$d/input-words"
    read event_s event_us event_hi event_unused event_key event_value event_extra < "$d/input-words" || continue
    [ -n "$event_value" ] && [ -z "$event_extra" ] || continue
    [ "$event_key" = 2162689 ] && [ "$event_value" = 1 ] || continue
    if [ "$shown" = 0 ]; then open_menu || fail INPUT_OPEN_FAILED
    else close_menu || fail INPUT_CLOSE_FAILED; fi
    toggles=$((toggles+1))
    printf 'visible_request=%s\ntoggles=%s\n' "$shown" "$toggles" > "$d/events"
done
