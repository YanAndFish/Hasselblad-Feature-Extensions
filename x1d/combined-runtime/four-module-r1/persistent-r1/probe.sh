#!/bin/sh
# 临时只读通路证明；FARM 写入请求为零。结束后恢复原消息服务配置。
set -eu
umask 077
r=/tmp/hbl-boot-probe-r1
d=/tmp/hbl-wireless-flash
u=/run/hbl-four-module
override=/run/systemd/system/msg2dbus-farm.service.d/90-hbl-boot-probe.conf
cd "$r"
sha256sum -c manifest.sha256 >/dev/null
[ ! -e "$override" ] && [ ! -L "$override" ]
[ ! -e "$u/boot-transport.status" ] && [ ! -L "$u/boot-transport.status" ]
[ "$(sha256sum "$d/manifest.sha256" | cut -d' ' -f1)" = f53e6a360c2eb68c1fce98ba52412b0479704166fa70c191e3662a7f154043b9 ]
[ "$(sha256sum "$d/libhbl-formal-observer.so" | cut -d' ' -f1)" = c960ea0e8685073adf3fc593e3fbe4c3e58a44dcbf29cb42ca8bb68733fc53e0 ]
(cd "$d";sha256sum -c manifest.sha256 >/dev/null)
systemctl is-active --quiet victory-gui msg2dbus-farm system-manager configstore jpeg-daemon
[ ! -e "$d/formal-stop.request" ]
[ -f "$d/formal-enable.ready" ] && [ "$(cat "$d/formal-enable.confirmed")" = ready ]
gui=$(systemctl show -p MainPID victory-gui | cut -d= -f2)
farm=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
case "$gui:$farm" in *[!0-9:]*|0:*|*:0|:*) exit 61;; esac
health() {
    h=$("$d/formal-system-check" --require-ui-stage)
    case "$h" in 'system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0'|'system=4 suc=0 farm=0 pwr=0 ui-power=1 hold=0') ;; *) return 1;; esac
}
health
HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD="$r/probe.so:$d/libhbl-formal-observer.so" "$d/formal-sync-hook-check" >selfcheck.txt
grep -q '^sync-hook-selftest: own=10 forwarded=.* status=1 hardware=0$' selfcheck.txt
printf '%s\n' '[Service]' 'Environment=HBL_BOOT_READONLY_PROBE=1' "Environment=LD_PRELOAD=$r/probe.so:$d/libhbl-formal-observer.so" >probe.conf
stop_requested=0
stop_confirmed=0
changed=0
restored=0
restore_attempted=0
ready_wait() {
    f=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
    case "$f" in ''|0|*[!0-9]*) return 1;; esac
    n=0
    while [ "$n" -lt 20 ]; do
        x=$(cat "$d/formal-worker.status" 2>/dev/null || true)
        [ "$x" = "formal-worker-ready-default-off
master=0 radio-held=0 radio-busy=0 same-process=1 pid=$f" ] && return 0
        n=$((n+1));sleep 1
    done
    return 1
}
restore() {
    [ "$restored" = 0 ] || return 0
    [ "$restore_attempted" = 0 ] || return 1
    restore_attempted=1
    [ "$stop_requested" = 0 ] || [ "$stop_confirmed" = 1 ] || return 1
    if [ "$changed" = 1 ]; then
        systemctl stop msg2dbus-farm || return 1
        [ "$(systemctl show -p MainPID msg2dbus-farm)" = MainPID=0 ] || return 1
        if [ -f "$override" ]; then cmp "$override" probe.conf || return 1;rm "$override" || return 1;fi
        systemctl daemon-reload || return 1
        if [ -f "$d/formal-stop.request" ]; then mv "$d/formal-stop.request" "$r/stop-archived" || return 1;fi
        systemctl start msg2dbus-farm || return 1
        ready_wait || return 1
    elif [ "$stop_requested" = 1 ]; then
        # 已明确停止 worker、但尚未改配置时，按同一已知版本恢复服务。
        systemctl stop msg2dbus-farm || return 1
        [ "$(systemctl show -p MainPID msg2dbus-farm)" = MainPID=0 ] || return 1
        if [ -f "$d/formal-stop.request" ]; then mv "$d/formal-stop.request" "$r/stop-archived" || return 1;fi
        systemctl start msg2dbus-farm || return 1
        ready_wait || return 1
    fi
    if [ "$stop_requested" = 1 ]; then
        if [ -e "$d/formal-enable.ready" ]; then mv "$d/formal-enable.ready" "$r/probe-enable.ready" || return 1;fi
        if [ -e "$d/formal-enable.confirmed" ]; then mv "$d/formal-enable.confirmed" "$r/probe-enable.confirmed" || return 1;fi
        printf ready >"$d/formal-enable.ready" || return 1
        n=0
        while [ "$n" -lt 15 ]; do
            [ "$(cat "$d/formal-enable.confirmed" 2>/dev/null || true)" = ready ] && break
            n=$((n+1));sleep 1
        done
        [ "$(cat "$d/formal-enable.confirmed")" = ready ] || return 1
    fi
    [ "$(systemctl show -p MainPID victory-gui)" = "MainPID=$gui" ] || return 1
    health || return 1
    restored=1
    printf original-message-service-restored >restored || return 1
}
cleanup() {
    rc=$?
    trap - 0 1 2 15
    if ! restore; then printf restoration-needs-review >result;exit 81;fi
    if [ "$rc" != 0 ]; then printf readonly-probe-failed-restored >result;fi
    exit "$rc"
}
trap cleanup 0 1 2 15
(set -C;printf stop >"$d/formal-stop.request")
stop_requested=1
n=0
while [ "$n" -lt 20 ]; do
    x=$(cat "$d/formal-worker.status")
    [ "$x" = "formal-worker-stopped-default-off
master=0 radio-held=0 radio-busy=0 same-process=1 pid=$farm" ] && break
    n=$((n+1));sleep 1
done
[ "$x" = "formal-worker-stopped-default-off
master=0 radio-held=0 radio-busy=0 same-process=1 pid=$farm" ]
stop_confirmed=1
health
systemctl stop msg2dbus-farm
[ "$(systemctl show -p MainPID msg2dbus-farm)" = MainPID=0 ]
mv "$d/formal-enable.ready" old.ready
mv "$d/formal-enable.confirmed" old.confirmed
mv "$d/formal-stop.request" old.stop
changed=1
(set -C;cat probe.conf >"$override")
systemctl daemon-reload
systemctl start msg2dbus-farm
ready_wait
n=0
while [ "$n" -lt 12 ]; do
    state=$(cat "$u/boot-transport.status" 2>/dev/null || true)
    case "$state" in stage=readonly-probe-ready\ *) break;; stage=readonly-probe-failed\ *|stage=source-unavailable\ *) break;; esac
    n=$((n+1));sleep 1
done
printf '%s\n' "$state" >transport-result.txt
case "$state" in 'stage=readonly-probe-ready requests=3 writes=0 pid='*) ;; *) exit 72;; esac
restore
printf readonly-probe-ready-original-restored >result
