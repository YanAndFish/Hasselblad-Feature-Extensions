"""只停用相机上的 af-only systemd 开机入口，保留安装目录和当前进程。"""
from pathlib import Path
import base64
import hashlib
import shlex
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
import session

REMOTE = "/tmp/hbl-disable-af-autoload"
SCRIPT = b"""#!/bin/sh
set -eu
g=/etc/systemd/system/victory-gui.service.d/92-hbl-af-only.conf
f=/etc/systemd/system/msg2dbus-farm.service.d/92-hbl-af-only.conf
p=/opt/hbl-af-only-v1
b=$p/.autoload-disabled
regular(){ test -f "$1" && test ! -L "$1"; }
absent(){ test ! -e "$1" && test ! -L "$1"; }
root_ro(){ awk '$2=="/"&&$3=="ext4"&&$4~/(^|,)ro(,|$)/{o=1}END{exit !o}' /proc/mounts; }
test "$(id -u)" = 0
test -d "$p" && test ! -L "$p" && root_ro
regular "$g" && regular "$f" && absent "$b"
systemctl is-active --quiet victory-gui msg2dbus-farm
mount -o remount,rw /
mkdir -m 700 "$b"
cp "$g" "$b/gui.conf"
cp "$f" "$b/farm.conf"
cmp -s "$g" "$b/gui.conf" && cmp -s "$f" "$b/farm.conf"
rm "$g" "$f"
sync
mount -o remount,ro /
root_ro && absent "$g" && absent "$f"
regular "$b/gui.conf" && regular "$b/farm.conf" && test -d "$p"
systemctl is-active --quiet victory-gui msg2dbus-farm
echo af-only-autoload-disabled-files-preserved
"""


def main():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError("workspace")
    s = session.Session("disable-af-autoload")
    digest = hashlib.sha256(SCRIPT).hexdigest()
    decoder = session.transport.DECODER
    s.command("fresh", f"test ! -e {REMOTE} && mkdir -m 700 {REMOTE}")
    for i, start in enumerate(range(0, len(decoder), 90)):
        op = ">" if i == 0 else ">>"
        s.command(f"decoder-{i}", f"printf %s {shlex.quote(decoder[start:start+90])} {op}{REMOTE}/d.awk")
    encoded = base64.b64encode(SCRIPT).decode("ascii")
    for i, start in enumerate(range(0, len(encoded), 170)):
        op = ">" if i == 0 else ">>"
        s.command(f"chunk-{i}", f"printf '%s\\n' {shlex.quote(encoded[start:start+170])} {op}{REMOTE}/p64")
    s.command("decode", f"r={REMOTE};printf '%b' \"$(awk -f \"$r/d.awk\" \"$r/p64\")\" >\"$r/run.sh\";sha256sum \"$r/run.sh\"")
    got = s.entries[-1]["output"].split()[0]
    if got != digest:
        raise RuntimeError("staged hash")
    s.command("dispatch", f"r={REMOTE};(sh \"$r/run.sh\">\"$r/out\" 2>&1;echo $? >\"$r/exit\") </dev/null >/dev/null 2>&1 &")
    result = "pending"
    for i in range(30):
        time.sleep(.5)
        result = s.command(f"poll-{i}", f"r={REMOTE};if test -f \"$r/exit\";then cat \"$r/exit\" \"$r/out\";else echo pending;fi")["output"]
        if result != "pending":
            break
    if result.splitlines() != ["0", "af-only-autoload-disabled-files-preserved"]:
        raise RuntimeError("camera transaction: " + result)
    print(result)


if __name__ == "__main__":
    main()
