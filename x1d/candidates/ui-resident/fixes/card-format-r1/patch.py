"""固定 a8 SettingsGeneric 的 text2 角色修正；不改变格式化命令/警告/页面范围。"""
from pathlib import Path
import hashlib
FIX=Path(__file__).resolve().parent
CANDIDATE=FIX.parents[1]
FROZEN=CANDIDATE/'build/fixed/ui-resident-0456d37bc5ddbc57/overlay'
OLD_SETTINGS_SHA='fc6b8208c358dcdb685eda00d92d974e7219e801c4cac89c1ffb79be968f8955'
OLD='"text2": v.text2,'
NEW='"text2": (v.text2 === undefined || v.text2 === null) ? "" : v.text2,'
def apply(source):
    if hashlib.sha256(source.encode()).hexdigest()!=OLD_SETTINGS_SHA:raise ValueError('unexpected frozen SettingsGeneric')
    if source.count(OLD)!=1:raise ValueError('text2 append anchor')
    return source.replace(OLD,NEW,1)
def resources():
    data={'/'+p.relative_to(FROZEN).as_posix():p.read_text(encoding='utf-8') for p in FROZEN.rglob('*.qml')}
    data['/settings/SettingsGeneric.qml']=apply(data['/settings/SettingsGeneric.qml'])
    return data
