#!/bin/sh
# 本文件仅供同目录的会话脚本引用，不包含传输或设备发现。
set -eu
umask 077
d=/tmp/hbl-x1d-rpa
s=$d/state
units=/run/systemd/system
tag=95-x1d-replay-af.conf
die() { printf 'replay-error stage=%s code=%s\n' "${stage:-arguments}" "$1"; exit "$1"; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pidofunit() {
    p=$(value "$1" MainPID) || return 1
    case "$p" in ''|0|*[!0-9]*) return 1;; esac
    printf '%s\n' "$p"
}
private_dir() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%h' "$1")" = 0:1 ]; }
package_check() {
    [ "$(id -u)" = 0 ] && private_dir "$d" || die 60
    [ -z "${LD_PRELOAD:-}" ] && [ -z "${LD_LIBRARY_PATH:-}" ] || die 61
    cd "$d"
    regular manifest.sha256 || die 61
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.\/-]+$/ || $2~/^\// || $2~/(^|\/)\.\.(\/|$)/ || seen[$2]++ {bad=1} END {exit bad}' manifest.sha256 || die 61
    while read -r digest file; do regular "$file" || die 61; done < manifest.sha256
    for file in common.sh preflight.sh install.sh restore.sh status.sh baseline.sha256 replay-check replay-ui.rcc libx1d-replay-session.so libx1d-replay-provider.so af-files.sha256 gui.af.conf bus.af.conf delta.conf af-proof.txt; do
        awk -v wanted="$file" '$2==wanted {n++} END {exit n!=1}' manifest.sha256 || die 61
    done
    sha256sum -c manifest.sha256 >/dev/null || die 61
    [ ! -s /etc/ld.so.preload ] || die 62
    [ -d "$units" ] && [ ! -L "$units" ] || die 62
}
baseline_check() {
    # 唯一允许的绝对路径来自本包固定版本清单，无照片、设置或设备节点。
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^\/(usr\/bin|usr\/lib|lib)\/[A-Za-z0-9_.+\/-]+$/ || $2~/(^|\/)\.\.(\/|$)/ || seen[$2]++ {bad=1} END {exit bad}' "$d/baseline.sha256" || die 62
    sha256sum -c "$d/baseline.sha256" >/dev/null || die 62
}
base_hash() { awk -v name="/usr/bin/$1" '$2==name {print $1}' "$d/baseline.sha256"; }
running() {
    service=$1; expected=$2
    [ "$(value "$service" LoadState)" = loaded ] && [ "$(value "$service" ActiveState)" = active ] &&
        [ "$(value "$service" SubState)" = running ] || return 1
    p=$(pidofunit "$service") || return 1
    [ "$(sha256sum "/proc/$p/exe" | cut -d' ' -f1)" = "$expected" ] || return 1
    [ -r "/proc/$p/maps" ] && awk 'index($0,"(deleted)") && !($2=="rw-s" && NF==7 && $7=="(deleted)" && ($6=="/dev/zero" || (index($6,"/tmp/weston-shared-")==1 && substr($6,20)~/^[A-Za-z0-9]+$/))) {bad=1} END {exit bad}' "/proc/$p/maps" || return 1
}
clean_unit() {
    [ "$(value "$1" FragmentPath)" = "/lib/systemd/system/$1.service" ] || return 1
    [ -z "$(value "$1" DropInPaths)" ] || return 1
    if value "$1" Environment | grep -Eq '(LD_PRELOAD|LD_LIBRARY_PATH)='; then return 1; fi
    p=$(pidofunit "$1") || return 1
    if tr '\000' '\n' < "/proc/$p/environ" | grep -Eq '^(LD_PRELOAD|LD_LIBRARY_PATH)='; then return 1; fi
    [ ! -L "$units/$1.service.d" ]
}
owners() {
    a=$(pidofunit configstore) && b=$(pidofunit jpeg-daemon) && c=$(pidofunit storage-daemon) || return 1
    "$d/replay-check" --owners "$a" "$b" "$c"
}
state_check() {
    private_dir "$s" && regular "$s/owner" && [ "$(cat "$s/owner")" = x1d-replay-session-v1 ] || die 63
    [ "$(sha256sum "$d/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$s/package.sha256")" ] || die 63
}
af=/tmp/hbl-x1d-combined
afs=$af/install-state
settings=/tmp/hbl-af-settings
gui90=$units/victory-gui.service.d/90-hbl-af-only.conf
bus90=$units/msg2dbus-farm.service.d/90-hbl-af-only.conf
delta=$units/victory-gui.service.d/$tag
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
af_original_files() {
    private_dir "$af" && private_dir "$afs" && private_dir "$settings" || return 1
    regular "$gui90" && regular "$bus90" && cmp -s "$gui90" "$d/gui.af.conf" && cmp -s "$bus90" "$d/bus.af.conf" || return 1
    sha256sum -c "$d/af-files.sha256" >/dev/null || return 1
    for name in owner package.sha256 gui.dropin farm.dropin af-installed.sha256 ram.started hold.release ui.done bus.done release.done; do regular "$afs/$name" || return 1; done
    [ "$(cat "$afs/owner")" = hbl-af-only-v1 ] && [ "$(cat "$afs/ram.started")" = started ] && [ "$(cat "$afs/hold.release")" = release ] || return 1
    cmp -s "$afs/gui.dropin" "$d/gui.af.conf" && cmp -s "$afs/farm.dropin" "$d/bus.af.conf" && cmp -s "$afs/af-installed.sha256" "$d/af-proof.txt" || return 1
    [ "$(sha256sum "$af/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$afs/package.sha256")" ] || return 1
    for role in configstore jpeg-daemon storage-daemon; do running "$role" "$(base_hash "$role")" && clean_unit "$role" || return 1; done
    running msg2dbus-farm "$(base_hash msg2dbus)" || return 1
    [ "$(value msg2dbus-farm FragmentPath)" = /lib/systemd/system/msg2dbus-farm.service ] && [ "$(value msg2dbus-farm DropInPaths)" = "$bus90" ] || return 1
    p=$(pidofunit msg2dbus-farm) || return 1
    [ "$(tr '\000' '\n' < "/proc/$p/environ" | grep '^LD_PRELOAD=')" = "LD_PRELOAD=$af/af/libhbl-af-bus.so" ] || return 1
    ! tr '\000' '\n' < "/proc/$p/environ" | grep -q '^LD_LIBRARY_PATH=' || return 1
    grep -Fq "$af/af/libhbl-af-bus.so" "/proc/$p/maps" || return 1
    [ -S "$settings/backend.sock" ] && [ ! -L "$settings/backend.sock" ] && [ "$(stat -c '%u:%a' "$settings/backend.sock")" = 0:600 ] || return 1
    grep -q '^stage=ready error=0 meta=1 uart=1$' "$settings/backend-r3.status" || return 1
    owners
}
protect_snapshot() {
    # 原 AF 证明/配置与生产进程身份；不读取 RAM 或照片，不保存 AF 参数。
    for role in msg2dbus-farm configstore jpeg-daemon storage-daemon; do
        p=$(pidofunit "$role") || return 1
        printf '%s %s ' "$role" "$p"
        sha256sum "/proc/$p/exe"
    done
    for name in owner package.sha256 gui.dropin farm.dropin af-installed.sha256 ram.started hold.release ui.done bus.done release.done; do sha256sum "$afs/$name"; done
    sha256sum "$gui90" "$bus90" "$af/manifest.sha256"
}
protection_unchanged() {
    af_original_files && protect_snapshot > "$s/protection.check" && cmp -s "$s/protection.before" "$s/protection.check"
}
gui_environment() {
    expected=$1
    p=$(pidofunit victory-gui) || return 1
    [ "$(tr '\000' '\n' < "/proc/$p/environ" | grep '^LD_PRELOAD=')" = "LD_PRELOAD=$expected" ] || return 1
    ! tr '\000' '\n' < "/proc/$p/environ" | grep -q '^LD_LIBRARY_PATH=' || return 1
    for pair in HBL_AF_ONLY_ENABLE=1 HBL_AF_ONLY_HOLD=1 HBL_AF_SETTINGS_ENABLE=1 HBL_AF_UI_R4_ENABLE=0; do
        [ "$(tr '\000' '\n' < "/proc/$p/environ" | grep "^${pair%%=*}=")" = "$pair" ] || return 1
    done
    if [ "$expected" = "$af/libhbl-af-only.so:$af/af/libhbl-af-ui.so" ]; then
        ! tr '\000' '\n' < "/proc/$p/environ" | grep -q '^X1D_REPLAY_SESSION=' || return 1
    else
        [ "$(tr '\000' '\n' < "/proc/$p/environ" | grep '^X1D_REPLAY_SESSION=')" = X1D_REPLAY_SESSION=1 ] || return 1
    fi
}
gui_ready() {
    mode=$1
    running victory-gui "$(base_hash victory-gui)" || return 1
    [ "$(value victory-gui FragmentPath)" = /lib/systemd/system/victory-gui.service ] || return 1
    if [ "$mode" = af ]; then
        [ "$(value victory-gui DropInPaths)" = "$gui90" ] && absent "$delta" || return 1
        gui_environment "$af/libhbl-af-only.so:$af/af/libhbl-af-ui.so" || return 1
    else
        regular "$delta" && cmp -s "$delta" "$d/delta.conf" || return 1
        [ "$(value victory-gui DropInPaths)" = "$gui90 $delta" ] || return 1
        gui_environment "$d/libx1d-replay-session.so:$d/libx1d-replay-provider.so:$af/libhbl-af-only.so:$af/af/libhbl-af-ui.so" || return 1
        p=$(pidofunit victory-gui)
        for lib in libx1d-replay-session.so libx1d-replay-provider.so; do grep -Fq "$d/$lib" "/proc/$p/maps" || return 1; done
    fi
    p=$(pidofunit victory-gui)
    for lib in libhbl-af-only.so af/libhbl-af-ui.so; do grep -Fq "$af/$lib" "/proc/$p/maps" || return 1; done
    [ "$(cat "$af/ui.status")" = af-only-ui-ready ] || return 1
    grep -Eq "^stage=[a-z-]+ pid=$p bound=1 " "$settings/ui-r4.status" || return 1
    [ -S "$settings/ui.sock" ] && [ ! -L "$settings/ui.sock" ] && [ "$(stat -c '%u:%a' "$settings/ui.sock")" = 0:600 ] || return 1
}
gui_idle() {
    p=$(pidofunit victory-gui) || return 1
    grep -Eq "^stage=[a-z-]+ pid=$p bound=1 shown=0 .* reading=0 applying=0 " "$settings/ui-r4.status"
}
stop_owned_gui() {
    if systemctl is-active --quiet victory-gui; then gui_idle || return 1; fi
    old=$(pidofunit victory-gui 2>/dev/null || :)
    : > "$s/gui-stop-intent"
    systemctl stop victory-gui || return 1
    ! systemctl is-active --quiet victory-gui || return 1
    [ -z "$old" ] || [ ! -d "/proc/$old" ] || return 1
    # 与 AF 原 stop_gui 合同一致：证明原进程退出后才处理其私有残留 UI socket。
    if ! absent "$settings/ui.sock"; then
        [ -S "$settings/ui.sock" ] && [ ! -L "$settings/ui.sock" ] && [ "$(stat -c '%u:%a' "$settings/ui.sock")" = 0:600 ] || return 1
        rm "$settings/ui.sock"
    fi
}
wait_health() {
    mode=$1
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if gui_ready "$mode" && protection_unchanged; then
            if [ "$mode" = af ]; then "$d/replay-check" --active && return 0
            else "$d/replay-check" --gpu && return 0; fi
        fi
        sleep 1
    done
    return 1
}
