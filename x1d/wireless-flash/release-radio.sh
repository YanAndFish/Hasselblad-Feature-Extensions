#!/bin/sh
# 仅释放本模块临时固件的准备状态；不触发发射。
marker=$(/usr/bin/wl phyreg 0 b 2>/dev/null || true)
if [ "$marker" = 0x584e ]; then
    /usr/bin/wl phyreg 27 b >/dev/null 2>&1 || true
fi
exit 0
