"""原构建函数保持来源绑定，仅把新重定位输出放入 r3。"""
import inspect
from pathlib import Path
from runtime import AF, HERE
import importlib.util
spec=importlib.util.spec_from_file_location('r6_native_builder',HERE/'native/build_candidate.py')
original=importlib.util.module_from_spec(spec)
# 原文件导入时的ROOT按本版路径修正；不执行其他构建。
code=(HERE/'native/build_candidate.py').read_text(encoding='utf-8').replace('ROOT=HERE.parents[2]','ROOT=HERE.parents[4]')
exec(compile(code,str(HERE/'native/build_candidate.py'),'exec'),original.__dict__)

source = code[code.index('def build('):code.index("\nif __name__==")]

old = "out=HERE/'build'/profile/f'{base:08x}'"
if source.count(old) != 1:
    raise ValueError('reviewed builder layout changed')
bindings = dict(original.__dict__, DELIVERY=HERE, HERE=HERE/'native')
exec(compile(source.replace(old, "out=DELIVERY/'build'/profile/f'{base:08x}'"), __file__, 'exec'), bindings)
build = bindings['build']
