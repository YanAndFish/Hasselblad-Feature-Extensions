#!/bin/sh
# 只安装/卸载固定探针。根分区仅在文件事务期间写入；不重启设备或当前 GUI。
set -eu
umask 077
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$source/common.sh"
dest=/opt/hbl-wifi-probe-v1
pending=/opt/hbl-wifi-probe-v1.installing
parent=/opt
dropdir=/etc/systemd/system/victory-gui.service.d
drop=$dropdir/91-hbl-wifi-probe.conf
expected_manifest=1dcdd5b792e04a979d801182d08379546c358108bf050bb49741ce590736b30c
rootflags() { awk '$2=="/" && $3=="ext4" {print $4}' /proc/mounts; }
root_ro() { case ",$(rootflags)," in *,ro,*) return 0;;*) return 1;;esac; }
root_rw() { case ",$(rootflags)," in *,rw,*) return 0;;*) return 1;;esac; }
same_manifest() { [ "$(sha256sum "$1/manifest.sha256" | awk '{print $1}')" = "$expected_manifest" ]; }
verify_source() { same_manifest "$source" && verify "$source"; }
verify_installed() {
    same_manifest "$dest" && verify "$dest" && regular "$drop" && cmp -s "$drop" "$dest/gui.conf" || return 1
    regular "$dest/persist.sh" && regular "$dest/installed.sha256" || return 1
    (cd "$dest" && sha256sum -c installed.sha256 >/dev/null)
}
no_other_gui_dropins() {
    for base in /etc/systemd/system /run/systemd/system /lib/systemd/system;do
        d=$base/victory-gui.service.d
        [ ! -L "$d" ] || return 1
        for f in "$d"/*.conf;do absent "$f" || [ "$f" = "$drop" ] || return 1;done
    done
}
remove_payload_files() {
    target=$1
    private "$target" || return 1
    # 名字来自已校验的固定源清单。逐个删除本包文件，不做递归删除。
    while read -r hash file;do
        if ! absent "$target/$file";then
            regular "$target/$file" && cmp -s "$target/$file" "$source/$file" || return 1
            rm -- "$target/$file" || return 1
        fi
    done < "$source/manifest.sha256"
    for file in manifest.sha256 persist.sh;do
        if ! absent "$target/$file";then
            regular "$target/$file" && cmp -s "$target/$file" "$source/$file" || return 1
            rm -- "$target/$file" || return 1
        fi
    done
    if ! absent "$target/installed.sha256";then regular "$target/installed.sha256" && rm -- "$target/installed.sha256" || return 1;fi
    rmdir "$target"
}
case "${1:-}" in
install)
    verify_source && regular "$source/persist.sh" && root_ro || exit 60
    for role in victory-gui msg2dbus-farm configstore jpeg-daemon storage-daemon;do clean "$role" || exit 61;done
    "$source/health" --require-ready >/dev/null || exit 62
    absent "$dest" && absent "$pending" && absent "$drop" && absent "$drop.new" || exit 63
    [ ! -L "$parent" ] && [ ! -L "$dropdir" ] || exit 64
    [ -d "$parent" ] || absent "$parent" || exit 64
    [ -d "$dropdir" ] || absent "$dropdir" || exit 64
    [ "$(df -Pk / | awk 'END {print $4}')" -gt 1024 ] || exit 65
    made_parent=0;made_dropdir=0;made_pending=0;made_dest=0;installed_drop=0;committed=0;touched=0
    finish() {
        code=$?;trap - 0
        if [ "$committed" = 0 ] && [ "$made_parent$made_dropdir$made_pending$made_dest$installed_drop" != 00000 ];then
            if root_ro;then mount -o remount,rw / || code=85;fi
            if root_rw;then
                if [ "$installed_drop" = 1 ];then
                    if regular "$drop" && cmp -s "$drop" "$source/gui.conf";then rm -- "$drop" || code=85;else code=85;fi
                fi
                if ! absent "$drop.new";then
                    if regular "$drop.new" && cmp -s "$drop.new" "$source/gui.conf";then rm -- "$drop.new" || code=85;else code=85;fi
                fi
                if [ "$made_dest" = 1 ];then remove_payload_files "$dest" || code=85;fi
                if [ "$made_pending" = 1 ] && [ -d "$pending" ];then remove_payload_files "$pending" || code=85;fi
                if [ "$made_dropdir" = 1 ];then rmdir "$dropdir" || code=85;fi
                if [ "$made_parent" = 1 ];then rmdir "$parent" || code=85;fi
            fi
        fi
        if [ "$touched" = 1 ];then
            sync
            root_ro || mount -o remount,ro / || code=86
            root_ro || code=86
        fi
        if [ "$code" = 0 ] && [ "$committed" = 1 ];then printf 'persistent-files-installed-next-boot\n';
        elif [ "$code" != 0 ];then printf 'persistent-install-failed exit=%s\n' "$code";fi
        exit "$code"
    }
    trap finish 0
    touched=1
    mount -o remount,rw /
    root_rw
    if absent "$parent";then mkdir -m 755 "$parent";made_parent=1;fi
    mkdir -m 700 "$pending";made_pending=1
    cp "$source/manifest.sha256" "$pending/manifest.sha256"
    while read -r hash file;do cp "$source/$file" "$pending/$file";done < "$source/manifest.sha256"
    cp "$source/persist.sh" "$pending/persist.sh"
    chmod 700 "$pending/health" "$pending/launch.sh" "$pending/monitor.sh" "$pending/persist.sh"
    (cd "$pending" && sha256sum manifest.sha256 persist.sh > installed.sha256)
    same_manifest "$pending" && verify "$pending"
    (cd "$pending" && sha256sum -c installed.sha256 >/dev/null)
    mv "$pending" "$dest";made_dest=1;made_pending=0
    if absent "$dropdir";then mkdir -m 755 "$dropdir";made_dropdir=1;fi
    cp "$source/gui.conf" "$drop.new"
    cmp -s "$drop.new" "$dest/gui.conf"
    mv "$drop.new" "$drop";installed_drop=1
    verify_installed
    # 不调用 daemon-reload/restart。当前原厂进程继续运行，下次正常开机读取此文件。
    sync
    mount -o remount,ro /
    root_ro
    verify_installed
    committed=1
    ;;
status)
    root_ro && verify_installed && no_other_gui_dropins
    printf 'persistent-files-verified-root-readonly\n'
    ;;
remove)
    # 卸载入口必须从独立临时副本执行，避免读取正在删除的脚本/清单。
    [ "$source" != "$dest" ] && verify_source && root_ro && verify_installed && no_other_gui_dropins || exit 70
    cmp -s "$source/persist.sh" "$dest/persist.sh" || exit 71
    touched=0
    finish_remove() {
        code=$?;trap - 0
        if [ "$touched" = 1 ];then sync;mount -o remount,ro / || code=86;root_ro || code=86;fi
        if [ "$code" = 0 ];then printf 'persistent-files-removed\n';else printf 'persistent-remove-incomplete exit=%s\n' "$code";fi
        exit "$code"
    }
    trap finish_remove 0
    touched=1;mount -o remount,rw /;root_rw
    rm -- "$drop"
    remove_payload_files "$dest"
    # 保留共享父目录。当前界面不会被本文件事务停止。
    ;;
*) exit 59;;
esac
