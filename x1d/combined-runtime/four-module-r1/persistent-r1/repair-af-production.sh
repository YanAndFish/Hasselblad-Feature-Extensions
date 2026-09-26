#!/bin/sh
# 仅替换已绑定启动脚本和清单。当前进程、RAM 和驱动不变。
set -eu
umask 077
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=/opt/hbl-af-only-v1
backup="$dest/.production-backup"
files='libhbl-af-loader.so common.sh manifest.sha256'
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
root_ro() { awk '$2=="/" && $3=="ext4" && $4~/(^|,)ro(,|$)/ {yes=1} END {exit !yes}' /proc/mounts; }
verify() { (cd "$dest" && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null); }
pin() { [ "$(sha256sum "$dest/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$source/new-pin")" ]; }
[ "$#" = 0 ] && [ "$(id -u)" = 0 ] && private "$source" && private "$dest" && root_ro || exit 60
(cd "$source" && sha256sum -c repair-manifest.sha256 >/dev/null) || exit 61
regular "$dest/enabled" && [ "$(cat "$dest/enabled")" = af-only-v1 ] && verify || exit 62
[ "$(sha256sum "$dest/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$source/old-pin")" ] || exit 62
absent "$backup" && absent "$dest/enabled.batch-next" || exit 63
for f in $files;do regular "$dest/$f" && regular "$source/files/$f" && absent "$dest/$f.batch-next" || exit 63;done
systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon || exit 64
touched=0;disabled=0;committed=0
finish() {
    rc=$?;trap - 0 1 2 15;set +e
    if [ "$touched" = 1 ];then
        if [ "$committed" = 0 ] && [ "$disabled" = 1 ];then
            # 校验失败时先保持未启用，再恢复已核对的原文件。
            root_ro && mount -o remount,rw / || true
            if ! absent "$dest/enabled";then regular "$dest/enabled" && rm "$dest/enabled" || rc=90;fi
            restored=1
            for f in $files;do cp "$backup/$f" "$dest/$f.batch-next" && mv "$dest/$f.batch-next" "$dest/$f" || restored=0;done
            if [ "$restored" = 1 ] && verify && [ "$(sha256sum "$dest/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$source/old-pin")" ];then
                cp "$backup/enabled" "$dest/enabled.batch-next" && mv "$dest/enabled.batch-next" "$dest/enabled" || rc=90
            else rc=90;fi
        fi
        sync || rc=92
        root_ro || mount -o remount,ro / || rc=91
        root_ro || rc=91
    fi
    if [ "$rc" = 0 ] && [ "$committed" = 1 ];then echo af-production-installed-awaiting-restart;else echo "boot-repair-stopped-$rc";fi
    exit "$rc"
}
trap finish 0
trap 'exit 89' 1 2 15
touched=1
mount -o remount,rw /
mkdir -m 700 "$backup"
for f in $files enabled;do
 if [ "$f" = libhbl-af-loader.so ];then ln "$dest/$f" "$backup/$f";else cp "$dest/$f" "$backup/$f";fi
 cmp -s "$dest/$f" "$backup/$f"
done
sync
disabled=1
rm "$dest/enabled"
sync
for f in $files;do cp "$source/files/$f" "$dest/$f.batch-next";cmp -s "$source/files/$f" "$dest/$f.batch-next";mv "$dest/$f.batch-next" "$dest/$f";done
verify && pin
sync
cp "$backup/enabled" "$dest/enabled.batch-next"
mv "$dest/enabled.batch-next" "$dest/enabled"
sync
mount -o remount,ro /
root_ro && verify && pin
committed=1
