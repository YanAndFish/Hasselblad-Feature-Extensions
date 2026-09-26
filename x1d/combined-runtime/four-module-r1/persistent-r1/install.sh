#!/bin/sh
# 固定包文件事务；不重启进程，下次正常开机由 systemd 读取。
set -eu
umask 077
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=/opt/hbl-four-module-v1
pending=/opt/hbl-four-module-v1.installing
gui=/etc/systemd/system/victory-gui.service.d/92-hbl-four-module.conf
farm=/etc/systemd/system/msg2dbus-farm.service.d/92-hbl-four-module.conf
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
rootflags() { awk '$2=="/" && $3=="ext4" {print $4}' /proc/mounts; }
root_ro() { case ",$(rootflags)," in *,ro,*)return 0;;*)return 1;;esac; }
root_rw() { case ",$(rootflags)," in *,rw,*)return 0;;*)return 1;;esac; }
verify() { (cd "$1" && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null); }
check_manifest() {
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.\/-]+$/ || $2~/^\// || $2~/(^|\/)\.\.(\/|$)/ {bad=1} END {exit bad}' "$1/manifest.sha256" || return 1
    while read -r h f;do regular "$1/$f" || return 1;done <"$1/manifest.sha256"
}
installed() {
    private "$dest" && regular "$dest/enabled" && [ "$(cat "$dest/enabled")" = enabled-current-firmware ] &&
    [ "$(sha256sum "$dest/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$dest/installed.manifest.sha256")" ] &&
    verify "$dest" && regular "$gui" && regular "$farm" && cmp -s "$gui" "$dest/gui.conf" && cmp -s "$farm" "$dest/farm.conf"
}
remove_own_package() {
    target=$1
    private "$target" || return 1
    # 删除范围严格来自本次已核验清单；不递归删除未知内容。
    for extra in enabled enabled.next installed.manifest.sha256;do
        if ! absent "$target/$extra";then regular "$target/$extra" && rm "$target/$extra" || return 1;fi
    done
    while read -r h f;do
        if ! absent "$target/$f";then regular "$target/$f" && cmp -s "$target/$f" "$source/$f" && rm "$target/$f" || return 1;fi
    done <"$source/manifest.sha256"
    if ! absent "$target/manifest.sha256";then cmp -s "$target/manifest.sha256" "$source/manifest.sha256" && rm "$target/manifest.sha256" || return 1;fi
    for sub in runtime/delta runtime;do
        if [ -d "$target/$sub" ] && [ ! -L "$target/$sub" ];then rmdir "$target/$sub" || return 1;fi
    done
    rmdir "$target"
}
case "${1:-}" in
install)
    [ "$#" = 2 ] && [ "$(id -u)" = 0 ] && private "$source" && root_ro || exit 60
    expected=$2
    [ "${#expected}" = 64 ] && [ "$(sha256sum "$source/manifest.sha256" | cut -d' ' -f1)" = "$expected" ] || exit 61
    check_manifest "$source" && verify "$source" || exit 61
    absent "$dest" && absent "$pending" && absent "$gui" && absent "$farm" && absent "$gui.new" && absent "$farm.new" || exit 62
    [ ! -L /opt ] && [ -d /opt ] || exit 63
    for unit in victory-gui msg2dbus-farm;do
        for root in /etc/systemd/system /lib/systemd/system;do
            dir=$root/$unit.service.d
            [ ! -L "$dir" ] || exit 63
            for file in "$dir"/*.conf;do absent "$file" || exit 63;done
        done
    done
    systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon || exit 64
    [ "$(df -Pk / | awk 'END {print $4}')" -gt 2048 ] || exit 65
    touched=0;made=0;committed=0;gui_added=0;farm_added=0
    finish() {
        rc=$?;trap - 0 1 2 15
        if [ "$committed" = 0 ] && [ "$touched" = 1 ];then
            if root_ro;then mount -o remount,rw / || rc=90;fi
            if root_rw;then
                if [ "$gui_added" = 1 ];then cmp -s "$gui" "$source/gui.conf" && rm "$gui" || rc=90;fi
                if [ "$farm_added" = 1 ];then cmp -s "$farm" "$source/farm.conf" && rm "$farm" || rc=90;fi
                for role in gui farm;do
                    case "$role" in gui) file=$gui.new;;farm) file=$farm.new;;esac
                    if ! absent "$file";then cmp -s "$file" "$source/$role.conf" && rm "$file" || rc=90;fi
                done
                if [ "$made" = 1 ];then remove_own_package "$pending" || rc=90;fi
                if [ "$made" = 2 ];then remove_own_package "$dest" || rc=90;fi
            fi
        fi
        if [ "$touched" = 1 ];then sync;root_ro || mount -o remount,ro / || rc=91;root_ro || rc=91;fi
        if [ "$rc" = 0 ] && [ "$committed" = 1 ];then printf 'persistent-files-installed-next-boot\n';else printf 'persistent-install-stopped-%s\n' "$rc";fi
        exit "$rc"
    }
    trap finish 0
    trap 'exit 89' 1 2 15
    touched=1;mount -o remount,rw /;root_rw
    mkdir -m 700 "$pending";made=1
    mkdir -m 700 "$pending/runtime" "$pending/runtime/delta"
    while read -r h f;do cp "$source/$f" "$pending/$f";done <"$source/manifest.sha256"
    cp "$source/manifest.sha256" "$pending/manifest.sha256"
    printf '%s\n' "$expected" >"$pending/installed.manifest.sha256"
    verify "$pending"
    mv "$pending" "$dest";made=2
    for dir in /etc/systemd/system/victory-gui.service.d /etc/systemd/system/msg2dbus-farm.service.d;do
        [ -d "$dir" ] || mkdir -m 755 "$dir"
    done
    cp "$dest/gui.conf" "$gui.new";cmp -s "$gui.new" "$dest/gui.conf";mv "$gui.new" "$gui";gui_added=1
    cp "$dest/farm.conf" "$farm.new";cmp -s "$farm.new" "$dest/farm.conf";mv "$farm.new" "$farm";farm_added=1
    # 双方配置和包均校验完成后才启用；掉电时未启用的 wrapper 直接运行原厂程序。
    sync
    printf 'enabled-current-firmware\n' >"$dest/enabled.next"
    mv "$dest/enabled.next" "$dest/enabled"
    installed
    sync;mount -o remount,ro /;root_ro
    installed
    committed=1
    ;;
status)
    [ "$#" = 1 ] && root_ro && installed || exit 66
    printf 'persistent-files-verified-root-readonly\n'
    ;;
*)exit 59;;
esac
