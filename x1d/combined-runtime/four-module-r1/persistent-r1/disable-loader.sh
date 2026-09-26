#!/bin/sh
# 停用四模块自动装载入口；不重启当前进程，不改当前控制器 RAM。
set -eu
umask 077
dest=/opt/hbl-four-module-v1
backup=/opt/hbl-four-module-v1.disabled
gui=/etc/systemd/system/victory-gui.service.d/92-hbl-four-module.conf
farm=/etc/systemd/system/msg2dbus-farm.service.d/92-hbl-four-module.conf
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
root_ro() { awk '$2=="/" && $3=="ext4" && $4~/(^|,)ro(,|$)/ {ok=1} END {exit !ok}' /proc/mounts; }
[ "$#" = 0 ] && [ "$(id -u)" = 0 ] && private "$dest" && root_ro || exit 60
regular "$dest/enabled" && [ "$(cat "$dest/enabled")" = enabled-current-firmware ] || exit 61
regular "$gui" && regular "$farm" && cmp -s "$gui" "$dest/gui.conf" && cmp -s "$farm" "$dest/farm.conf" || exit 62
absent "$backup" && absent "$gui.disabled-next" && absent "$farm.disabled-next" || exit 63
systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon || exit 64
touched=0
committed=0
finish() {
    rc=$?
    trap - 0 1 2 15
    if [ "$touched" = 1 ] && [ "$committed" = 0 ];then
        root_ro && mount -o remount,rw / || true
        for item in gui.conf farm.conf;do
            case "$item" in gui.conf) target=$gui;;farm.conf) target=$farm;;esac
            if absent "$target";then cp "$backup/$item" "$target.disabled-next" && mv "$target.disabled-next" "$target" || rc=90
            else regular "$target" && cmp -s "$target" "$backup/$item" || rc=90;fi
        done
    fi
    if [ "$touched" = 1 ];then sync;root_ro || mount -o remount,ro / || rc=91;root_ro || rc=91;fi
    if [ "$rc" = 0 ] && [ "$committed" = 1 ];then echo four-module-autoload-disabled-next-boot;else echo "disable-loader-stopped-$rc";fi
    exit "$rc"
}
trap finish 0
trap 'exit 89' 1 2 15
touched=1
mount -o remount,rw /
mkdir -m 700 "$backup"
cp "$dest/enabled" "$backup/enabled"
cp "$gui" "$backup/gui.conf"
cp "$farm" "$backup/farm.conf"
cmp -s "$dest/enabled" "$backup/enabled"
cmp -s "$gui" "$backup/gui.conf"
cmp -s "$farm" "$backup/farm.conf"
sync
# 只移除两个 systemd 开机入口；安装目录和启用标记原样保留。
rm "$gui"
rm "$farm"
sync
mount -o remount,ro /
root_ro && regular "$dest/enabled" && [ "$(cat "$dest/enabled")" = enabled-current-firmware ] && absent "$gui" && absent "$farm"
private "$backup" && regular "$backup/enabled" && regular "$backup/gui.conf" && regular "$backup/farm.conf"
systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon
committed=1
