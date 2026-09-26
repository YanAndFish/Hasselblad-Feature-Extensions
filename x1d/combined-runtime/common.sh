#!/bin/sh
# 组合 Linux 事务的固定公共检查；只有 root 协调器可派发阶段。
set -eu
umask 077
r=/tmp/hbl-x1d-combined
s=$r/install-state
d=/tmp/hbl-wireless-flash
a=/tmp/hbl-af-settings
units=/run/systemd/system
gui=$units/victory-gui.service.d/90-hbl-combined.conf
farm=$units/msg2dbus-farm.service.d/90-hbl-combined.conf
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%h' "$1")" = 0:1 ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pid() { p=$(value "$1" MainPID);case "$p" in ''|0|*[!0-9]*) return 1;; esac;printf '%s\n' "$p"; }
held() { "$r/system-check" --require-held-min-ms "${1:-90000}"; }
owned() { private "$s" && regular "$s/owner" && [ "$(cat "$s/owner")" = hbl-combined-v1 ] && [ "$(sha256sum "$r/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$s/package.sha256")" ]; }
verify_package() {
    [ "$(id -u)" = 0 ] && private "$r" && regular "$r/manifest.sha256" || return 1
    [ -z "${LD_PRELOAD:-}" ] && [ -z "${LD_LIBRARY_PATH:-}" ] && [ ! -s /etc/ld.so.preload ] || return 1
    (cd "$r"
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.\/-]+$/ || $2~/^\// || $2~/(^|\/)\.\.(\/|$)/ || seen[$2]++ {bad=1} END {exit bad || NR<20}' manifest.sha256 || exit 1
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
gui_text() {
    chain=$r/libhbl-combined.so:$r/af/libhbl-af-ui.so:$r/replay/libx1d-replay-joint.so
    [ "$1" != provider ] || chain=$chain:$r/replay/libx1d-replay-provider.so
    printf '%s\n' '[Service]' 'Restart=no' 'UMask=0077' 'Environment=HBL_FORMAL_ENABLE_PLUGIN=1' 'Environment=HBL_FORMAL_INSTALL_HOLD=1' 'Environment=HBL_AF_SETTINGS_ENABLE=1' 'Environment=X1D_REPLAY_SESSION=1' "Environment=LD_PRELOAD=$chain"
}
gui_ready() {
    systemctl is-active --quiet victory-gui || return 1
    [ "$(cat "$r/ui.status")" = formal-ui-loaded-default-off ] || return 1
    p=$(pid victory-gui) || return 1
    for library in "$r/libhbl-combined.so" "$r/af/libhbl-af-ui.so" "$r/replay/libx1d-replay-joint.so"; do grep -Fq "$library" "/proc/$p/maps" || return 1; done
    [ -S "$d/formal-ui.sock" ] && [ -S "$a/ui.sock" ] || return 1
    held
}
observer_ready() {
    systemctl is-active --quiet msg2dbus-farm || return 1
    p=$(pid msg2dbus-farm) || return 1
    for library in "$d/libhbl-formal-observer.so" "$r/af/libhbl-af-bus.so"; do grep -Fq "$library" "/proc/$p/maps" || return 1; done
    grep -q '^stage=ready meta=1 observe=1$' "$d/formal-observer.status" || return 1
    [ "$(head -n 1 "$d/formal-worker.status")" = formal-worker-ready-default-off ] || return 1
    grep -q "^master=0 radio-held=0 radio-busy=0 same-process=1 pid=$p\$" "$d/formal-worker.status" || return 1
    [ -S "$d/formal-worker.sock" ] && [ -S "$a/backend.sock" ] || return 1
    held
}
wait_ready() { for n in 1 2 3 4 5 6 7 8 9 10; do "$1" 2>/dev/null && return 0;sleep 1;done;return 1; }
stop_gui() {
    old=$(pid victory-gui 2>/dev/null || :)
    systemctl stop victory-gui || return 1
    ! systemctl is-active --quiet victory-gui || return 1
    [ -z "$old" ] || [ ! -d "/proc/$old" ] || return 1
    # 只在旧 GUI 确认退出后清其固定自有 socket；从不覆盖其他类型的文件。
    for endpoint in "$a/ui.sock" "$d/formal-ui.sock"; do
        if ! absent "$endpoint"; then [ -S "$endpoint" ] && [ ! -L "$endpoint" ] && [ "$(stat -c '%u:%a' "$endpoint")" = 0:600 ] || return 1;rm "$endpoint";fi
    done
}
