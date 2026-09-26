#!/bin/sh
# 同一个 service 控制组中的有限检查；不常驻，不改相机设置。
set -eu
umask 077
r=/run/hbl-wifi-probe
expected=$1
case "$expected" in ''|0|*[!0-9]*) exit 60;;esac
mainpid() { systemctl show victory-gui -p MainPID | sed -n 's/^MainPID=//p'; }
n=0
started=$(date +%s)
while [ "$n" -lt 25 ];do
    sleep 1
    current=$(mainpid)
    # 启动中短暂为 0 可以等待；已经换进程则不接管新进程。
    case "$current" in "$expected"|0) ;; *) exit 0;;esac
    if [ -f "$r/ui.status" ];then
        status=$(cat "$r/ui.status")
        if [ "$status" = "probe-ready pid=$expected" ];then
            health_rc=0
            health=$("$r/health" --require-ready 2>&1) || health_rc=$?
            printf 'attempt=%s exit=%s %s\n' "$n" "$health_rc" "$health" >> "$r/health.log"
            accepted=0
            case "$health" in "ui-health-ready pid=$expected system=2 power=0"|"ui-health-ready pid=$expected system=4 power=1") accepted=1;;esac
            if [ "$health_rc" = 0 ] && [ "$accepted" = 1 ] && [ "$(mainpid)" = "$expected" ];then
                printf 'probe-verified pid=%s\n' "$expected" > "$r/verified"
                exit 0
            fi
        else
            case "$status" in probe-*-failed*) break;;esac
        fi
    fi
    [ "$(( $(date +%s) - started ))" -lt 25 ] || break
    n=$((n+1))
done
if [ "$(mainpid)" = "$expected" ];then
    printf 'readiness-failed-factory-restart-requested\n' > "$r/fallback.reason"
    # launch.sh 的本次开机标记仍在；重启直接使用原厂 GUI。
    systemctl --no-block restart victory-gui
fi
