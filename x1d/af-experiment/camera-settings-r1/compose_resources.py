"""纯资源组合：由主任务传入最终资源字典，本模块不注册 RCC、不写其他目录。"""
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
def compose(files):
    if '/af-settings/SettingsPage.qml' in files:raise ValueError('AF resources already composed')
    result=dict(files)
    result['/af-settings/SettingsPage.qml']=(HERE/'SettingsPage.qml').read_text(encoding='utf-8')
    return result
def component_checks():return ['qrc:/af-settings/SettingsPage.qml']
def sources():
    return {name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ('SettingsPage.qml','compose_resources.py')}
