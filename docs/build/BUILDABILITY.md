# 离线构建与验证

使用 Python 3.11+；C／C++ 示例使用已验证的 Zig 0.13.0。依赖自行准备，明确指定输出目录，以下入口不连接相机。从仓库根目录执行下列命令。

## 像素组件

```sh
python -B scripts/build_pixel_research.py --compiler zig --build-dir ./outputs/pixel-research
```

内存／固定算法对照、双路消费和跨批次检查，另有十个 C 组件与十一项 Python 检查。仅全部默认检查通过后标记成功；可选 LibRaw、TIFF 和大图工具不属于默认测试。

## X1D II 检测库

```sh
python -B scripts/build_x1dii_detector.py --compiler zig --build-dir ./outputs/x1dii-detector
```

编译已核对的开源库，对自造 160 × 120 空白 BGR 图执行检测。不编译缺头文件的发布器，不证明实际检测或对焦效果。

## X1D 核心与工具

```sh
python -B scripts/CodeTests/test_build_contract.py
python -B scripts/build_core.py --compiler zig --driver zig --build-dir ./outputs/core
python -B x1d/offline-resources/CodeTests/test_resources.py
```

默认五个核心主机测试，额外适配测试需明确输入。文本资源用自造数据；声音路由与抽象策略不证明扬声器或真实引闪。

## 界面

已验证环境为 Python 3.11 与 PySide6 6.4.1：

```sh
python -B x2d/flash-ui/CodeTests/smoke.py
```

使用 offscreen 和 software。可选 `--font` 读取已安装字体，`--screenshot` 写入指定位置。浏览器可打开 `x1d/shutter-effects/index.html`，不附音频。

其他旧脚本不是默认步骤。缺口见 [BUILD_INPUTS.md](BUILD_INPUTS.md)，不提供相机安装验收。
