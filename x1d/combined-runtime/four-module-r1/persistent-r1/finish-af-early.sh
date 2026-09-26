#!/bin/sh
# 仅用于已核实的旧库映射占用导致只读恢复失败；由用户正常重启释放。
set -eu
umask 077
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=/opt/hbl-af-only-v1
files='libhbl-af-loader.so manifest.sha256'
regular(){ [ -f "$1" ] && [ ! -L "$1" ]; }
private(){ [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
verify(){ (cd "$dest" && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null); }
pin(){ [ "$(sha256sum "$dest/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$source/$1")" ]; }
[ "$#" = 0 ] && [ "$(id -u)" = 0 ] && private "$source" && private "$dest" && private "$source/backup"
awk '$2=="/" && $3=="ext4" && $4~/(^|,)rw(,|$)/ {yes=1} END{exit !yes}' /proc/mounts
(cd "$source" && sha256sum -c repair-manifest.sha256 >/dev/null)
regular "$dest/enabled" && [ "$(cat "$dest/enabled")" = af-only-v1 ] && verify && pin old-pin
pid=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
[ "$pid" = "$(cat "$source/previous-pid")" ]
awk '/libhbl-af-loader.so/ && /deleted/ {yes=1} END{exit !yes}' "/proc/$pid/maps"
systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon
for f in $files enabled;do regular "$source/backup/$f" && cmp -s "$dest/$f" "$source/backup/$f";done
for f in $files;do regular "$source/files/$f" && [ ! -e "$dest/$f.early-next" ] && [ ! -L "$dest/$f.early-next" ];done
[ ! -e "$dest/enabled.early-next" ] && [ ! -L "$dest/enabled.early-next" ]
changed=0;committed=0
finish(){
 rc=$?;trap - 0 1 2 15;set +e
 if [ "$changed" = 1 ] && [ "$committed" = 0 ];then
  rm -f "$dest/enabled"
  restored=1
  for f in $files;do cp "$source/backup/$f" "$dest/$f.early-next" && mv "$dest/$f.early-next" "$dest/$f" || restored=0;done
  if [ "$restored" = 1 ] && verify && pin old-pin;then
   cp "$source/backup/enabled" "$dest/enabled.early-next" && mv "$dest/enabled.early-next" "$dest/enabled" || rc=90
  else rc=90;fi
 fi
 sync || rc=92
 if [ "$committed" = 1 ] && [ "$rc" = 0 ];then echo af-early-installed-root-rw-awaiting-normal-restart;else echo "af-early-finish-stopped-$rc";fi
 exit "$rc"
}
trap finish 0
trap 'exit 89' 1 2 15
changed=1
rm "$dest/enabled"
sync
for f in $files;do cp "$source/files/$f" "$dest/$f.early-next";cmp -s "$source/files/$f" "$dest/$f.early-next";mv "$dest/$f.early-next" "$dest/$f";done
verify && pin new-pin
sync
cp "$source/backup/enabled" "$dest/enabled.early-next"
mv "$dest/enabled.early-next" "$dest/enabled"
sync
verify && pin new-pin
committed=1
