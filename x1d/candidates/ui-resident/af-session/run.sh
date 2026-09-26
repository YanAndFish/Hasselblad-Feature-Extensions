#!/bin/sh
. /tmp/hbl-ui-af/common.sh
[ "$#" = 1 ] || exit 59
phase=$1
case "$phase" in preflight|ui|status|restore) ;; *) exit 59;;esac
verify_package && private "$r/phases" || exit 60
mkdir -m 700 "$r/phase.lock" || exit 62
finish() {
    code=$?;trap - 0 1 2 15
    if [ "${recording:-0}" = 1 ];then
        printf '%s\n' "$code" > "$r/phases/$phase.exit.next"
        mv "$r/phases/$phase.exit.next" "$r/phases/$phase.exit"
    fi
    rmdir "$r/phase.lock"
    exit "$code"
}
trap finish 0
trap 'exit 72' 1 2 15
if [ "$phase" != status ];then
    absent "$r/phases/$phase.sent" || exit 62
    for sent in "$r/phases"/*.sent;do
        [ -e "$sent" ] || continue
        [ "$phase" = restore ] || regular "${sent%.sent}.exit" || exit 62
    done
    (set -C;printf sent > "$r/phases/$phase.sent") || exit 62
    recording=1
fi
if [ "$phase" = restore ];then sh "$r/restore.sh" restore;else sh "$r/install.sh" "$phase";fi
