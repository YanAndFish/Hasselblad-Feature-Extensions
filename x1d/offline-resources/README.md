# Offline Text Resource Tools

`reader.py` and `writer.py` isolate original project text-resource read/write functions. They use the Python standard library, without device access, firmware paths, resource assets or installers.

They support the project's Qt RCC v1 text subset, not every Qt resource version. Four synthetic-text checks passed in `CodeTests/test_resources.py`. Callers must establish rights to their inputs; producing a file does not automatically grant redistribution rights. See [index](../../README.md).

---

## 中文

`reader.py` 从项目原有组合工具中提取单独的读取函数；`writer.py` 沿用项目自写的文本资源生成函数。两者只依赖 Python 标准库，无设备访问、固件路径、资源内容或安装入口。

支持本项目使用的 Qt RCC v1 文本子集，不承诺解析所有 Qt 资源版本。四项自造文本测试通过，见 `CodeTests/test_resources.py`。传入材料的权利由调用者自行确认；工具可生成文件不代表输出自动具有再分发许可。

当前组件与机型关系见 [公开索引](../../README.md)。
