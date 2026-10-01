# 构建输入与缺口

公开组件使用显式编译器、输入与输出；依赖保持原许可，厂商输入和资源不随本批提供。

| 入口 | 输入 | 当前输出／限制 |
| --- | --- | --- |
| `scripts/build_pixel_research.py` | Python、Zig、输出目录 | 自造输入的像素及组件测试 |
| `scripts/build_x1dii_detector.py` | Python、Zig、输出目录 | BSD 检测库的编译与空白图调用 |
| `scripts/build_core.py` | C++11 或 Zig，可选适配表 | 默认五个主机测试，额外适配需单独输入 |
| `x1d/offline-resources/CodeTests/test_resources.py` | Python 标准库 | 自造文本资源测试 |
| `x2d/flash-ui/CodeTests/smoke.py` | Python、PySide6、字体 | 离线界面与可选截图 |
| `x1d/tools/generate_display_tables.py` | 合法矩阵 RGB ICC 与输出文件 | 显示表；不附带 ICC 或生成表 |

X1D II 发布器缺少 `af_request.h`、`proxy_bridge.h`、`preview_resize.h` 和 `menu_control.h`；检测库可编译不表示这些依赖已解决。

旧目标构建仍有运行库、生成输入和组合适配缺口，未在本次重新闭环。不要把历史设备脚本当默认命令，缺文件时明确失败，不复用旧成功报告。

真实拍摄、显影、RAW、相册、HEIF 及安装包不在公开测试范围。见 [构建方法](BUILDABILITY.md)与[状态](PUBLICATION_STATUS.md)。
