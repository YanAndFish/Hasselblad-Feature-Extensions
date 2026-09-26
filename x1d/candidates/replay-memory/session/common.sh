#!/bin/sh
# 本文件仅供同目录的会话脚本引用，不包含传输或设备发现。
set -eu
umask 077
d=/tmp/hbl-x1d-rpm
s=$d/state
units=/run/systemd/system
tag=90-x1d-replay.conf
die() { printf 'replay-error stage=%s code=%s\n' "${stage:-arguments}" "$1"; exit "$1"; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pidofunit() {
    p=$(value "$1" MainPID) || return 1
    case "$p" in ''|0|*[!0-9]*) return 1;; esac
    printf '%s\n' "$p"
}
private_dir() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
package_check() {
    [ "$(id -u)" = 0 ] && private_dir "$d" || die 60
    [ -z "${LD_PRELOAD:-}" ] && [ -z "${LD_LIBRARY_PATH:-}" ] || die 61
    cd "$d"
    regular manifest.sha256 || die 61
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.\/-]+$/ || $2~/^\// || $2~/(^|\/)\.\.(\/|$)/ || seen[$2]++ {bad=1} END {exit bad}' manifest.sha256 || die 61
    while read -r digest file; do regular "$file" || die 61; done < manifest.sha256
    for file in common.sh preflight.sh install.sh restore.sh status.sh baseline.sha256 replay-check replay-ui.rcc libx1d-replay-session.so libx1d-replay-provider.so; do
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
    private_dir "$s" && regular "$s/owner" && [ "$(cat "$s/owner")" = x1d-replay-memory-v1 ] || die 63
    [ "$(sha256sum "$d/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$s/package.sha256")" ] || die 63
}
install_drop() {
    role=$1; expected=$2; directory=$units/$role.service.d; destination=$directory/$tag
    [ ! -L "$directory" ] && [ ! -e "$destination" ] && [ ! -L "$destination" ] || die 68
    if [ ! -d "$directory" ]; then mkdir "$directory"; : > "$s/$role.directory-created"; fi
    # 写前登记意图；失败时恢复器只移除内容仍与本轮模板相同的文件。
    : > "$s/$role.touched"
    (set -C; cat "$expected" > "$destination") || die 68
}
wait_running() {
    role=$1; expected=$2
    for n in 1 2 3 4 5 6 7 8 9 10; do running "$role" "$expected" && return 0; sleep 1; done
    return 1
}
