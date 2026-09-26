#!/bin/sh
# 仅替换已绑定启动脚本和清单。当前进程、RAM 和驱动不变。
set -eu
umask 077
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=/opt/hbl-four-module-v1
backup=/opt/hbl-four-module-v1.wait-r4-backup
files='boot-coordinate.sh boot-farm.sh runtime/manifest.sha256 manifest.sha256 installed.manifest.sha256'
added=runtime/boot-wait
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
root_ro() { awk '$2=="/" && $3=="ext4" && $4~/(^|,)ro(,|$)/ {yes=1} END {exit !yes}' /proc/mounts; }
verify() { (cd "$dest" && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null); }
pin() { [ "$(sha256sum "$dest/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$dest/installed.manifest.sha256")" ]; }
[ "$#" = 0 ] && [ "$(id -u)" = 0 ] && private "$source" && private "$dest" && root_ro || exit 60
(cd "$source" && sha256sum -c repair-manifest.sha256 >/dev/null) || exit 61
regular "$dest/enabled" && [ "$(cat "$dest/enabled")" = enabled-current-firmware ] && verify && pin || exit 62
[ "$(cat "$dest/installed.manifest.sha256")" = "$(cat "$source/old-pin")" ] || exit 62
absent "$backup" && absent "$dest/enabled.wait-next" || exit 63
for f in $files;do regular "$dest/$f" && regular "$source/files/$f" && absent "$dest/$f.wait-next" || exit 63;done
regular "$source/files/$added" && absent "$dest/$added" && absent "$dest/$added.wait-next" || exit 63
systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon || exit 64
touched=0;disabled=0;committed=0
finish() {
    rc=$?;trap - 0 1 2 15
    if [ "$touched" = 1 ];then
        if [ "$committed" = 0 ] && [ "$disabled" = 1 ];then
            # 校验失败时先保持未启用，再恢复已核对的原文件。
            root_ro && mount -o remount,rw / || true
            if ! absent "$dest/enabled";then regular "$dest/enabled" && rm "$dest/enabled" || rc=90;fi
            restored=1
            for f in "$added" "$added.wait-next";do
                if ! absent "$dest/$f";then regular "$dest/$f" && rm "$dest/$f" || restored=0;fi
            done
            for f in $files;do cp "$backup/$f" "$dest/$f.wait-next" && mv "$dest/$f.wait-next" "$dest/$f" || restored=0;done
            if [ "$restored" = 1 ] && verify && pin;then
                cp "$backup/enabled" "$dest/enabled.wait-next" && mv "$dest/enabled.wait-next" "$dest/enabled" || rc=90
            else rc=90;fi
        fi
        sync
        root_ro || mount -o remount,ro / || rc=91
        root_ro || rc=91
    fi
    if [ "$rc" = 0 ] && [ "$committed" = 1 ];then echo stage-wait-files-repaired-next-boot;else echo "boot-repair-stopped-$rc";fi
    exit "$rc"
}
trap finish 0
trap 'exit 89' 1 2 15
touched=1
mount -o remount,rw /
mkdir -m 700 "$backup" "$backup/runtime"
for f in $files enabled;do cp "$dest/$f" "$backup/$f";cmp -s "$dest/$f" "$backup/$f";done
sync
disabled=1
rm "$dest/enabled"
sync
for f in $added $files;do cp "$source/files/$f" "$dest/$f.wait-next";cmp -s "$source/files/$f" "$dest/$f.wait-next";mv "$dest/$f.wait-next" "$dest/$f";done
verify && pin
sync
cp "$backup/enabled" "$dest/enabled.wait-next"
mv "$dest/enabled.wait-next" "$dest/enabled"
sync
mount -o remount,ro /
root_ro && verify && pin
committed=1
