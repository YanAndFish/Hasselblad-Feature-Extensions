#!/bin/sh
# 本脚本只管理本轮组合 Linux 链；FARM/AF 字节写入由 PC 的固定装载器串行执行。
. /tmp/hbl-x1d-combined/common.sh
phase=${1:-}
[ "$#" = 1 ] || exit 59
case "$phase" in preflight|ui|observer|provider|bridge|enable|release) ;; *) exit 59;; esac
verify_package || exit 60
if [ "$phase" = preflight ] || [ "$phase" = ui ]; then
    for path in "$s" "$d" "$a" "$r/replay-state" "$gui" "$farm"; do absent "$path" || exit 61;done
    [ -d "$units" ] && [ ! -L "$units" ] || exit 61
    for role in victory-gui msg2dbus-farm; do clean_service "$role" || exit 61;done
    for directory in "$units/victory-gui.service.d" "$units/msg2dbus-farm.service.d"; do [ ! -L "$directory" ] || exit 61;done
    "$r/system-check" --check && "$r/system-check" --check-files && "$r/system-check" --require-ui-stage || exit 62
    if [ "$phase" = preflight ]; then printf '%s\n' combined-preflight-ready;exit 0;fi
    mkdir -m 700 "$s" "$d" "$a" "$r/replay-state"
    printf '%s\n' hbl-combined-v1 > "$s/owner"
    sha256sum "$r/manifest.sha256" | cut -d' ' -f1 > "$s/package.sha256"
    cp -R "$r/flash/." "$d/"
    chmod 700 "$d" "$d/delta"
    (cd "$d" && sha256sum -c manifest.sha256 >/dev/null) || exit 62
    mkdir -m 700 "$d/formal-state"
    printf '%s\n' formal-linux-install-v1 > "$d/formal-state/owner"
    HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD="$d/libhbl-formal-observer.so" "$d/formal-sync-hook-check" || exit 62
    "$d/formal-client-check" --check-direct || exit 62
    "$r/system-check" --begin-hold || exit 62
    gui_text bridge > "$s/gui.dropin"
    if [ ! -d "$units/victory-gui.service.d" ]; then mkdir "$units/victory-gui.service.d";: > "$s/gui.directory";fi
    : > "$s/gui.touched"
    (set -C;cat "$s/gui.dropin" > "$gui") || exit 63
    systemctl daemon-reload
    systemctl restart victory-gui || exit 64
    wait_ready gui_ready || exit 64
    p=$(pid victory-gui);"$r/replay/replay-joint-check" --gpu "$p" || exit 64
    : > "$s/ui.done"
    printf '%s\n' combined-ui-ready-default-off
    exit 0
fi
owned && owned_dropins && [ -f "$s/ui.done" ] || exit 65
case "$phase" in
observer)
    absent "$farm" && absent "$s/observer.done" && absent "$r/replay-state/backend" || exit 65
    held 180000 || exit 65
    sh "$d/formal-prepare-radio.sh" || exit 66
    "$d/formal-netlink-probe" || exit 66
    held 180000 || exit 66
    printf '%s\n' '[Service]' 'Restart=no' 'UMask=0077' 'Environment=HBL_FORMAL_SYNC_OBSERVE=1' 'Environment=HBL_AF_SETTINGS_ENABLE=1' "Environment=LD_PRELOAD=$d/libhbl-formal-observer.so:$r/af/libhbl-af-bus.so" > "$s/farm.dropin"
    if [ ! -d "$units/msg2dbus-farm.service.d" ]; then mkdir "$units/msg2dbus-farm.service.d";: > "$s/farm.directory";fi
    : > "$s/farm.touched"
    (set -C;cat "$s/farm.dropin" > "$farm") || exit 67
    systemctl daemon-reload
    systemctl restart msg2dbus-farm || exit 68
    wait_ready observer_ready || exit 68
    : > "$s/observer.done"
    printf '%s\n' combined-observer-ready-default-off
    ;;
provider|bridge)
    [ -f "$s/observer.done" ] && absent "$s/hold.release" || exit 65
    if [ "$phase" = provider ]; then
        [ -f "$r/replay-state/backend/jpeg.done" ] && absent "$s/provider.done" || exit 65
        held && observer_ready || exit 65
    else
        # provider 启动失败时允许显式回到已验收桥接链；保持 deadline 原值。
        [ -f "$s/provider.started" ] && absent "$s/bridge.done" || exit 65
    fi
    gui_text "$phase" > "$s/gui.next"
    stop_gui || exit 69
    if [ "$phase" = provider ]; then : > "$s/provider.started";fi
    cmp -s "$gui" "$s/gui.dropin" || exit 69
    cat "$s/gui.next" > "$gui"
    mv "$s/gui.next" "$s/gui.dropin"
    systemctl daemon-reload
    systemctl start victory-gui || exit 70
    wait_ready gui_ready || exit 70
    p=$(pid victory-gui);"$r/replay/replay-joint-check" --gpu "$p" || exit 70
    if [ "$phase" = provider ]; then grep -Fq "$r/replay/libx1d-replay-provider.so" "/proc/$p/maps" || exit 70;fi
    sh "$r/replay/backend.sh" --status
    : > "$s/$phase.done"
    printf 'combined-%s-ready-default-off\n' "$phase"
    ;;
enable)
    [ -f "$s/provider.done" ] && absent "$d/formal-enable.ready" && absent "$d/formal-enable.confirmed" || exit 65
    held && gui_ready && observer_ready || exit 65
    (set -C;printf ready > "$d/formal-enable.ready") || exit 71
    for n in 1 2 3 4 5 6 7 8 9 10; do [ -f "$d/formal-enable.confirmed" ] && break;sleep 1;done
    [ "$(cat "$d/formal-enable.confirmed")" = ready ] || exit 71
    : > "$s/enable.done"
    printf '%s\n' combined-user-controls-enabled-default-off
    ;;
release)
    [ -f "$s/enable.done" ] && absent "$s/hold.release" || exit 65
    held 10000 || exit 65
    (set -C;printf release > "$s/hold.release") || exit 71
    sleep 1
    "$r/system-check" --require-active || exit 71
    : > "$s/release.done"
    printf '%s\n' combined-installed-ready-for-user
    ;;
esac
