P=344
START=52
BOOT='a1c0acd0-85e8-4580-aef1-096f1e9a0412'
ADDRESS=547928388480
LENGTH=1068
PRODUCT=548040249392
ORIGINAL='c8b5407c615b60c05078bc7ba9ada8cf53c905bac17faa59561f948feac0d430'
CANDIDATE='19ba28bc2896cb330b92eda6e7718e2ae7416c6144fd3782466dbece14ce45aa'
WINDOW=15
D='/tmp/afw-520c8cd9'
# Variables P, START, BOOT, ADDRESS, LENGTH, ORIGINAL, CANDIDATE, PRODUCT,
# WINDOW and D are substituted in a separate, host-validated fixed prefix.
backend_log() { printf '%s\n' "$*"; }
backend_same() {
    [ "$(cat /proc/sys/kernel/random/boot_id)" = "$BOOT" ] &&
    [ "$(awk '{print $22}' /proc/"$P"/stat)" = "$START" ]
}
memory_hash() {
    dd if=/proc/"$P"/mem bs=1 skip="$ADDRESS" count="$LENGTH" 2>/dev/null | sha256sum | awk '{print $1}'
}
backend_is_original() { [ "$(memory_hash)" = "$ORIGINAL" ]; }
backend_is_candidate() { [ "$(memory_hash)" = "$CANDIDATE" ]; }
backend_preflight() {
    backend_same &&
    grep -q ' /tmp tmpfs ' /proc/mounts &&
    [ "$(sha256sum "$D/original" | awk '{print $1}')" = "$ORIGINAL" ] &&
    [ "$(sha256sum "$D/candidate" | awk '{print $1}')" = "$CANDIDATE" ] &&
    [ "$(dd if=/proc/"$P"/mem bs=1 skip="$PRODUCT" count=4 2>/dev/null | od -An -tu4 | tr -d ' \n')" = 81470 ] &&
    awk '/TracerPid:/{n++;if($2!=0)bad++} END{exit(!n||bad)}' /proc/"$P"/task/*/status &&
    backend_is_original
}
backend_freeze() {
    backend_same || return 1
    kill -STOP "$P" || return 1
    n=0
    while [ "$n" -lt 20 ]; do
        if awk '/State:/{n++;if($2!="T")bad++} END{exit(!n||bad)}' /proc/"$P"/task/*/status; then return 0; fi
        n=$((n+1)); sleep 0.01
    done
    return 1
}
backend_pc_clear() {
    # There are no BL/BLR calls in either replaced instruction range. Check all
    # stopped PCs; refuse if a thread is within the enclosing function or if
    # the kernel refuses to disclose a PC. No speculative in-flight patching.
    awk -v low="$ADDRESS" -v high="$((ADDRESS+LENGTH))" '
      {n++; p=$NF; if(NF<3||p!~/^0x[0-9a-fA-F]+$/)bad++;
       v=p+0; if(v>=low&&v<high)bad++}
      END{exit(!n||bad)}' /proc/"$P"/task/*/syscall
}
backend_write_candidate() {
    backend_same && busybox dd if="$D/candidate" of=/proc/"$P"/mem bs=1 seek="$ADDRESS" count="$LENGTH" conv=notrunc 2>/dev/null
}
backend_write_original() {
    backend_same && busybox dd if="$D/original" of=/proc/"$P"/mem bs=1 seek="$ADDRESS" count="$LENGTH" conv=notrunc 2>/dev/null
}
backend_thaw() { backend_same && kill -CONT "$P"; }
backend_wait() { sleep "$WINDOW"; }
backend_retry_wait() { sleep 0.02; }

# Shared transaction state machine. Backend functions are supplied by a fixed
# generated device prefix or by the offline fault-injection harness.
tx_dirty=0
tx_paused=0
tx_finished=0
tx_restoring=0

tx_restore() {
    [ "$tx_dirty" = 1 ] || return 0
    tx_restoring=1
    backend_same || { backend_log IDENTITY_CHANGED_NO_WRITE; return 91; }
    tx_paused=1
    backend_freeze || { backend_log RESTORE_FREEZE_FAILED; return 92; }
    attempts=0
    while ! backend_pc_clear; do
        # Retry only before any restoration write, and only while the entire
        # candidate is still verified. Never resume partially written code.
        attempts=$((attempts+1))
        [ "$attempts" -lt 10 ] && backend_is_candidate || {
            backend_log RESTORE_PC_BUSY_PROCESS_PAUSED; return 95;
        }
        backend_thaw || return 94
        tx_paused=0
        backend_retry_wait
        tx_paused=1
        backend_freeze || return 92
    done
    # This transaction owns a possibly partial write. Always restore the exact
    # original function before resuming; do not merely reverse selected bytes.
    backend_write_original && backend_is_original || {
        backend_log RESTORE_FAILED_PROCESS_PAUSED_POWER_CYCLE_REQUIRED
        return 93
    }
    tx_dirty=0
    backend_thaw || { backend_log RESTORED_BUT_RESUME_FAILED; return 94; }
    tx_paused=0
    tx_finished=1
    backend_log RESTORED
}

tx_finish() {
    code=$?
    trap - EXIT HUP INT TERM
    if [ "$tx_dirty" = 1 ] && [ "$tx_restoring" = 0 ]; then
        tx_restore || code=99
    elif [ "$tx_paused" = 1 ] && [ "$tx_dirty" = 0 ]; then
        backend_thaw || code=98
    fi
    backend_log "EXIT:$code"
    exit "$code"
}

tx_run() {
    trap tx_finish EXIT
    trap 'exit 97' HUP INT TERM
    backend_preflight || return 10
    tx_paused=1
    backend_freeze || return 11
    backend_pc_clear || return 12
    backend_is_original || return 13
    tx_dirty=1
    backend_write_candidate || return 14
    backend_is_candidate || return 15
    backend_thaw || return 16
    tx_paused=0
    backend_log ACTIVE
    # Device-local deadline: USB disconnect does not cancel restoration.
    backend_wait || return 17
    tx_restore || return 18
}

# Explicitly requested RAM-only installation. Successful installation ends
# ownership of rollback-on-exit; the saved restore entry remains available.
tx_install_until_restart() {
    trap tx_finish EXIT
    trap 'exit 97' HUP INT TERM
    backend_preflight || return 10
    tx_paused=1
    backend_freeze || return 11
    backend_pc_clear || return 12
    backend_is_original || return 13
    tx_dirty=1
    backend_write_candidate || return 14
    backend_is_candidate || return 15
    backend_thaw || return 16
    tx_paused=0
    tx_dirty=0
    tx_finished=1
    backend_log ACTIVE_UNTIL_RESTART
}

echo $$ >"$D/owner" || exit 80
tx_install_until_restart
exit $?
