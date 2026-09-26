#!/bin/sh
# 临时替换本次运行的无线固件；只查询 marker/ready，不持有或发射。
set -eu
umask 077
phase=preflight
d=/tmp/hbl-wireless-flash
s=$d/formal-state
p=/sys/module/firmware_class/parameters/path
module=/sys/module/brcmfmac/parameters/firmware_path
[ "$#" = 0 ] && [ "$(id -u)" = 0 ] || exit 80
[ -d "$d" ] && [ ! -L "$d" ] && [ "$(stat -c '%u:%a' "$d")" = 0:700 ] || exit 80
[ -d "$s" ] && [ ! -L "$s" ] && [ "$(stat -c '%u:%a' "$s")" = 0:700 ] || exit 80
[ "$(cat "$s/owner")" = formal-linux-install-v1 ] || exit 80
[ ! -e "$s/radio-snapshot-complete" ] && [ ! -e "$d/test" ] && [ ! -L "$d/test" ] || exit 80
[ "$(sha256sum /lib/firmware/test/brcm/brcmfmac4356-pcie.bin | cut -d' ' -f1)" = e5eb76a8b333e402b213843e2e93ff771615adcbc05ca7113d04ef0951555159 ] || exit 81
cd "$d"
sha256sum -c manifest.sha256 >/dev/null || exit 81
mkdir -p "$d/test/brcm"
cp /lib/firmware/test/brcm/brcmfmac4356-pcie.bin "$d/test/brcm/brcmfmac4356-pcie.bin"
dd if="$d/delta/0.bin" bs=1 seek=307100 1<>"$d/test/brcm/brcmfmac4356-pcie.bin" 2>/dev/null
dd if="$d/delta/1.bin" bs=1 seek=399416 1<>"$d/test/brcm/brcmfmac4356-pcie.bin" 2>/dev/null
dd if="$d/delta/2.bin" bs=1 seek=606750 1<>"$d/test/brcm/brcmfmac4356-pcie.bin" 2>/dev/null
[ "$(sha256sum "$d/test/brcm/brcmfmac4356-pcie.bin" | cut -d' ' -f1)" = 86d10d4131bcaa90dd0781545cec918ab10e56fd3d808c2dc85a019ee9edba98 ] || exit 82
[ -r "$p" ] && [ -w "$p" ] && [ -r "$module" ] || exit 83
previous=$(cat "$module")
case "$previous" in ''|test) ;; *) exit 83;; esac
[ "$(wc -c < "$p")" -le 4096 ] || exit 83
cp "$p" "$s/firmware-class.path"
printf '%s' "$previous" > "$s/module-firmware.path"
for service in network-manager hostapd; do
    # 目标旧 systemctl 会把 loaded/inactive 的 hostapd 显示为 is-active=unknown。
    # 只读取这两项属性，先确认服务存在，再保存实际 ActiveState。
    unit=$(systemctl show -p LoadState -p ActiveState "$service") || exit 83
    load=$(printf '%s\n' "$unit" | sed -n 's/^LoadState=//p')
    active=$(printf '%s\n' "$unit" | sed -n 's/^ActiveState=//p')
    [ "$load" = loaded ] || exit 83
    case "$active" in active) printf 'active\n';; inactive|failed) printf 'inactive\n';; *) exit 83;; esac > "$s/$service.active"
    printf '%s\n' "$unit" > "$s/$service.unit"
done
: > "$s/radio-snapshot-complete"
restore_class_path() {
    if [ -s "$s/firmware-class.path" ]; then cat "$s/firmware-class.path" > "$p"; else printf '\000' > "$p"; fi
    [ "$(cat "$p")" = "$(cat "$s/firmware-class.path")" ]
}
on_exit() {
    result=$?
    trap - 0 1 2 15
    if ! restore_class_path; then printf '%s\n' firmware-class-path-restore-failed; result=87; fi
    printf 'phase=%s exit=%s\n' "$phase" "$result" >"$s/radio-prepare.status"
    exit "$result"
}
trap on_exit 0
trap 'exit 88' 1 2 15
phase=driver-reload
: > "$s/radio-mutated"
systemctl stop network-manager hostapd || exit 84
rmmod brcmfmac || exit 84
printf '%s' "$d" > "$p"
modprobe brcmfmac firmware_path=test || exit 85
: > "$s/radio-injected"
# modprobe 返回只表示异步固件请求已排队。标记验证前必须保留搜索路径。
phase=wait-driver
n=0
until /usr/bin/wl ver >/dev/null 2>&1;do
    n=$((n+1));[ "$n" -lt 20 ] || exit 86
    sleep 1
done
configure() {
    phase=$1;shift
    /usr/bin/wl "$@" >/dev/null 2>&1 || exit 86
}
configure configure-mpc mpc 0
configure configure-band band b
configure configure-up up
configure configure-scan scansuppress 1
configure configure-channel chanspec 2/20
configure configure-power phy_txpwrindex 10 10
phase=verify-marker
n=0
while :;do
    marker=$(/usr/bin/wl phyreg 0 b 2>/dev/null) || exit 86
    [ "$marker" = 0x5854 ] && break
    n=$((n+1));[ "$n" -lt 10 ] || exit 86
    sleep 1
done
phase=verify-idle
ready=$(/usr/bin/wl phyreg 17 b) || exit 86
case "$ready" in 0x0000|0x0) ;; *) exit 86;; esac
phase=restore-search-path
restore_class_path || exit 87
: > "$s/radio-prepared"
phase=ready
printf '%s\n' formal-radio-prepared-marker-5854-default-off
