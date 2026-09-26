"""原构建函数保持来源绑定，仅把新重定位输出放入 r3。"""
import inspect
from pathlib import Path
from runtime import AF, HERE
import build_candidate as original

source = inspect.getsource(original.build)
old = "out=HERE/'build'/f'{base:08x}'"
if source.count(old) != 1:
    raise ValueError('reviewed builder layout changed')
bindings = dict(original.__dict__, DELIVERY=HERE)
exec(compile(source.replace(old, "out=DELIVERY/'build'/f'{base:08x}'"), __file__, 'exec'), bindings)
build = bindings['build']
