#!/system/bin/sh
# Inspect only the uniquely selected, short-lived diagnostic child.
for attempt in 1 2 3 4 5; do
    for process in $(pidof camera-gui); do
        args=$(tr '\000' ' ' < /proc/$process/cmdline 2>/dev/null)
        case "$args" in
            *file:/tmp/x2d-autoload-probe/probe.png*)
                printf 'ARGS=%s\n' "$args"
                cat /proc/$process/attr/current
                grep libx2d_preview_probe /proc/$process/maps
                tr '\000' '\n' < /proc/$process/environ | grep -E '^(LD_PRELOAD|X2D_AUTOLOAD_PROBE)='
                exit 0
                ;;
        esac
    done
    sleep 0.2
done
echo NO_DIAGNOSTIC_CHILD
