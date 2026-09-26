#!/bin/sh
set -eu
umask 077
r=/tmp/hbl-ui-full-r1
s=$r/state
units=/run/systemd/system
gui=$units/victory-gui.service.d/90-hbl-ui-resident.conf
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%h' "$1")" = 0:1 ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pid() { p=$(value "$1" MainPID);case "$p" in ''|0|*[!0-9]*) return 1;;esac;printf '%s\n' "$p"; }
verify_package() {
    [ "$(id -u)" = 0 ] && private "$r" && regular "$r/manifest.sha256" || return 1
    [ -z "${LD_PRELOAD:-}" ] && [ -z "${LD_LIBRARY_PATH:-}" ] && [ ! -s /etc/ld.so.preload ] || return 1
    (cd "$r"
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.-]+$/ || seen[$2]++ {bad=1} END {exit bad || NR!=8}' manifest.sha256 || exit 1
    while read -r digest file; do regular "$file" || exit 1;done < manifest.sha256
    sha256sum -c manifest.sha256 >/dev/null) || return 1
    sha256sum -c "$r/baseline.sha256" >/dev/null
}
clean_service() {
    role=$1
    [ "$(value "$role" FragmentPath)" = "/lib/systemd/system/$role.service" ] && [ -z "$(value "$role" DropInPaths)" ] || return 1
    # 还检查尚未 daemon-reload 的文件，避免重启时才载入别人的覆盖配置。
    for base in /etc/systemd/system /run/systemd/system /lib/systemd/system;do
        directory=$base/$role.service.d
        [ ! -L "$directory" ] || return 1
        for conf in "$directory"/*.conf;do absent "$conf" || return 1;done
    done
    systemctl is-active --quiet "$role" || return 1
    ! value "$role" Environment | grep -Eq '(LD_PRELOAD|LD_LIBRARY_PATH)=' || return 1
    p=$(pid "$role") || return 1
    ! tr '\000' '\n' < "/proc/$p/environ" | grep -Eq '^(LD_PRELOAD|LD_LIBRARY_PATH)='
}
health() {
    current=$(pid victory-gui) || return 1
    health_result=$("$r/ui-health" --require-ready) || return 1
    case "$health_result" in "ui-health-ready pid=$current system="*) ;; *) return 1;;esac
}
owned() {
    private "$s" && regular "$s/owner" && regular "$s/manifest.sha256" &&
    [ "$(cat "$s/owner")" = hbl-ui-resident-v1 ] && cmp -s "$s/manifest.sha256" "$r/manifest.sha256"
}
bus_unchanged() { clean_service msg2dbus-farm && [ "$(pid msg2dbus-farm)" = "$(cat "$s/bus.pid")" ]; }
owned_dropin() {
    regular "$gui" && regular "$s/gui.dropin" && cmp -s "$gui" "$s/gui.dropin" &&
    [ "$(value victory-gui DropInPaths)" = "$gui" ]
}
only_owned_files() {
    for base in /etc/systemd/system /run/systemd/system /lib/systemd/system;do
        directory=$base/victory-gui.service.d
        [ ! -L "$directory" ] || return 1
        for conf in "$directory"/*.conf;do
            absent "$conf" || [ "$conf" = "$gui" ] || return 1
        done
    done
}
gui_ready() {
    systemctl is-active --quiet victory-gui && owned_dropin && only_owned_files || return 1
    p=$(pid victory-gui) || return 1
    regular "$r/ui.status" && [ "$(cat "$r/ui.status")" = "ui-resident-ready-resources6-components5-pools3-pages23-rows pid=$p" ] || return 1
    grep -Fq "$r/libhbl-ui-resident.so" "/proc/$p/maps" && bus_unchanged && health
}
wait_ready() {
    limit=10;[ "$1" != gui_ready ] || limit=40
    n=0
    while [ "$n" -lt "$limit" ];do
        n=$((n+1))
        if [ "$1" = gui_ready ];then
            if ! regular "$r/ui.status";then sleep 1;continue;fi
            case "$(cat "$r/ui.status")" in
                ui-resident-*-failed*|ui-resident-pool-timeout*) return 1;;
                ui-resident-pool-pending*) sleep 1;continue;;
            esac
        fi
        "$1" 2>/dev/null && return 0
        sleep 1
    done
    return 1
}
stop_gui() {
    old=$(pid victory-gui 2>/dev/null || :)
    systemctl stop victory-gui || return 1
    ! systemctl is-active --quiet victory-gui || return 1
    [ -z "$old" ] || [ ! -d "/proc/$old" ]
}
