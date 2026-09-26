#!/bin/sh
# 正式临时 Linux 链安装；本脚本不安装、解除或修改 FARM/AF 钩子。
set -eu
umask 077
d=/tmp/hbl-wireless-flash
s=$d/formal-state
gui=/run/systemd/system/victory-gui.service.d/80-hbl-formal-flash.conf
farm=/run/systemd/system/msg2dbus-farm.service.d/80-hbl-formal-flash.conf
mode=${1:-}
[ "$#" = 1 ] || exit 59
case "$mode" in --stage-ui|--start-observer) ;; *) exit 59;; esac
[ "$(id -u)" = 0 ] || exit 60
[ -d "$d" ] && [ ! -L "$d" ] && [ "$(stat -c '%u:%a' "$d")" = 0:700 ] || exit 60
if [ "$mode" = --stage-ui ]; then
    [ ! -e "$s" ] && [ ! -L "$s" ] || exit 60
else
    [ -d "$s" ] && [ ! -L "$s" ] && [ "$(stat -c '%u:%a' "$s")" = 0:700 ] || exit 60
    [ "$(cat "$s/owner")" = formal-linux-install-v1 ] && [ -f "$s/ui-hold-ready" ] && [ ! -e "$s/install-complete" ] || exit 60
fi
cd "$d"
# 包只允许明确的相对文件；manifest 不得使校验跳出这个新建目录。
[ -f manifest.sha256 ] && [ ! -L manifest.sha256 ] || exit 61
awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.\/-]+$/ || $2~/^\// || $2~/(^|\/)\.\.(\/|$)/ {bad=1} END {exit bad}' manifest.sha256 || exit 61
while read -r digest file; do [ -f "$file" ] && [ ! -L "$file" ] || exit 61; done < manifest.sha256
sha256sum -c manifest.sha256 >/dev/null || exit 61
for file in formal-install.sh formal-restore.sh formal-prepare-radio.sh libhbl-formal.so libhbl-formal-observer.so formal-ui.rcc formal-sync-hook-check formal-client-check formal-netlink-probe formal-system-check formal-hold.check; do
    [ -f "$file" ] && [ ! -L "$file" ] || exit 61
    awk -v wanted="$file" '$2==wanted {n++} END {exit n!=1}' manifest.sha256 || exit 61
done
[ "$(sha256sum /usr/bin/victory-gui | cut -d' ' -f1)" = d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b ] || exit 62
[ "$(sha256sum /usr/lib/libappscommon.so.1.0.0 | cut -d' ' -f1)" = 2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263 ] || exit 62
[ "$(sha256sum /usr/bin/msg2dbus | cut -d' ' -f1)" = 988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1 ] || exit 62
if [ "$mode" = --stage-ui ]; then
for file in "$gui" "$farm" /run/systemd/system/hbl-wireless-worker.service "$d/formal-stop.request" "$d/formal-enable.ready" "$d/formal-enable.confirmed" "$d/formal-worker.sock" "$d/formal-ui.sock" "$d/formal-runtime.status" "$d/formal-observer.status" "$d/formal-worker.status" "$d/formal-install.status" "$d/formal-restore.status"; do
    [ ! -e "$file" ] && [ ! -L "$file" ] || exit 63
done
for directory in /run/systemd/system/victory-gui.service.d /run/systemd/system/msg2dbus-farm.service.d; do
    [ ! -L "$directory" ] || exit 63
done
[ -z "${LD_PRELOAD:-}" ] || exit 63
for service in victory-gui msg2dbus-farm; do
    systemctl is-active --quiet "$service" || exit 63
    if systemctl show -p Environment "$service" | grep -q 'LD_PRELOAD='; then exit 63; fi
    pid=$(systemctl show -p MainPID "$service" | cut -d= -f2)
    case "$pid" in ''|0|*[!0-9]*) exit 63;; esac
    [ -r "/proc/$pid/environ" ] || exit 63
    if tr '\000' '\n' < "/proc/$pid/environ" | grep -q '^LD_PRELOAD='; then exit 63; fi
done
mkdir "$s"
printf '%s\n' formal-linux-install-v1 > "$s/owner"
sha256sum manifest.sha256 | cut -d' ' -f1 > "$s/package-manifest.sha256"
else
    [ "$(sha256sum manifest.sha256 | cut -d' ' -f1)" = "$(cat "$s/package-manifest.sha256")" ] || exit 63
    cmp -s "$gui" "$s/gui.dropin" && [ ! -e "$farm" ] && [ ! -L "$farm" ] || exit 63
    "$d/formal-system-check" --require-held || exit 63
