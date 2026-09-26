#!/bin/sh
. /tmp/hbl-af-bus-r4/common.sh
[ "$#" = 1 ] || exit 59
case "$1" in apply|restore) action=$1;; *) exit 59;; esac
delta_package && private "$d/phases" || exit 60
for sent in "$d/phases"/*.sent;do [ -e "$sent" ] || continue;regular "${sent%.sent}.exit" || exit 61;done
absent "$d/phases/$action.sent" || exit 61
(set -C;printf sent > "$d/phases/$action.sent") || exit 61
finish(){ result=$?;trap - 0 1 2 15;printf '%s\n' "$result" > "$d/phases/$action.exit";exit "$result"; }
trap finish 0
trap 'exit 72' 1 2 15
sh "$d/$action.sh"
