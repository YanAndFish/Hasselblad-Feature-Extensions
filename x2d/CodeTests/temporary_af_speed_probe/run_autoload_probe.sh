#!/system/bin/sh
# One dedicated diagnostic process. Never stop or restart the main GUI.
export XDG_RUNTIME_DIR=/tmp
export XDG_CACHE_HOME=/tmp/x2d-autoload-probe
export QT_QPA_FONTDIR=/system/lib64/qt/lib/fonts
timeout 10 env X2D_AUTOLOAD_PROBE=1 LD_PRELOAD=/system/lib64/libx2d_preview_probe.so \
  /system/bin/camera-test --version \
  > /tmp/x2d-autoload-probe/process.log 2>&1
result=$?
printf 'PROCESS_EXIT=%s\n' "$result" > /tmp/x2d-autoload-probe/exit-status
