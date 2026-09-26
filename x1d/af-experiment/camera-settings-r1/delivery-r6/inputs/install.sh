#!/bin/sh
. /tmp/hbl-x1d-combined/common.sh
phase=${1:-}
[ "$#" = 1 ] || exit 59
case "$phase" in preflight|ui|bus|release) ;; *) exit 59;; esac
verify_package || exit 60
if [ "$phase" = preflight ] || [ "$phase" = ui ]; then
    for path in "$s" "$a" /tmp/hbl-wireless-flash /tmp/hbl-af-ui-r4 /tmp/hbl-af-bus-r3 "$gui" "$farm"; do absent "$path" || exit 61;done
    [ -d "$units" ] && [ ! -L "$units" ] || exit 61
    for role in victory-gui msg2dbus-farm; do clean_service "$role" || exit 61;done
    for directory in "$units/victory-gui.service.d" "$units/msg2dbus-farm.service.d"; do [ ! -L "$directory" ] || exit 61;done
    "$r/system-check" --check && "$r/system-check" --check-files && "$r/system-check" --require-ui-stage || exit 62
    if [ "$phase" = preflight ]; then "$r/bus-local-check" || exit 62;printf '%s\n' af-only-preflight-ready;exit 0;fi
    mkdir -m 700 "$s" "$a"
    printf '%s\n' hbl-af-only-v1 > "$s/owner"
    sha256sum "$r/manifest.sha256" | cut -d' ' -f1 > "$s/package.sha256"
    "$r/system-check" --begin-hold || exit 62
    printf '%s\n' '[Service]' 'Restart=no' 'UMask=0077' 'Environment=HBL_AF_ONLY_ENABLE=1' 'Environment=HBL_AF_ONLY_HOLD=1' 'Environment=HBL_AF_SETTINGS_ENABLE=1' 'Environment=HBL_AF_UI_R4_ENABLE=0' "Environment=LD_PRELOAD=$r/libhbl-af-only.so:$r/af/libhbl-af-ui.so" > "$s/gui.dropin"
    if [ ! -d "$units/victory-gui.service.d" ]; then mkdir "$units/victory-gui.service.d";: > "$s/gui.directory";fi
    : > "$s/gui.touched"
    (set -C;cat "$s/gui.dropin" > "$gui") || exit 63
    systemctl daemon-reload
    systemctl restart victory-gui || exit 64
    wait_ready gui_ready || exit 64
    : > "$s/ui.done"
    printf '%s\n' af-only-ui-ready
    exit 0
fi
owned && owned_dropins && [ -f "$s/ui.done" ] || exit 65
case "$phase" in
bus)
    absent "$farm" && absent "$s/bus.done" && held || exit 65
    printf '%s\n' '[Service]' 'Restart=no' 'UMask=0077' 'Environment=HBL_AF_SETTINGS_ENABLE=1' "Environment=LD_PRELOAD=$r/af/libhbl-af-bus.so" > "$s/farm.dropin"
    if [ ! -d "$units/msg2dbus-farm.service.d" ]; then mkdir "$units/msg2dbus-farm.service.d";: > "$s/farm.directory";fi
    : > "$s/farm.touched"
    (set -C;cat "$s/farm.dropin" > "$farm") || exit 67
    systemctl daemon-reload
    systemctl restart msg2dbus-farm || exit 68
    wait_ready bus_ready || exit 68
    : > "$s/bus.done"
    printf '%s\n' af-only-bus-ready
    ;;
release)
    [ -f "$s/bus.done" ] && regular "$s/af-installed.sha256" && absent "$s/hold.release" || exit 65
    [ "$(wc -c < "$s/af-installed.sha256")" = 65 ] && grep -Eq '^[0-9a-f]{64}$' "$s/af-installed.sha256" || exit 65
    gui_ready && bus_ready && held 10000 || exit 65
    (set -C;printf release > "$s/hold.release") || exit 71
    sleep 1
    "$r/system-check" --require-active || exit 71
    : > "$s/release.done"
    printf '%s\n' af-only-installed-ready-for-user
    ;;
esac
