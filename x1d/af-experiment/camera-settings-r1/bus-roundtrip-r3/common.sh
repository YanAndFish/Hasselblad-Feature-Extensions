#!/bin/sh
set -eu
umask 077
. /tmp/hbl-x1d-combined/common.sh
d=/tmp/hbl-af-bus-r3
delta=/run/systemd/system/msg2dbus-farm.service.d/95-hbl-af-bus-r3.conf
ui_delta=/run/systemd/system/victory-gui.service.d/95-hbl-af-ui-r4.conf
delta_package() {
    verify_package && owned && owned_dropins && private "$d" || return 1
    regular "$d/manifest.sha256" || return 1
    (cd "$d"
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.-]+$/ || seen[$2]++ {bad=1} END {exit bad || NR!=7}' manifest.sha256 || exit 1
    while read -r digest file;do regular "$file" || exit 1;done < manifest.sha256
    sha256sum -c manifest.sha256 >/dev/null) || return 1
    [ "$(cat "$s/package.sha256")" = 79da1a75552717936fbad737d8d4532c489907a7e02197e4acd0605f43c63b05 ]
}
ui_ready() {
    private /tmp/hbl-af-ui-r4 && regular /tmp/hbl-af-ui-r4/manifest.sha256 || return 1
    [ "$(sha256sum /tmp/hbl-af-ui-r4/manifest.sha256 | cut -d' ' -f1)" = 67da9db221c3e47598c204393d9d0a628d427d497da7763d618a5f724c75f9ca ] || return 1
    (cd /tmp/hbl-af-ui-r4;sha256sum -c manifest.sha256 >/dev/null) || return 1
    regular "$s/af-installed.sha256" && regular "$s/hold.release" && regular "$s/release.done" || return 1
    [ "$(value victory-gui DropInPaths)" = "$gui $ui_delta" ] || return 1
    regular "$ui_delta" && cmp -s "$ui_delta" /tmp/hbl-af-ui-r4/95-hbl-af-ui-r4.conf || return 1
    systemctl is-active --quiet victory-gui || return 1
    p=$(pid victory-gui)
    grep -Fq "$r/libhbl-af-only.so" "/proc/$p/maps" && grep -Fq /tmp/hbl-af-ui-r4/libhbl-af-ui.so "/proc/$p/maps" || return 1
    grep -Eq "^stage=[a-z-]+ pid=$p bound=1 " "$a/ui-r4.status" || return 1
    [ -S "$a/ui.sock" ] && "$r/system-check" --require-ui-stage
}
gui_same() {
    ui_ready && regular "$d/gui.pid" && [ "$(pid victory-gui)" = "$(cat "$d/gui.pid")" ]
}
old_ready() {
    systemctl is-active --quiet msg2dbus-farm || return 1
    [ "$(value msg2dbus-farm DropInPaths)" = "$farm" ] || return 1
    p=$(pid msg2dbus-farm)
    grep -Fq "$r/af/libhbl-af-bus.so" "/proc/$p/maps" || return 1
    grep -q '^stage=ready error=0 meta=1 uart=1$' "$a/backend-r2.status" && [ -S "$a/backend.sock" ]
}
base_ready() { delta_package && ui_ready && old_ready; }
new_ready() {
    gui_same && systemctl is-active --quiet msg2dbus-farm || return 1
    [ "$(value msg2dbus-farm DropInPaths)" = "$farm $delta" ] || return 1
    p=$(pid msg2dbus-farm)
    [ "$p" != "$(cat "$d/old-bus.pid")" ] || return 1
    grep -Fq "$d/libhbl-af-bus.so" "/proc/$p/maps" || return 1
    grep -q '^stage=ready error=0 meta=1 uart=1$' "$a/backend-r3.status" || return 1
    regular "$a/backend-r3-flow.status" && grep -Eq '^stage=[a-z-]+ error=[0-9]+ pending=[01] events=[0-9]+ ' "$a/backend-r3-flow.status" && [ -S "$a/backend.sock" ]
}
stop_bus() {
    old=$(pid msg2dbus-farm 2>/dev/null || :)
    systemctl stop msg2dbus-farm || return 1
    ! systemctl is-active --quiet msg2dbus-farm || return 1
    [ -z "$old" ] || [ ! -d "/proc/$old" ] || return 1
    if ! absent "$a/backend.sock";then
        [ -S "$a/backend.sock" ] && [ ! -L "$a/backend.sock" ] && [ "$(stat -c '%u:%a' "$a/backend.sock")" = 0:600 ] || return 1
        rm "$a/backend.sock"
    fi
    for file in "$a/backend-r2.status" "$a/backend-r3.status" "$a/backend-r3-flow.status";do
        if ! absent "$file";then regular "$file" && [ "$(stat -c '%a' "$file")" = 600 ] || return 1;rm "$file";fi
    done
}
