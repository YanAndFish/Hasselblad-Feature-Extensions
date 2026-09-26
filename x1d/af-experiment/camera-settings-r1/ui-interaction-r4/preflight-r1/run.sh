#!/bin/sh
. /tmp/hbl-af-ui-r4/preflight-r1/common.sh
fix=$d/preflight-r1
[ "$#" = 1 ] || exit 59
case "$1" in apply-preflight-r1) action=apply;; restore-preflight-r1) action=restore;; *) exit 59;; esac
phase=$1
delta_package && private "$fix" && private "$d/phases" || exit 60
(cd "$fix";sha256sum -c manifest.sha256 >/dev/null) || exit 60
for sent in "$d/phases"/*.sent;do [ -e "$sent" ] || continue;regular "${sent%.sent}.exit" || exit 61;done
regular "$d/phases/apply.sent" && regular "$d/phases/apply.exit" && regular "$d/phases/apply.log" || exit 61
(cd "$d/phases";sha256sum -c "$fix/prior.sha256" >/dev/null) || exit 61
if [ "$action" = apply ];then
    for item in touched applied failure-restored failure-restore-unknown restored bus.pid base-gui.dropin base-gui.sha256;do absent "$d/$item" || exit 61;done
    absent "$delta" || exit 61
else
    regular "$d/phases/apply-preflight-r1.sent" && regular "$d/phases/apply-preflight-r1.exit" || exit 61
fi
absent "$d/phases/$phase.sent" || exit 61
(set -C;printf sent > "$d/phases/$phase.sent") || exit 61
finish(){ result=$?;trap - 0 1 2 15;printf '%s\n' "$result" > "$d/phases/$phase.exit";exit "$result"; }
trap finish 0
trap 'exit 72' 1 2 15
sh "$fix/$action.sh"
