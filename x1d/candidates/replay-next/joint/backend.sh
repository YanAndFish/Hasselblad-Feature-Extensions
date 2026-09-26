#!/bin/sh
# 组合协调器明确派发的回放后端阶段；不管理 GUI/FARM/worker/共同保持窗口。
set -eu
umask 077
r=/tmp/hbl-x1d-combined
d=$r/replay
s=$r/replay-state/backend
units=/run/systemd/system
tag=90-x1d-replay-joint.conf
phase=${1:-}
[ "$#" = 1 ] || exit 59
case "$phase" in --prepare|--config|--jpeg|--restore|--status) ;; *) exit 59;; esac
fail() { printf 'replay-backend-failed phase=%s code=%s\n' "$phase" "$1"; exit "$1"; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
value() { systemctl show -p "$2" "$1" | sed -n "s/^$2=//p"; }
pid() { p=$(value "$1" MainPID);case "$p" in ''|0|*[!0-9]*) return 1;; esac;printf '%s\n' "$p"; }
expected() { awk -v name="/usr/bin/$1" '$2==name {print $1}' "$d/baseline.sha256"; }
running() {
    role=$1;digest=$2
    [ "$(value "$role" LoadState)" = loaded ] && [ "$(value "$role" ActiveState)" = active ] && [ "$(value "$role" SubState)" = running ] || return 1
    p=$(pid "$role") && [ "$(sha256sum "/proc/$p/exe" | cut -d' ' -f1)" = "$digest" ] || return 1
    [ -r "/proc/$p/maps" ] && ! grep -q '(deleted)' "/proc/$p/maps"
}
clean() {
    [ "$(value "$1" FragmentPath)" = "/lib/systemd/system/$1.service" ] && [ -z "$(value "$1" DropInPaths)" ] || return 1
    ! value "$1" Environment | grep -Eq '(LD_PRELOAD|LD_LIBRARY_PATH)=' || return 1
    p=$(pid "$1") || return 1
    ! tr '\000' '\n' < "/proc/$p/environ" | grep -Eq '^(LD_PRELOAD|LD_LIBRARY_PATH)='
}
owners() { a=$(pid configstore) && b=$(pid jpeg-daemon) && c=$(pid storage-daemon) && "$d/replay-owners" --owners "$a" "$b" "$c" >/dev/null; }
protected() {
    for service in msg2dbus-farm storage-daemon; do
        p=$(pid "$service") || return 1
        [ "$(value "$service" ActiveState)" = active ] || return 1
        printf '%s %s ' "$service" "$p"
        # Linux comm 字段可能含空格，先移除最后的 ')' 之前内容；剩余第20项是 starttime。
        sed 's/.*) //' "/proc/$p/stat" | awk '{printf "%s ",$20}'
        sha256sum "/proc/$p/exe" | cut -d' ' -f1
    done
    # 正式 worker 位于 msg2dbus-farm 同一进程，没有独立 systemd worker 服务。
    # 这是构造/停止时的登记快照；当前 master/busy 的实时确认仍由协调器负责。
    farm_pid=$(pid msg2dbus-farm) || return 1
    worker=/tmp/hbl-wireless-flash/formal-worker.status
    private /tmp/hbl-wireless-flash && regular "$worker" && [ "$(stat -c '%u:%h' "$worker")" = 0:1 ] || return 1
    [ "$(stat -c '%s' "$worker")" -le 256 ] || return 1
    awk -v actual="$farm_pid" '
        NR==1 && $0!="formal-worker-ready-default-off" {bad=1}
        NR==2 && (NF!=5 || $1!="master=0" || $2!="radio-held=0" || $3!="radio-busy=0" || $4!="same-process=1" || $5!="pid="actual) {bad=1}
        END {exit bad || NR!=2}' "$worker" || return 1
    printf 'formal-worker same-process=1 pid=%s registered-default-off\n' "$farm_pid"
}
protected_match() { current=$(protected) && [ "$current" = "$(cat "$s/protected")" ]; }
held() { "$r/system-check" --require-held-min-ms 90000 >/dev/null; }
gpu() { p=$(pid victory-gui) && "$d/replay-joint-check" --gpu "$p" >/dev/null; }
wait_role() {
    for n in 1 2 3 4 5 6 7 8 9 10; do running "$1" "$2" && return 0;sleep 1;done
    return 1
}
[ "$(id -u)" = 0 ] && private "$r" && private "$d" && private "$r/replay-state" || fail 60
[ -z "${LD_PRELOAD:-}" ] && [ -z "${LD_LIBRARY_PATH:-}" ] || fail 60
cd "$d"
regular manifest.sha256 || fail 61
awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!~/^[A-Za-z0-9_.\/-]+$/ || $2~/^\// || $2~/(^|\/)\.\.(\/|$)/ || seen[$2]++ {bad=1} END {exit bad}' manifest.sha256 || fail 61
while read -r digest file; do regular "$file" || fail 61; done < manifest.sha256
sha256sum -c manifest.sha256 >/dev/null || fail 61
for file in backend.sh baseline.sha256 coordinator.sha256 replay-owners replay-joint-check libx1d-replay-joint.so libx1d-replay-provider.so libx1d-jpeg-adapter.so payload/configstore payload/jpeg-daemon; do
    awk -v wanted="$file" '$2==wanted {n++} END {exit n!=1}' manifest.sha256 || fail 61
