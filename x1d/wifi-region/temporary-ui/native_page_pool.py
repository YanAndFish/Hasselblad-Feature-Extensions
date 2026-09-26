"""PagePool 的发行构建适配：固定旧基线，只输出薄 QML 和原生入口。

父任务负责将 NativePagePoolCore 安装为 _hblPagePoolCore，再把返回文本
写入原有 PagePool.qml 资源路径。此模块不修改输入、不连接设备。
"""
from pathlib import Path
import hashlib

BASELINE_SHA256 = "f492f585d872ba8130b68461c4ce36acd65d037590074b967e461cc36b58fd59"
MODULE = Path(__file__).resolve().parent


def apply_native_page_pool(source: str) -> str:
    """拒绝未知/已迁移源；允许 Python read_text 的 CRLF 标准化。"""
    baseline = (MODULE / "PagePool.qml").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA256:
        raise ValueError("Frozen PagePool.qml baseline changed")
    if source.replace("\r\n", "\n") != baseline.decode("utf-8").replace("\r\n", "\n"):
        raise ValueError("Unknown or already converted PagePool.qml")
    return (MODULE / "NativePagePool.qml").read_text(encoding="utf-8")
