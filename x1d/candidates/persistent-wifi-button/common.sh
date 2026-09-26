#!/bin/sh
set -eu
umask 077
r=/run/hbl-wifi-probe
proc=/proc
required_uid=0
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%h' "$1")" = "$required_uid:1" ]; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = "$required_uid:700" ]; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pid() { p=$(value "$1" MainPID);case "$p" in ''|0|*[!0-9]*) return 1;;esac;printf '%s\n' "$p"; }
verify() {
    directory=$1
    [ "$(id -u)" = "$required_uid" ] && private "$directory" && regular "$directory/manifest.sha256" || return 1
    (cd "$directory"
    awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.-]+$/ || seen[$2]++ {bad=1} END {exit bad || NR!=9}' manifest.sha256 || exit 1
    while read -r digest file;do regular "$file" || exit 1;done < manifest.sha256
    sha256sum -c manifest.sha256 >/dev/null) || return 1
    sha256sum -c "$directory/baseline.sha256" >/dev/null
}
clean() {
    role=$1
    [ "$(value "$role" FragmentPath)" = "/lib/systemd/system/$role.service" ] && [ -z "$(value "$role" DropInPaths)" ] || return 1
    for base in /etc/systemd/system /run/systemd/system /lib/systemd/system;do
        directory=$base/$role.service.d
        [ ! -L "$directory" ] || return 1
        for f in "$directory"/*.conf;do absent "$f" || return 1;done
    done
    systemctl is-active --quiet "$role" || return 1
    ! value "$role" Environment | grep -Eq '(LD_PRELOAD|LD_LIBRARY_PATH)=' || return 1
    p=$(pid "$role") || return 1
    ! tr '\000' '\n' < "$proc/$p/environ" | grep -Eq '^(LD_PRELOAD|LD_LIBRARY_PATH)='
}
ready() {
    p=$(pid victory-gui) || return 1
    regular "$r/verified" && [ "$(cat "$r/verified")" = "probe-verified pid=$p" ] || return 1
    regular "$r/ui.status" && [ "$(cat "$r/ui.status")" = "probe-ready pid=$p" ] || return 1
    grep -Fq "$r/libhbl-wifi-probe.so" "$proc/$p/maps" || return 1
    result=$("$r/health" --require-ready) || return 1
    case "$result" in "ui-health-ready pid=$p system=2 power=0"|"ui-health-ready pid=$p system=4 power=1") return 0;;*) return 1;;esac
}
