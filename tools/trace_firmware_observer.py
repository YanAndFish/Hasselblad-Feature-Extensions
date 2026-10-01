"""公开范围调整：不提供厂商固件提取或内部实现分析器。"""
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hasselblad Feature Extensions contributors

def unavailable(*args, **kwargs):
    raise RuntimeError('This firmware analysis component is excluded from the public project. See docs/publication/PUBLIC_UPDATES.md.')


def __getattr__(name):
    raise RuntimeError('This firmware analysis component is excluded from the public project.')


if __name__ == '__main__':
    raise SystemExit('Unsupported: firmware analysis is excluded from this public project.')
