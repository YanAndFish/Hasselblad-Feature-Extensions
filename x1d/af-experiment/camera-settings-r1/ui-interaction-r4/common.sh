#!/bin/sh
set -eu
umask 077
. /tmp/hbl-x1d-combined/common.sh
d=/tmp/hbl-af-ui-r4
delta=/run/systemd/system/victory-gui.service.d/95-hbl-af-ui-r4.conf
delta_package() {
    verify_package && owned && owned_dropins && private "$d" || return 1
    regular "$d/manifest.sha256" || return 1
    (cd "$d";sha256sum -c manifest.sha256 >/dev/null) || return 1
    [ "$(cat "$s/package.sha256")" = 79da1a75552717936fbad737d8d4532c489907a7e02197e4acd0605f43c63b05 ] || return 1
}
base_ready() {
    delta_package && regular "$s/af-installed.sha256" && regular "$s/hold.release" && regular "$s/release.done" || return 1
    [ "$(value victory-gui DropInPaths)" = "$gui" ] || return 1
    systemctl is-active --quiet victory-gui && systemctl is-active --quiet msg2dbus-farm || return 1
    "$r/system-check" --require-active || return 1
    p=$(pid victory-gui);grep -Fq "$r/libhbl-af-only.so" "/proc/$p/maps" && grep -Fq "$r/af/libhbl-af-ui.so" "/proc/$p/maps" || return 1
    grep -q '^stage=ready error=0 meta=1 uart=1$' /tmp/hbl-af-settings/backend-r2.status || return 1
    [ -S /tmp/hbl-af-settings/backend.sock ]
}
bus_unchanged() {
    [ "$(pid msg2dbus-farm)" = "$(cat "$d/bus.pid")" ] && systemctl is-active --quiet msg2dbus-farm || return 1
    p=$(pid msg2dbus-farm);grep -Fq "$r/af/libhbl-af-bus.so" "/proc/$p/maps"
}
r4_ready() {
    bus_unchanged && systemctl is-active --quiet victory-gui || return 1
    [ "$(value victory-gui DropInPaths)" = "$gui $delta" ] || return 1
    p=$(pid victory-gui)
    grep -Fq "$r/libhbl-af-only.so" "/proc/$p/maps" && grep -Fq "$d/libhbl-af-ui.so" "/proc/$p/maps" || return 1
    [ "$(cat "$r/ui.status")" = af-only-ui-ready ] || return 1
    grep -Eq "^stage=[a-z-]+ pid=$p bound=1 " /tmp/hbl-af-settings/ui-r4.status || return 1
    [ -S /tmp/hbl-af-settings/ui.sock ] && "$r/system-check" --require-active
}
clear_ui_status() {
    for file in "$r/ui.status" /tmp/hbl-af-settings/ui-r4.status; do
        if ! absent "$file"; then regular "$file" || return 1;rm "$file";fi
    done
}
