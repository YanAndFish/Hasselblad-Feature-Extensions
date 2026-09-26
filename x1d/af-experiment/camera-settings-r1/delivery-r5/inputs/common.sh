#!/bin/sh
# 仅 AF 的 Linux 事务；目录名沿用已冻结健康检查器，不代表组合功能。
set -eu
umask 077
r=/tmp/hbl-x1d-combined
s=$r/install-state
a=/tmp/hbl-af-settings
units=/run/systemd/system
gui=$units/victory-gui.service.d/90-hbl-af-only.conf
farm=$units/msg2dbus-farm.service.d/90-hbl-af-only.conf
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%h' "$1")" = 0:1 ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pid() { p=$(value "$1" MainPID);case "$p" in ''|0|*[!0-9]*) return 1;; esac;printf '%s\n' "$p"; }
held() { "$r/system-check" --require-held-min-ms "${1:-180000}"; }
owned() { private "$s" && regular "$s/owner" && [ "$(cat "$s/owner")" = hbl-af-only-v1 ] && [ "$(sha256sum "$r/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$s/package.sha256")" ]; }
verify_package() {
    [ "$(id -u)" = 0 ] && private "$r" && regular "$r/manifest.sha256" || return 1
    [ -z "${LD_PRELOAD:-}" ] && [ -z "${LD_LIBRARY_PATH:-}" ] && [ ! -s /etc/ld.so.preload ] || return 1
    (cd "$r"
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.\/-]+$/ || $2~/^\// || $2~/(^|\/)\.\.(\/|$)/ || seen[$2]++ {bad=1} END {exit bad || NR<9}' manifest.sha256 || exit 1
    while read -r digest file; do regular "$file" || exit 1; done < manifest.sha256
    sha256sum -c manifest.sha256 >/dev/null) || return 1
    sha256sum -c "$r/baseline.sha256" >/dev/null
}
clean_service() {
    service=$1
    [ "$(value "$service" FragmentPath)" = "/lib/systemd/system/$service.service" ] && [ -z "$(value "$service" DropInPaths)" ] || return 1
    systemctl is-active --quiet "$service" || return 1
    ! value "$service" Environment | grep -Eq '(LD_PRELOAD|LD_LIBRARY_PATH)=' || return 1
    p=$(pid "$service") || return 1
    ! tr '\000' '\n' < "/proc/$p/environ" | grep -Eq '^(LD_PRELOAD|LD_LIBRARY_PATH)='
}
owned_dropins() {
    if [ -f "$s/gui.touched" ]; then regular "$gui" && cmp -s "$gui" "$s/gui.dropin" || return 1; fi
    if [ -f "$s/farm.touched" ]; then regular "$farm" && cmp -s "$farm" "$s/farm.dropin" || return 1; fi
}
restore_before_ram_ready() {
    verify_package && absent "$s/ram.started" || return 1
    if owned && owned_dropins;then return 0;fi
    absent "$gui" && absent "$farm" && clean_service victory-gui && clean_service msg2dbus-farm
}
gui_ready() {
    systemctl is-active --quiet victory-gui || return 1
    [ "$(cat "$r/ui.status")" = af-only-ui-ready ] || return 1
    p=$(pid victory-gui) || return 1
    for library in "$r/libhbl-af-only.so" "$r/af/libhbl-af-ui.so"; do grep -Fq "$library" "/proc/$p/maps" || return 1; done
    grep -Eq "^stage=[a-z-]+ pid=$p bound=1 " "$a/ui-r4.status" && [ -S "$a/ui.sock" ] && held
}
bus_ready() {
    systemctl is-active --quiet msg2dbus-farm || return 1
    p=$(pid msg2dbus-farm) || return 1
    grep -Fq "$r/af/libhbl-af-bus.so" "/proc/$p/maps" || return 1
    grep -q '^stage=ready error=0 meta=1 uart=1$' "$a/backend-r3.status" || return 1
    regular "$a/backend-r3-flow.status" && [ -S "$a/backend.sock" ] && held
}
wait_ready() { for n in 1 2 3 4 5 6 7 8 9 10; do "$1" 2>/dev/null && return 0;sleep 1;done;return 1; }
stop_gui() {
    old=$(pid victory-gui 2>/dev/null || :)
    systemctl stop victory-gui || return 1
    ! systemctl is-active --quiet victory-gui || return 1
    [ -z "$old" ] || [ ! -d "/proc/$old" ] || return 1
    if ! absent "$a/ui.sock"; then [ -S "$a/ui.sock" ] && [ ! -L "$a/ui.sock" ] && [ "$(stat -c '%u:%a' "$a/ui.sock")" = 0:600 ] || return 1;rm "$a/ui.sock";fi
}
