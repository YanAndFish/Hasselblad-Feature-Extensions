#!/bin/sh
# 一次派发、一份退出记录；已派发未知结果禁止重跑任何依赖阶段。
. /tmp/hbl-x1d-combined/common.sh
phase=${1:-}
[ "$#" = 1 ] || exit 59
case "$phase" in preflight|ui|observer|provider|bridge|enable|release|replay-prepare|replay-config|replay-jpeg|replay-restore|worker-stop|restore-linux) ;; *) exit 59;; esac
verify_package || exit 60
j=$r/phases
private "$j" || exit 61
for sent in "$j"/*.sent; do
    [ -e "$sent" ] || continue
    regular "${sent%.sent}.exit" || exit 62
done
absent "$j/$phase.sent" || exit 62
(set -C;printf sent > "$j/$phase.sent") || exit 62
finish() { result=$?;trap - 0 1 2 15;printf '%s\n' "$result" > "$j/$phase.exit.next";mv "$j/$phase.exit.next" "$j/$phase.exit";exit "$result"; }
trap finish 0
trap 'exit 72' 1 2 15
case "$phase" in
replay-*) sh "$r/replay/backend.sh" "--${phase#replay-}";;
worker-stop|restore-linux) sh "$r/restore.sh" "$phase";;
*) sh "$r/install.sh" "$phase";;
esac
