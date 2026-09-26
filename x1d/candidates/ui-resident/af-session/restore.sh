#!/bin/sh
. /tmp/hbl-ui-af/common.sh
[ "$#" = 1 ] && [ "$1" = restore ] || exit 59
verify_package && owned && protected_unchanged || exit 60
if [ -f "$s/gui.claimed" ];then
    regular "$gui" && cmp -s "$gui" "$s/gui.dropin" && only_dropins victory-gui integrated || exit 66
    drops=$(value victory-gui DropInPaths)
    [ "$drops" = "$afgui $fixgui" ] || [ "$drops" = "$afgui $fixgui $gui" ] || exit 66
    stop_gui || exit 67
    rm "$gui"
    mv "$s/gui.claimed" "$s/gui.restored"
    systemctl daemon-reload || exit 67
    systemctl start victory-gui || exit 67
fi
wait_ready r4_ready || exit 68
: > "$s/restored.done"
printf '%s\n' ui-af-r4-restored
