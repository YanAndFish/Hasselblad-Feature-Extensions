#!/bin/sh
set -eu
. /tmp/hbl-x1d-rp/common.sh
stage=restore
[ "$#" = 0 ] || die 59
package_check
state_check
if [ -f "$s/restored" ]; then
    for role in victory-gui; do running "$role" "$(base_hash "$role")" || die 74; done
    owners || die 74
    printf '%s\n' replay-original-services-restored
    exit 0
fi
: > "$s/restore-started"
# 先证明所有将移除的 drop-in 属于本次，未知内容一个也不删。
for role in victory-gui; do
    path=$units/$role.service.d/$tag
    if [ -e "$path" ] || [ -L "$path" ]; then
        [ -f "$s/$role.touched" ] && regular "$path" || die 73
        if [ "$role" = victory-gui ]; then cmp -s "$path" "$s/gui.hold" || cmp -s "$path" "$s/gui.full" || die 73
        else cmp -s "$path" "$s/$role.drop" || die 73; fi
    fi
done
for role in victory-gui; do
    path=$units/$role.service.d/$tag
    if [ -f "$s/$role.touched" ] && [ -f "$path" ]; then rm "$path"; fi
done
systemctl daemon-reload
# 恢复仅重启本轮触及的服务；storage、FARM、无线及持久文件均不改。
for role in victory-gui; do
    if [ -f "$s/$role.touched" ]; then
        if [ "$role" = victory-gui ]; then : > "$s/release"; fi
        systemctl restart "$role" || die 74
        wait_running "$role" "$(base_hash "$role")" || die 74
    fi
done
: > "$s/release"
owners || die 74
"$d/replay-check" --active || die 74
: > "$s/restored"
printf '%s\n' replay-original-services-restored > "$s/restore.status"
cat "$s/restore.status"
