#!/bin/sh
set -eu
. /tmp/hbl-x1d-rp/common.sh
stage=arguments
[ "$#" = 1 ] || die 59
mode=$1
case "$mode" in --stage-ui|--enable) ;; *) die 59;; esac
package_check
if [ "$mode" = --stage-ui ]; then
    sh "$d/preflight.sh" || die 64
    mkdir -m 700 "$s"
    printf '%s\n' x1d-replay-session-v1 > "$s/owner"
    sha256sum "$d/manifest.sha256" | cut -d' ' -f1 > "$s/package.sha256"
else
    state_check
    [ -f "$s/ui-ready" ] && [ ! -e "$s/enabled" ] && [ ! -e "$s/release" ] && [ ! -e "$s/restore-started" ] || die 63
    cmp -s "$units/victory-gui.service.d/$tag" "$s/gui.hold" || die 63
fi
finish() {
    result=$?
    trap - 0 1 2 15
    if [ "$result" != 0 ]; then
        printf 'replay-install-failed stage=%s exit=%s\n' "$stage" "$result" > "$s/install.status"
        if sh "$d/restore.sh"; then printf '%s\n' replay-rollback-complete; else printf '%s\n' replay-rollback-incomplete; fi
    fi
    exit "$result"
}
trap finish 0
trap 'exit 72' 1 2 15
if [ "$mode" = --stage-ui ]; then
    stage=begin-hold
    "$d/replay-check" --begin || die 65
    printf '%s\n' '[Service]' 'Restart=no' 'Environment=X1D_REPLAY_SESSION=1' \
        'Environment=LD_PRELOAD=/tmp/hbl-x1d-rp/libx1d-replay-session.so' > "$s/gui.hold"
    stage=gui-hold-dropin
    install_drop victory-gui "$s/gui.hold"
    systemctl daemon-reload
    stage=gui-hold-restart
    systemctl restart victory-gui || die 66
    wait_running victory-gui "$(base_hash victory-gui)" || die 66
    stage=gui-hold-health
    for n in 1 2 3 4 5 6 7 8 9 10; do "$d/replay-check" --gpu && break; sleep 1; done
    "$d/replay-check" --gpu || die 67
    p=$(pidofunit victory-gui)
    grep -Fq "$d/libx1d-replay-session.so" "/proc/$p/maps" || die 67
    owners || die 67
    : > "$s/ui-ready"
    printf '%s\n' replay-ui-hold-and-gpu-ready > "$s/install.status"
else
    stage=before-enable
    baseline_check
    "$d/replay-check" --gpu || die 67
    for role in configstore storage-daemon jpeg-daemon; do running "$role" "$(base_hash "$role")" && clean_unit "$role" || die 64; done
    owners || die 64
    stage=gui-replay
    printf '%s\n' '[Service]' 'Restart=no' 'Environment=X1D_REPLAY_SESSION=1' \
        'Environment="LD_PRELOAD=/tmp/hbl-x1d-rp/libx1d-replay-session.so /tmp/hbl-x1d-rp/libx1d-replay-provider.so"' > "$s/gui.full"
    # 只替换仍等于本轮保持模板的私有文件，拒绝覆盖其他会话修改。
    cmp -s "$units/victory-gui.service.d/$tag" "$s/gui.hold" || die 68
    cat "$s/gui.full" > "$units/victory-gui.service.d/$tag"
    systemctl daemon-reload
    systemctl restart victory-gui || die 66
    wait_running victory-gui "$(base_hash victory-gui)" || die 66
    for n in 1 2 3 4 5 6 7 8 9 10; do "$d/replay-check" --gpu && break; sleep 1; done
    "$d/replay-check" --gpu && owners || die 67
    stage=loaded-maps
    p=$(pidofunit victory-gui)
    grep -Fq "$d/libx1d-replay-provider.so" "/proc/$p/maps" && grep -Fq "$d/libx1d-replay-session.so" "/proc/$p/maps" || die 67
    : > "$s/enabled"
    # 完成时释放活动保持；候选与状态观察继续存在，正常待机不改设置。
    : > "$s/release"
    printf '%s\n' replay-session-loaded-awaiting-functional-validation > "$s/install.status"
fi
trap - 0 1 2 15
cat "$s/install.status"
