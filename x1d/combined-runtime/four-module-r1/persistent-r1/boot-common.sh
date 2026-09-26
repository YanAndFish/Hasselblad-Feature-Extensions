#!/bin/sh
# 固定独立包路径；根分区只读，启动副本与日志放入 RAM。
p=/opt/hbl-four-module-v1
d=/tmp/hbl-wireless-flash
u=/run/hbl-four-module
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
private() { [ -d "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
verify_package() {
    private "$p" && regular "$p/manifest.sha256" && regular "$p/installed.manifest.sha256" || return 1
    [ "$(sha256sum "$p/manifest.sha256" | cut -d' ' -f1)" = "$(cat "$p/installed.manifest.sha256")" ] || return 1
    (cd "$p" && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null) || return 1
    regular "$p/enabled" && [ "$(cat "$p/enabled")" = enabled-current-firmware ]
}
data_ready() {
    awk '$2=="/media/data" && $3=="ext4" {found=1} END {exit !found}' /proc/mounts
}
