#!/bin/sh
set -eu
umask 077
r=/tmp/hbl-ui-af
s=$r/state
af=/tmp/hbl-x1d-combined
afstate=$af/install-state
r4=/tmp/hbl-af-ui-r4
sockets=/tmp/hbl-af-settings
units=/run/systemd/system
gui=$units/victory-gui.service.d/99-hbl-ui-af.conf
afgui=$units/victory-gui.service.d/90-hbl-af-only.conf
fixgui=$units/victory-gui.service.d/95-hbl-af-ui-r4.conf
afbus=$units/msg2dbus-farm.service.d/90-hbl-af-only.conf
oldpreload=$af/libhbl-af-only.so:$r4/libhbl-af-ui.so
newpreload=$r/libhbl-ui-af.so:$oldpreload
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%h' "$1")" = 0:1 ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
socket_file() { [ -S "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:600 ]; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pid() { p=$(value "$1" MainPID);case "$p" in ''|0|*[!0-9]*) return 1;;esac;printf '%s\n' "$p"; }
environment() { tr '\000' '\n' < "/proc/$1/environ" | sed -n "s/^$2=//p"; }
verify_package() {
    [ "$(id -u)" = 0 ] && private "$r" && regular "$r/manifest.sha256" || return 1
    [ -z "${LD_PRELOAD:-}" ] && [ -z "${LD_LIBRARY_PATH:-}" ] && [ ! -s /etc/ld.so.preload ] || return 1
    (cd "$r"
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.-]+$/ || seen[$2]++ {bad=1} END {exit bad || NR<10}' manifest.sha256 || exit 1
    while read -r digest file;do regular "$file" || exit 1;done < manifest.sha256
    sha256sum -c manifest.sha256 >/dev/null) || return 1
    sha256sum -c "$r/baseline.sha256" >/dev/null
}
inherited_files() {
    private "$af" && private "$afstate" && private "$r4" && private "$sockets" || return 1
    # 清单由固定 f325 与 AF owner 的 r4 产物生成；任何陌生修订均拒绝。
    while read -r digest file;do regular "$file" || return 1;done < "$r/inherited.sha256"
    sha256sum -c "$r/inherited.sha256" >/dev/null || return 1
    regular "$afstate/owner" && [ "$(cat "$afstate/owner")" = hbl-af-only-v1 ] || return 1
    regular "$afstate/af-installed.sha256" && [ "$(cat "$afstate/af-installed.sha256")" = "$(cat "$r/af-receipt.expected")" ] || return 1
    regular "$afstate/hold.release" && [ "$(cat "$afstate/hold.release")" = release ] || return 1
    regular "$afstate/release.done" && regular "$afstate/ram.started" || return 1
    regular "$afgui" && regular "$fixgui" && regular "$afbus" || return 1
    cmp -s "$afgui" "$r/af-gui.expected" && cmp -s "$fixgui" "$r/r4-gui.expected" && cmp -s "$afbus" "$r/af-bus.expected"
}
only_dropins() {
    role=$1;mode=$2
    for base in /etc/systemd/system /run/systemd/system /lib/systemd/system;do
        directory=$base/$role.service.d;[ ! -L "$directory" ] || return 1
        for conf in "$directory"/*.conf;do
            absent "$conf" && continue
            if [ "$role" = victory-gui ];then
                [ "$conf" = "$afgui" ] || [ "$conf" = "$fixgui" ] || { [ "$mode" = integrated ] && [ "$conf" = "$gui" ]; } || return 1
            elif [ "$role" = msg2dbus-farm ];then [ "$conf" = "$afbus" ] || return 1
            else return 1;fi
        done
    done
}
service_base() {
    [ "$(value "$1" FragmentPath)" = "/lib/systemd/system/$1.service" ] && systemctl is-active --quiet "$1"
}
plain_service() {
    role=$1;service_base "$role" && only_dropins "$role" plain && [ -z "$(value "$role" DropInPaths)" ] || return 1
    p=$(pid "$role") || return 1
    [ -z "$(environment "$p" LD_PRELOAD)" ] && [ -z "$(environment "$p" LD_LIBRARY_PATH)" ]
}
af_bus_ready() {
    service_base msg2dbus-farm && only_dropins msg2dbus-farm af && [ "$(value msg2dbus-farm DropInPaths)" = "$afbus" ] || return 1
    p=$(pid msg2dbus-farm) || return 1
    [ "$(environment "$p" LD_PRELOAD)" = "$af/af/libhbl-af-bus.so" ] && [ "$(environment "$p" HBL_AF_SETTINGS_ENABLE)" = 1 ] || return 1
    grep -Fq "$af/af/libhbl-af-bus.so" "/proc/$p/maps" && socket_file "$sockets/backend.sock" || return 1
    regular "$sockets/backend-r2.status" && [ "$(cat "$sockets/backend-r2.status")" = 'stage=ready error=0 meta=1 uart=1' ]
}
health() {
    current=$(pid victory-gui) || return 1
    result=$("$r/ui-health" --require-ready) || return 1
    case "$result" in "ui-health-ready pid=$current system="*) ;; *) return 1;;esac
}
r4_diagnostic() {
    regular "$sockets/ui-r4.status" || return 1
    awk -v current="$1" '
    BEGIN {split("stage pid bound shown width height connected reading applying paused queries applies replies envelope config lens socket timeouts sendfail edits",key," ")}
    NF!=20 {exit 1}
    {for(i=1;i<=20;i++){split($i,v,"=");if(v[1]!=key[i])exit 1;if(i==1){if(v[2]!~/^[a-z-]+$/)exit 1}else if(v[2]!~/^[0-9]+$/)exit 1}
     if($2!="pid="current || $3!="bound=1" || $9!="applying=0")exit 1}
    END {if(NR!=1)exit 1}' "$sockets/ui-r4.status"
}
gui_ready() {
    mode=$1
    service_base victory-gui && only_dropins victory-gui "$mode" || return 1
    expected=$oldpreload;drops="$afgui $fixgui"
    if [ "$mode" = integrated ];then expected=$newpreload;drops="$drops $gui";regular "$gui" && cmp -s "$gui" "$s/gui.dropin" || return 1;fi
    [ "$(value victory-gui DropInPaths)" = "$drops" ] || return 1
    p=$(pid victory-gui) || return 1
    [ "$(environment "$p" LD_PRELOAD)" = "$expected" ] && [ -z "$(environment "$p" LD_LIBRARY_PATH)" ] || return 1
    for key in HBL_AF_ONLY_ENABLE HBL_AF_SETTINGS_ENABLE HBL_AF_UI_R4_ENABLE;do [ "$(environment "$p" "$key")" = 1 ] || return 1;done
    for library in "$af/libhbl-af-only.so" "$r4/libhbl-af-ui.so";do grep -Fq "$library" "/proc/$p/maps" || return 1;done
    socket_file "$sockets/ui.sock" && [ "$(cat "$af/ui.status")" = af-only-ui-ready ] && r4_diagnostic "$p" || return 1
    if [ "$mode" = integrated ];then
        [ "$(environment "$p" HBL_UI_AF_ENABLE)" = 1 ] && grep -Fq "$r/libhbl-ui-af.so" "/proc/$p/maps" || return 1
        regular "$r/ui.status" && [ "$(cat "$r/ui.status")" = "ui-af-ready-resources10-components8-contexts2 pid=$p" ] || return 1
    else [ -z "$(environment "$p" HBL_UI_AF_ENABLE)" ] || return 1;fi
    health
}
owned() { private "$s" && regular "$s/owner" && [ "$(cat "$s/owner")" = hbl-ui-af-r4-v1 ] && cmp -s "$s/manifest.sha256" "$r/manifest.sha256"; }
protected_unchanged() {
    inherited_files && af_bus_ready && [ "$(pid msg2dbus-farm)" = "$(cat "$s/bus.pid")" ] && sha256sum -c "$s/protected.sha256" >/dev/null
}
integrated_ready() { protected_unchanged && gui_ready integrated; }
r4_ready() { protected_unchanged && gui_ready af; }
wait_ready() { for n in 1 2 3 4 5 6 7 8 9 10;do "$1" 2>/dev/null && return 0;sleep 1;done;return 1; }
stop_gui() {
    oldpid=$(pid victory-gui 2>/dev/null || :)
    systemctl stop victory-gui || return 1
    ! systemctl is-active --quiet victory-gui || return 1
    [ -z "$oldpid" ] || [ ! -d "/proc/$oldpid" ] || return 1
    # 只清理已退出 GUI 的 AF UI socket；后台 socket 与进程始终保留。
    if ! absent "$sockets/ui.sock";then socket_file "$sockets/ui.sock" || return 1;rm "$sockets/ui.sock";fi
}
