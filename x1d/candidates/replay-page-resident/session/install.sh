#!/bin/sh
. /tmp/hbl-replay-page/common.sh
[ "$#" = 1 ] || exit 59
case "$1" in preflight|ui|status) ;; *) exit 59;;esac
verify_package || exit 60
if [ "$1" = status ];then
    owned && gui_ready || exit 65
    printf '%s\n' replay-page-session-ready
    exit 0
fi
absent "$s" && absent "$gui" && absent "$r/replay.status" || exit 61
[ -d "$units" ] && [ ! -L "$units" ] && [ ! -L "$units/victory-gui.service.d" ] || exit 61
for role in victory-gui msg2dbus-farm configstore jpeg-daemon storage-daemon;do clean_service "$role" || exit 61;done
# 只读检查原生 ABI/属性。前置阶段不写状态、不重启服务。
"$r/replay-health" --self-test && health || exit 62
if [ "$1" = preflight ];then printf '%s\n' replay-page-preflight-ready;exit 0;fi
mkdir -m 700 "$s"
printf '%s\n' hbl-replay-page-v1 > "$s/owner"
cp "$r/manifest.sha256" "$s/manifest.sha256"
pid msg2dbus-farm > "$s/bus.pid"
recover_on_exit() {
    result=$?;trap - 0 1 2 15
    if [ "$result" != 0 ];then
        if sh "$r/restore.sh" restore;then printf '%s\n' replay-page-install-failed-original-restored;else printf '%s\n' replay-page-install-failed-recovery-required;fi
    fi
    exit "$result"
}
trap recover_on_exit 0
trap 'exit 72' 1 2 15
printf '%s\n' '[Service]' 'Restart=no' 'UMask=0077' 'Environment=HBL_REPLAY_PAGE_ENABLE=1' "Environment=LD_PRELOAD=$r/libhbl-replay-page.so" > "$s/gui.dropin"
if [ ! -d "$units/victory-gui.service.d" ];then mkdir "$units/victory-gui.service.d";: > "$s/gui.directory";fi
: > "$s/gui.claimed"
(set -C;cat "$s/gui.dropin" > "$gui") || exit 63
systemctl daemon-reload || exit 64
systemctl restart victory-gui || exit 64
wait_ready gui_ready || exit 64
: > "$s/ui.done"
printf '%s\n' replay-page-session-ready