fi
exec 3>&1
exec >> "$d/formal-install.log" 2>&1
cleanup() {
    result=$?
    trap - 0 1 2 15
    if [ "$result" != 0 ]; then
        printf 'install-failed=%s rollback=before-farm-install\n' "$result"
        if sh "$d/formal-restore.sh" --before-farm-install; then
            printf '%s\n' formal-install-failed-original-linux-restored > "$d/formal-install.status"
            printf '%s\n' formal-install-failed-original-linux-restored >&3
        else
            printf '%s\n' formal-install-failed-rollback-incomplete > "$d/formal-install.status"
            printf '%s\n' formal-install-failed-rollback-incomplete-see-log >&3
        fi
    fi
    exit "$result"
}
trap cleanup 0
trap 'exit 72' 1 2 15
if [ "$mode" = --stage-ui ]; then
printf '%s\n' stage=selfchecks
chmod 700 "$d/formal-sync-hook-check" "$d/formal-client-check" "$d/formal-netlink-probe" "$d/formal-system-check"
HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD="$d/libhbl-formal-observer.so" "$d/formal-sync-hook-check" || exit 64
"$d/formal-client-check" --check-direct || exit 64
"$d/formal-system-check" --check || exit 64
"$d/formal-system-check" --check-files || exit 64
"$d/formal-system-check" --begin-hold || exit 64
printf '%s\n' '[Service]' 'Environment=HBL_FORMAL_ENABLE_PLUGIN=1' 'Environment=HBL_FORMAL_INSTALL_HOLD=1' 'UMask=0077' 'Environment=LD_PRELOAD=/tmp/hbl-wireless-flash/libhbl-formal.so' > "$s/gui.dropin"
if [ ! -d /run/systemd/system/victory-gui.service.d ]; then
    mkdir /run/systemd/system/victory-gui.service.d
    : > "$s/created-gui-directory"
fi
[ ! -e "$gui" ] && [ ! -L "$gui" ] || exit 69
(set -C; cat "$s/gui.dropin" > "$gui") || exit 69
: > "$s/created-gui-dropin"
systemctl daemon-reload
printf '%s\n' stage=gui
systemctl restart victory-gui || exit 70
gui_ready() {
    systemctl is-active --quiet victory-gui || return 1
    [ "$(cat "$d/formal-runtime.status")" = formal-ui-loaded-default-off ] || return 1
    p=$(systemctl show -p MainPID victory-gui | cut -d= -f2)
    case "$p" in ''|0|*[!0-9]*) return 1;; esac
    grep -q '/tmp/hbl-wireless-flash/libhbl-formal.so' "/proc/$p/maps" || return 1
    [ -S "$d/formal-ui.sock" ] && [ ! -L "$d/formal-ui.sock" ] || return 1
    "$d/formal-system-check" --require-held
}
for n in 1 2 3 4 5 6 7 8 9 10; do gui_ready 2>/dev/null && break; sleep 1; done
gui_ready || exit 70
: > "$s/ui-hold-ready"
printf '%s\n' formal-ui-hold-ready-default-off > "$d/formal-install.status"
trap - 0 1 2 15
cat "$d/formal-install.status" >&3
exit 0
fi
"$d/formal-system-check" --require-held || exit 64
printf '%s\n' stage=prepare-radio
sh "$d/formal-prepare-radio.sh" || exit 65
"$d/formal-netlink-probe" || exit 66
"$d/formal-system-check" --require-held || exit 66
printf '%s\n' '[Service]' 'Environment=HBL_FORMAL_SYNC_OBSERVE=1' 'Environment=LD_PRELOAD=/tmp/hbl-wireless-flash/libhbl-formal-observer.so' > "$s/farm.dropin"
if [ ! -d /run/systemd/system/msg2dbus-farm.service.d ]; then
    mkdir /run/systemd/system/msg2dbus-farm.service.d
    : > "$s/created-farm-directory"
fi
[ ! -e "$farm" ] && [ ! -L "$farm" ] || exit 67
(set -C; cat "$s/farm.dropin" > "$farm") || exit 67
: > "$s/created-farm-dropin"
systemctl daemon-reload
printf '%s\n' stage=observer
systemctl restart msg2dbus-farm || exit 68
observer_ready() {
    systemctl is-active --quiet msg2dbus-farm || return 1
    p=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
    case "$p" in ''|0|*[!0-9]*) return 1;; esac
    grep -q '/tmp/hbl-wireless-flash/libhbl-formal-observer.so' "/proc/$p/maps" || return 1
    grep -q '^stage=ready meta=1 observe=1$' "$d/formal-observer.status" || return 1
    [ "$(head -n 1 "$d/formal-worker.status")" = formal-worker-ready-default-off ] || return 1
    grep -q "^master=0 radio-held=0 radio-busy=0 same-process=1 pid=$p\$" "$d/formal-worker.status" || return 1
    [ -S "$d/formal-worker.sock" ] && [ ! -L "$d/formal-worker.sock" ] || return 1
    "$d/formal-system-check" --require-held
}
for n in 1 2 3 4 5 6 7 8 9 10; do observer_ready 2>/dev/null && break; sleep 1; done
observer_ready || exit 68
observer_ready || exit 70
printf '%s\n' formal-linux-ready-default-off > "$d/formal-install.status"
: > "$s/install-complete"
trap - 0 1 2 15
cat "$d/formal-install.status" >&3
