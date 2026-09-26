#!/bin/sh
# 由已确认引闪释放的 UI 事务调用；不操作拍摄服务或相机快门。
set -eu
umask 077
base=/opt/hbl-af-only-v1
state=/run/hbl-four-module/radio-mode
search=/sys/module/firmware_class/parameters/path
module=/sys/module/brcmfmac/parameters/firmware_path
[ "$#" = 1 ] && [ "$(id -u)" = 0 ] || exit 60
case "$1" in boot|0|1|2) mode=$1;;*)exit 60;;esac
[ -d /run/hbl-four-module ] && [ ! -L /run/hbl-four-module ] || exit 61
if [ ! -e "$state" ];then mkdir -m 700 "$state";fi
[ -d "$state" ] && [ ! -L "$state" ] && [ "$(stat -c '%u:%a' "$state")" = 0:700 ] || exit 61
mkdir "$state/lock" || exit 62
restore_search() {
    if [ -f "$state/search" ];then
        if [ -s "$state/search" ];then cat "$state/search" > "$search";else printf '\000' > "$search";fi
    fi
}
finish() { rc=$?;trap - 0;restore_search || rc=90;rmdir "$state/lock" || rc=90;exit "$rc"; }
trap finish 0
wait_driver() {
    n=0
    until [ -r "$module" ] && /usr/bin/wl ver >/dev/null 2>&1;do
        n=$((n+1));[ "$n" -lt 20 ] || return 1;sleep 1
    done
}
power() {
    dbus-send --system --print-reply --reply-timeout=2000 --dest=com.hasselblad.config /config org.freedesktop.DBus.Properties.Set string:com.hasselblad.config string:WIFI_power variant:boolean:"$1" >/dev/null
}
power_value() {
    dbus-send --system --print-reply --reply-timeout=2000 --dest=com.hasselblad.config /config org.freedesktop.DBus.Properties.Get string:com.hasselblad.config string:WIFI_power | sed -n 's/.*boolean \(true\|false\).*/\1/p'
}
ap_ready() {
    systemctl is-active --quiet network-manager hostapd &&
    iw dev | grep -q 'type AP'
}
wait_ap() { n=0;until ap_ready;do n=$((n+1));[ "$n" -lt 12 ] || return 1;sleep 1;done; }
if [ "$mode" = boot ];then
    # 冷启动只保存原厂驱动来源，绝不主动装入引闪固件、改频段或写配置。
    [ ! -e "$state/module" ] && [ ! -e "$state/search" ] || exit 63
    wait_driver || exit 64
    original=$(cat "$module");case "$original" in ''|test);;*)exit 64;;esac
    [ "$(wc -c < "$search")" -le 4096 ] || exit 64
    printf '%s' "$original" > "$state/module"
    cat "$search" > "$state/search"
    printf factory > "$state/driver"
    v=$(power_value)
    case "$v" in true)wait_ap || exit 65;echo radio-mode-ready:1;;false)echo radio-mode-ready:0;;*)exit 65;;esac
    exit 0
fi
[ -f "$state/module" ] && [ -f "$state/search" ] && [ -f "$state/driver" ] || exit 66
original=$(cat "$state/module");case "$original" in ''|test);;*)exit 66;;esac
current=$(cat "$state/driver");case "$current" in factory|flash);;*)exit 66;;esac
if [ "$mode" = 2 ];then target=flash;else target=factory;fi
# 保持原厂频段和地区字段；仅用户明确选择 Wi-Fi/关闭时修改 power。
power false
systemctl stop network-manager hostapd
if [ "$current" != "$target" ];then
    if [ "$target" = flash ];then
        [ "$(sha256sum "$base/radio.bin" | cut -d' ' -f1)" = 86d10d4131bcaa90dd0781545cec918ab10e56fd3d808c2dc85a019ee9edba98 ] || exit 67
        mkdir -p "$state/firmware/test/brcm"
        cp "$base/radio.bin" "$state/firmware/test/brcm/brcmfmac4356-pcie.bin"
    fi
    # 任一中途失败后拒绝继续猜测驱动身份，由冷启动重建。
    printf unknown > "$state/driver"
    rmmod brcmfmac
    if [ "$target" = flash ];then
        printf '%s' "$state/firmware" > "$search"
        modprobe brcmfmac firmware_path=test
    else
        restore_search
        if [ "$original" = test ];then modprobe brcmfmac firmware_path=test;else modprobe brcmfmac;fi
    fi
    # 在加载完成前保留固件搜索位置。
    wait_driver || exit 68
    restore_search
    printf '%s' "$target" > "$state/driver"
fi
if [ "$mode" = 2 ];then
    /usr/bin/wl mpc 0 >/dev/null
    /usr/bin/wl band b >/dev/null
    /usr/bin/wl up >/dev/null
    /usr/bin/wl scansuppress 1 >/dev/null
    /usr/bin/wl chanspec 2/20 >/dev/null
    /usr/bin/wl phy_txpwrindex 10 10 >/dev/null
    [ "$(/usr/bin/wl phyreg 0 b)" = 0x5854 ] || exit 69
    case "$(/usr/bin/wl phyreg 17 b)" in 0x0000|0x0);;*)exit 69;;esac
elif [ "$mode" = 1 ];then
    # Off and a freshly restored driver can both leave the interface down.
    # hostapd's HT40 coexistence scan requires a live radio before startup.
    /usr/bin/wl scansuppress 0 >/dev/null
    /usr/bin/wl up >/dev/null
    systemctl start network-manager
    power true
    wait_ap || exit 70
else
    /usr/bin/wl down >/dev/null
fi
printf 'radio-mode-ready:%s\n' "$mode"
