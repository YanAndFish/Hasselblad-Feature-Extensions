#!/bin/sh
. /tmp/hbl-ui-full-r2/common.sh
[ "$#" = 1 ] && [ "$1" = restore ] || exit 59
verify_package && owned || exit 60
# 即使别人随后增加另一份 drop-in，也拒绝代其停止 GUI 或删除其文件。
if [ -f "$s/gui.claimed" ];then
    regular "$gui" && cmp -s "$gui" "$s/gui.dropin" && only_owned_files || exit 66
    drops=$(value victory-gui DropInPaths)
    [ -z "$drops" ] || [ "$drops" = "$gui" ] || exit 66
    stop_gui || exit 67
    rm "$gui"
    mv "$s/gui.claimed" "$s/gui.restored"
    systemctl daemon-reload || exit 67
    systemctl start victory-gui || exit 67
fi
original_ready() { clean_service victory-gui && bus_unchanged && health; }
wait_ready original_ready || exit 68
: > "$s/restored.done"
printf '%s\n' ui-resident-original-restored
