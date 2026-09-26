#!/bin/sh
. /tmp/hbl-ui-af/common.sh
[ "$#" = 1 ] || exit 59
case "$1" in preflight|ui|status) ;; *) exit 59;;esac
verify_package || exit 60
if [ "$1" = status ];then owned && integrated_ready || exit 65;printf '%s\n' ui-af-session-ready;exit 0;fi
absent "$s" && absent "$gui" && absent "$r/ui.status" || exit 61
inherited_files && af_bus_ready && gui_ready af || exit 61
for role in configstore jpeg-daemon storage-daemon;do plain_service "$role" || exit 61;done
"$r/ui-health" --self-test || exit 62
if [ "$1" = preflight ];then printf '%s\n' ui-af-preflight-ready;exit 0;fi
mkdir -m 700 "$s"
printf '%s\n' hbl-ui-af-r4-v1 > "$s/owner"
cp "$r/manifest.sha256" "$s/manifest.sha256"
pid msg2dbus-farm > "$s/bus.pid"
sha256sum "$afgui" "$fixgui" "$afbus" "$afstate/owner" "$afstate/hold.release" "$afstate/af-installed.sha256" "$afstate/release.done" "$afstate/ram.started" > "$s/protected.sha256"
recover() {
    code=$?;trap - 0 1 2 15
    if [ "$code" != 0 ];then
        if sh "$r/restore.sh" restore;then printf '%s\n' ui-af-install-failed-r4-restored;else printf '%s\n' ui-af-install-failed-recovery-required;fi
    fi
    exit "$code"
}
trap recover 0
trap 'exit 72' 1 2 15
printf '%s\n' '[Service]' 'Environment=HBL_UI_AF_ENABLE=1' "Environment=LD_PRELOAD=$newpreload" > "$s/gui.dropin"
: > "$s/gui.claimed"
(set -C;cat "$s/gui.dropin" > "$gui") || exit 63
# 先正常停止 GUI，并清理仅其遗留的 UI socket；不碰 AF 后台。
stop_gui || exit 64
systemctl daemon-reload || exit 64
systemctl start victory-gui || exit 64
wait_ready integrated_ready || exit 64
: > "$s/ui.done"
printf '%s\n' ui-af-session-ready
