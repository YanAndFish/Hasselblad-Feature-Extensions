#!/bin/sh
# 仅更新下次启动使用的候选及服务入口，不重启服务，不拍摄、不读照片。
set -eu
umask 077
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=/opt/hbl-af-only-v1
backup="$dest/.full-jpeg-output-backup"
oldfiles='baseline.sha256 manifest.sha256'
added='configstore-full jpeg-daemon-full full-jpeg-config.conf full-jpeg-encoder.conf'
cdir=/etc/systemd/system/configstore.service.d
jdir=/etc/systemd/system/jpeg-daemon.service.d
clink="$cdir/93-hbl-full-jpeg.conf"
jlink="$jdir/93-hbl-full-jpeg.conf"
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
root_ro() { awk '$2=="/" && $3=="ext4" && $4~/(^|,)ro(,|$)/ {yes=1} END {exit !yes}' /proc/mounts; }
verify() { (cd "$dest" && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null); }
pin() { [ "$(sha256sum "$dest/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$source/$1-pin")" ]; }
[ "$#" = 0 ] && [ "$(id -u)" = 0 ] && private "$source" && private "$dest" && root_ro || exit 60
(cd "$source" && sha256sum -c repair-manifest.sha256 >/dev/null) || exit 61
regular "$dest/enabled" && [ "$(cat "$dest/enabled")" = af-only-v1 ] && verify && pin old || exit 62
absent "$backup" && absent "$dest/enabled.batch-next" || exit 63
for f in $oldfiles;do regular "$dest/$f" && regular "$source/files/$f" && absent "$dest/$f.batch-next" || exit 63;done
for f in $added;do absent "$dest/$f" && regular "$source/files/$f" && absent "$dest/$f.batch-next" || exit 63;done
# 独立服务无其他 drop-in 才接入，避免覆盖用户未知启动规则。
for d in "$cdir" "$jdir";do absent "$d" || exit 63;done
[ "$(systemctl show -p DropInPaths configstore)" = DropInPaths= ] || exit 64
[ "$(systemctl show -p DropInPaths jpeg-daemon)" = DropInPaths= ] || exit 64
(cd "$source/files" && sha256sum -c baseline.sha256 >/dev/null) || exit 65
systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon || exit 66
touched=0;disabled=0;committed=0;madec=0;madej=0
finish() {
 rc=$?;trap - 0 1 2 15;set +e
 if [ "$touched" = 1 ];then
  if [ "$committed" = 0 ] && [ "$disabled" = 1 ];then
   root_ro && mount -o remount,rw / || true
   rm -f "$dest/enabled"
   [ "$madec" = 0 ] || { rm -f "$clink";rmdir "$cdir"; }
   [ "$madej" = 0 ] || { rm -f "$jlink";rmdir "$jdir"; }
   restored=1
   for f in $oldfiles;do cp "$backup/$f" "$dest/$f.batch-next" && mv "$dest/$f.batch-next" "$dest/$f" || restored=0;done
   for f in $added;do rm -f "$dest/$f" "$dest/$f.batch-next" || restored=0;done
   if [ "$restored" = 1 ] && verify && pin old;then
    cp "$backup/enabled" "$dest/enabled.batch-next" && mv "$dest/enabled.batch-next" "$dest/enabled" || rc=90
   else rc=90;fi
  fi
  sync || rc=92
  root_ro || mount -o remount,ro / || rc=91
  root_ro || rc=91
 fi
 if [ "$rc" = 0 ] && [ "$committed" = 1 ];then echo af-production-installed-awaiting-restart;else echo "full-jpeg-stopped-$rc";fi
 exit "$rc"
}
trap finish 0
trap 'exit 89' 1 2 15
touched=1
mount -o remount,rw /
mkdir -m 700 "$backup"
for f in $oldfiles enabled;do cp "$dest/$f" "$backup/$f";cmp -s "$dest/$f" "$backup/$f";done
sync
disabled=1
rm "$dest/enabled"
sync
for f in $oldfiles $added;do cp "$source/files/$f" "$dest/$f.batch-next";cmp -s "$source/files/$f" "$dest/$f.batch-next";mv "$dest/$f.batch-next" "$dest/$f";done
chmod 700 "$dest/configstore-full" "$dest/jpeg-daemon-full"
chmod 644 "$dest/full-jpeg-config.conf" "$dest/full-jpeg-encoder.conf"
verify && pin new
mkdir -m 755 "$cdir";madec=1
mkdir -m 755 "$jdir";madej=1
cp "$dest/full-jpeg-config.conf" "$clink"
cp "$dest/full-jpeg-encoder.conf" "$jlink"
chmod 644 "$clink" "$jlink"
cmp -s "$dest/full-jpeg-config.conf" "$clink"
cmp -s "$dest/full-jpeg-encoder.conf" "$jlink"
sync
cp "$backup/enabled" "$dest/enabled.batch-next"
mv "$dest/enabled.batch-next" "$dest/enabled"
sync
mount -o remount,ro /
root_ro && verify && pin new
committed=1
