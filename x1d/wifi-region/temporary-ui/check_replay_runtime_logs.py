"""Read only aggregate UI errors; never print image URLs or photo identifiers."""
from pathlib import Path
import sys
P=Path(__file__).resolve().parent
sys.path[:0]=[str(P.parents[1]/'patch-distribution'),str(P.parents[1]/'tools')]
from usb_transport import Channel
c=Channel()
with c.session():
    print(c.command('systemctl is-active storage-daemon dbus;true'))
    for token in ['Invalid image provider','Failed to get image','Cannot open','ReferenceError','NativePhotoPlayback','PhotoPlaybackPage','hbljpeg']:
        command='p=$(cat /run/hbl-four-module/gui.pid);journalctl _PID=$p -n 1500 --no-pager -o cat | grep -c "'+token+'";true'
        print(token, c.command(command).strip())
    print(c.command('p=$(cat /run/hbl-four-module/gui.pid);journalctl _PID=$p -n 1500 --no-pager -o cat | sed -n "s/.*ReferenceError: /ReferenceError: /p" | sort -u | head -c 230;true'))
    print(c.command('p=$(cat /run/hbl-four-module/gui.pid);journalctl _PID=$p -n 1500 --no-pager -o cat | grep NativePhotoPlayback | tail -c 230;true'))
    print(c.command('p=$(cat /run/hbl-four-module/gui.pid);journalctl _PID=$p -n 1500 --no-pager -o cat | grep JpegRead | tail -c 230;true'))
    print(c.command('journalctl -u storage-daemon -n 300 --no-pager -o cat | grep -oE "Too big chunk|Too large file chunk requested|Error starting file transfer|Failed to start transfer|Not supported" | tail -c 230;true'))
