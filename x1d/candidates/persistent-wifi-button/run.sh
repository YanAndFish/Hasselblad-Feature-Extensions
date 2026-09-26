#!/bin/sh
# 受控独立临时装载、状态、恢复。持久安装在单独脚本中。
set -eu
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$source/common.sh"
gui=/run/systemd/system/victory-gui.service.d/91-hbl-wifi-probe.conf
factory() {
    regular "$gui" && regular "$source/temporary.conf" && cmp -s "$gui" "$source/temporary.conf" || return 1
    [ "$(value victory-gui DropInPaths)" = "$gui" ] || return 1
    systemctl stop victory-gui || return 1
    ! systemctl is-active --quiet victory-gui || return 1
    rm -- "$gui"
    systemctl daemon-reload && systemctl start victory-gui || return 1
    n=0
    while [ "$n" -lt 15 ];do
        if clean victory-gui && "$source/health" --require-ready >/dev/null;then printf 'factory-restored\n';return 0;fi
        n=$((n+1));sleep 1
    done
    return 1
}
verify "$source" || exit 60
case "${1:-}" in
preflight)
    for role in victory-gui msg2dbus-farm configstore jpeg-daemon storage-daemon;do clean "$role" || exit 61;done
    "$source/health" --require-ready >/dev/null
    absent "$r"
    printf 'probe-preflight-ready\n'
    ;;
temporary)
    sh "$source/run.sh" preflight >/dev/null
    absent "$source/temporary.conf" && absent "$gui" && absent "$gui.new" || exit 62
    pid msg2dbus-farm > "$source/bus.pid"
    printf '[Service]\nExecStart=\nExecStart=/bin/sh %s/launch.sh\n' "$source" > "$source/temporary.conf"
    [ -d /run/systemd/system/victory-gui.service.d ] || mkdir -m 755 /run/systemd/system/victory-gui.service.d
    cp "$source/temporary.conf" "$gui.new"
    mv "$gui.new" "$gui"
    on_exit() {
        code=$?;trap - 0
        if [ "$code" -ne 0 ];then factory > "$source/recovery.log" 2>&1 || printf 'recovery-required\n' > "$source/recovery.log";fi
        exit "$code"
    }
    trap on_exit 0
    systemctl daemon-reload
    systemctl restart victory-gui
    n=0
    while [ "$n" -lt 35 ];do
        if ready;then
            [ "$(pid msg2dbus-farm)" = "$(cat "$source/bus.pid")" ] || exit 63
            printf 'probe-temporary-ready\n';exit 0
        fi
        [ ! -f "$r/fallback.reason" ] || exit 64
        n=$((n+1));sleep 1
    done
    exit 65
    ;;
status)
    ready
    printf 'probe-ready\n'
    ;;
restore)
    factory
    ;;
archive-runtime)
    clean victory-gui
    private "$r" && absent /run/hbl-wifi-probe-temporary-evidence || exit 66
    mv "$r" /run/hbl-wifi-probe-temporary-evidence
    printf 'runtime-evidence-preserved\n'
    ;;
*) exit 59;;
esac
