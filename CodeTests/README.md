# Offline Verification Index

Recommended entry points and dependencies are in [BUILDABILITY.md](../docs/build/BUILDABILITY.md). They use synthetic inputs or software substitutes and do not connect to a camera.

| Area | Entry |
| --- | --- |
| Build failure contracts | `scripts/CodeTests/test_build_contract.py` |
| X1D core | `scripts/build_core.py`, with explicit compiler and output |
| Pixel algorithms | [X2D checks](../x2d/CodeTests/README.md) |
| X1D II detector | `scripts/build_x1dii_detector.py`, detector only |
| UI/text resources | Independent commands in the root build guide |

Earlier Node-client substitute tests and helper compilation were not repeated for device or firmware paths in this update. Success reports must describe the current execution; component success is not whole-camera or installer acceptance.

---

## 中文

推荐入口和依赖见 [BUILDABILITY.md](../docs/build/BUILDABILITY.md)。所有推荐测试使用自造输入或软件替身，不连接相机。

| 方向 | 入口 |
| --- | --- |
| 构建故障契约 | `scripts/CodeTests/test_build_contract.py` |
| X1D 核心 | `scripts/build_core.py`，显式提供编译器和输出目录 |
| 像素算法 | [X2D 测试](../x2d/CodeTests/README.md) |
| X1D II 检测库 | `scripts/build_x1dii_detector.py`，只测试开源库 |
| 界面与文本资源 | 根目录构建说明中的独立命令 |

Node 客户端先前有替身测试与辅助程序编译记录，本次未重新运行其设备或固件分析路径。成功报告须对应本次执行，组件通过不能证明整机或完整安装包。
