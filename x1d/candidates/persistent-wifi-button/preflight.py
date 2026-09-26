"""本轮白名单只读前检；显式 --device 才访问相机。"""
from pathlib import Path
import hashlib, importlib.util, json, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TRANSPORT = ROOT / 'x1d/wireless-flash/research/mechanical_sync_session.py'
COMMANDS = [
    ('gui-identity', 'sha256sum /usr/bin/victory-gui'),
    ('mounts', "awk '$2==\"/\"||$2==\"/etc\"||$2==\"/media/data\" {print $2,$3,$4}' /proc/mounts"),
    ('services', 'systemctl is-active victory-gui msg2dbus-farm configstore jpeg-daemon storage-daemon'),
    ('gui-dropins', 'systemctl show victory-gui -p DropInPaths -p FragmentPath'),
    ('identity', 'id -u'),
    ('persistent-unit-directory', 'ls -ld /etc/systemd/system /media/data'),
]
def main():
    assert Path.cwd().resolve() == ROOT
    assert hashlib.sha256(TRANSPORT.read_bytes()).hexdigest() == '2ebbadf244613f64641266342679743b172899555ff6757f9cfded523433528a'
    assert all(0 < len(c.encode('ascii')) <= 231 for _, c in COMMANDS)
    if sys.argv[1:] != ['--device']:
        print(json.dumps({'offline':True,'commands':COMMANDS})); return
    out = HERE / 'build'; out.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location('persistent_button_transport', TRANSPORT)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    mod.HERE = HERE
    session = mod.Session('preflight.json')
    session.output = out / 'preflight.json'
    if session.output.exists(): raise RuntimeError('Preflight evidence already exists; do not overwrite')
    for name, cmd in COMMANDS:
        result = session.command(name, cmd, 15000)
        print(json.dumps(result), flush=True)
        if name == 'gui-identity' and result['output'].split()[0] != 'd29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b':
            raise RuntimeError('Current GUI does not match fixed X1D baseline')
if __name__ == '__main__': main()
