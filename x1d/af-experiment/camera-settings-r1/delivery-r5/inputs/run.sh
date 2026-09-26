#!/bin/sh
. /tmp/hbl-x1d-combined/common.sh
phase=${1:-}
[ "$#" = 1 ] || exit 59
case "$phase" in preflight|ui|bus|release|restore-linux) ;; *) exit 59;; esac
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
if [ "$phase" = restore-linux ];then sh "$r/restore.sh" "$phase";else sh "$r/install.sh" "$phase";fi
