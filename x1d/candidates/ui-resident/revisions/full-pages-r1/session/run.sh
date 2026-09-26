#!/bin/sh
. /tmp/hbl-ui-full-r1/common.sh
[ "$#" = 1 ] || exit 59
phase=$1
case "$phase" in preflight|ui|status|restore) ;; *) exit 59;;esac
verify_package && private "$r/phases" || exit 60
# mkdir 原子锁：结果不明时先观察，禁止重发安装。
mkdir -m 700 "$r/phase.lock" || exit 62
finish() {
    result=$?;trap - 0 1 2 15
    if [ "${recording:-0}" = 1 ];then
        printf '%s\n' "$result" > "$r/phases/$phase.exit.next"
        mv "$r/phases/$phase.exit.next" "$r/phases/$phase.exit"
    fi
    rmdir "$r/phase.lock"
    exit "$result"
}
trap finish 0
trap 'exit 72' 1 2 15
if [ "$phase" != status ];then
    absent "$r/phases/$phase.sent" || exit 62
    for sent in "$r/phases"/*.sent;do
        [ -e "$sent" ] || continue
        # 恢复可在旧安装被终止且锁已释放后执行；不容许第二次安装。
        [ "$phase" = restore ] || regular "${sent%.sent}.exit" || exit 62
    done
    (set -C;printf sent > "$r/phases/$phase.sent") || exit 62
    recording=1
fi
if [ "$phase" = restore ];then sh "$r/restore.sh" restore;else sh "$r/install.sh" "$phase";fi