done
awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || $2!="/tmp/hbl-x1d-combined/system-check" {bad=1} END {exit bad || NR!=1}' coordinator.sha256 || fail 61
sha256sum -c coordinator.sha256 >/dev/null || fail 61
[ ! -s /etc/ld.so.preload ] && [ -d "$units" ] && [ ! -L "$units" ] || fail 61
if [ "$phase" = --prepare ]; then
    [ ! -e "$s" ] && [ ! -L "$s" ] || fail 62
    held && gpu && owners || fail 63
    sha256sum -c baseline.sha256 >/dev/null || fail 63
    for role in configstore jpeg-daemon; do running "$role" "$(expected "$role")" && clean "$role" || fail 63;done
    snapshot=$(protected) || fail 63
    mkdir -m 700 "$s"
    printf '%s\n' replay-joint-backend-v1 > "$s/owner"
    sha256sum manifest.sha256 | cut -d' ' -f1 > "$s/package.sha256"
    printf '%s\n' "$snapshot" > "$s/protected"
    : > "$s/prepared"
    printf '%s\n' replay-backend-prepared
    exit 0
fi
private "$s" && regular "$s/owner" && [ "$(cat "$s/owner")" = replay-joint-backend-v1 ] || fail 62
[ "$(sha256sum manifest.sha256 | cut -d' ' -f1)" = "$(cat "$s/package.sha256")" ] && regular "$s/prepared" || fail 62
if [ "$phase" = --status ]; then
    state=prepared
    [ ! -f "$s/config.done" ] || state=config
    [ ! -f "$s/jpeg.done" ] || state=jpeg
    [ ! -f "$s/restore.done" ] || state=restored
    pstate=mismatch;protected_match && pstate=match
    live() {
        if running "$1" "$(expected "$1")";then printf original
        elif running "$1" "$(sha256sum "$d/payload/$1" | cut -d' ' -f1)";then printf candidate
        else printf unconfirmed;fi
    }
    phase_state() {
        if regular "$s/$1.exit";then head -c 3 "$s/$1.exit"
        elif [ -e "$s/$1.sent" ];then printf pending
        else printf none;fi
    }
    printf 'replay-backend recorded=%s config=%s jpeg=%s exits=%s,%s,%s protected-processes=%s\n' "$state" "$(live configstore)" "$(live jpeg-daemon)" "$(phase_state config)" "$(phase_state jpeg)" "$(phase_state restore)" "$pstate"
    exit 0
fi
# 每一阶段以 noclobber 登记；未知/部分失败不重发、不自动处理其他模块。
name=${phase#--}
[ ! -e "$s/restore.sent" ] || fail 64
for prior in config jpeg; do
    if [ -e "$s/$prior.sent" ] && ! regular "$s/$prior.exit"; then fail 64;fi
done
held && protected_match || fail 63
if [ "$phase" != --restore ]; then gpu && owners || fail 63;fi
case "$phase" in
    --config) [ ! -e "$s/config.sent" ] && [ ! -e "$s/jpeg.sent" ] || fail 64;role=configstore;;
    --jpeg) regular "$s/config.done" && [ ! -e "$s/jpeg.sent" ] || fail 64;role=jpeg-daemon;;
esac
(set -C; : > "$s/$name.sent") || fail 64
finish() { result=$?;trap - 0 1 2 15;printf '%s\n' "$result" > "$s/$name.exit.next";mv "$s/$name.exit.next" "$s/$name.exit";exit "$result"; }
trap finish 0
trap 'exit 72' 1 2 15
if [ "$phase" = --restore ]; then
    # 先验证全部自有 drop-in，未知内容保留；从不还原 GUI 或执行整包 restore。
    for role in configstore jpeg-daemon; do
        path=$units/$role.service.d/$tag
        [ ! -L "$units/$role.service.d" ] || fail 65
        if [ -e "$path" ] || [ -L "$path" ]; then regular "$path" && regular "$s/$role.touched" && cmp -s "$path" "$s/$role.drop" || fail 65;fi
    done
    for role in configstore jpeg-daemon; do
        if regular "$s/$role.touched"; then
            path=$units/$role.service.d/$tag
            if [ -f "$path" ]; then rm "$path";fi
            systemctl daemon-reload
            systemctl restart "$role" || fail 66
            wait_role "$role" "$(expected "$role")" || fail 66
            held && protected_match && owners || fail 67
            : > "$s/$role.restored"
        fi
    done
    : > "$s/restore.done"
    printf '%s\n' replay-backend-original-services-restored
else
    clean "$role" && running "$role" "$(expected "$role")" || fail 65
    directory=$units/$role.service.d;destination=$directory/$tag
    [ ! -L "$directory" ] && [ ! -e "$destination" ] && [ ! -L "$destination" ] || fail 65
    printf '%s\n' '[Service]' 'Restart=no' 'ExecStart=' "ExecStart=$d/payload/$role" > "$s/$role.drop"
    if [ "$role" = jpeg-daemon ]; then printf '%s\n' "Environment=LD_PRELOAD=$d/libx1d-jpeg-adapter.so" >> "$s/$role.drop";fi
    if [ ! -d "$directory" ]; then mkdir "$directory";: > "$s/$role.directory-created";fi
    : > "$s/$role.touched"
    (set -C;cat "$s/$role.drop" > "$destination") || fail 65
    systemctl daemon-reload
    systemctl restart "$role" || fail 66
    wait_role "$role" "$(sha256sum "$d/payload/$role" | cut -d' ' -f1)" || fail 66
    held && protected_match && owners || fail 67
    if [ "$role" = jpeg-daemon ]; then p=$(pid "$role");grep -Fq "$d/libx1d-jpeg-adapter.so" "/proc/$p/maps" || fail 67;fi
    : > "$s/$name.done"
    printf 'replay-backend-%s-ready\n' "$name"
fi
