# Hasselblad Feature Extensions

An independent, unofficial source repository for camera-feature research. It presents selected, sanitized original algorithms, UI components, and offline tests. Main development remains in a separate research project. This repository does not currently provide a complete installable camera update.

## Contents and status

| Area | Entry | Public scope |
| --- | --- | --- |
| X2D pixel synthesis | [Pixel research](x2d/CodeTests/pixel_shift_rgb/README.md) | Four/six-frame merging, batched parallel reads, background writes and a plain-memory pipeline; the six-frame target is approximately 400 MP |
| X2D target policies | [X2D index](x2d/README.md) | Eye preference, grayscale template tracking, previews and EXIF tools; no camera backend |
| X1D II face priority | [X1D II](X1D2/README.md) | Original excerpts and a BSD-licensed detector; the complete publisher still has missing dependencies |
| X1D components | [X1D](x1d/README.md) | Flash/settings policies, replay research, audio routing, animation and offline resource tools |
| X2D II | [X2D II](x2d2/README.md) | Topic index, without a completed on-camera adaptation |
| Offline UI | [Flash UI](x2d/flash-ui/README.md) | Original icons and QML pages, without a device backend |

X1D II and X2D II are different models. X1D II face-priority excerpts are in `X1D2/`; historical candidates do not establish current camera installation or acceptance.

## Offline verification

Use Python 3.11+ and, for these tested examples, Zig 0.13.0. Specify an output directory. These entry points do not connect to a camera.

```sh
python -B scripts/CodeTests/test_build_contract.py
python -B scripts/build_core.py --compiler zig --driver zig --build-dir ./outputs/core
python -B scripts/build_pixel_research.py --compiler zig --build-dir ./outputs/pixel-research
python -B scripts/build_x1dii_detector.py --compiler zig --build-dir ./outputs/x1dii-detector
```

The pixel entry checks plain-memory results against a fixed file algorithm, plus ten C component checks and eleven Python tests. The X1D II entry builds only the detector and checks a synthetic blank image; it does not build the incomplete publisher. See [build methods](BUILDABILITY.md) and [inputs](BUILD_INPUTS.md).

## Publication notes

- [Updates](PUBLIC_UPDATES.md) and [verification status](PUBLICATION_STATUS.md)
- [Scope](PUBLICATION_SCOPE.md), [source review](SOURCE_REVIEW.md), and [contributing](CONTRIBUTING.md)
- [Layout](DIRECTORY_LAYOUT.md) and [stage summary](STAGE_DELIVERY.md)

Current documents use concise topic summaries, without historical firmware addresses, device records or internal work logs. Git history has not been rewritten; documentation cleanup is not a comprehensive rights review of older source.

Original work uses [MIT](LICENSE). The detector in `X1D2/face-afs/vendor/libfacedetection/` retains its original BSD-3-Clause terms, notices and publicly released model parameters. Project licensing does not grant third-party rights. This project is not affiliated with or endorsed by the manufacturer.

---

## 中文

独立、非官方的相机功能研究源码仓库，展示经过筛选和脱敏的原创算法、界面组件及离线测试。主要开发在独立研究项目进行；本仓库目前没有完整可安装的相机更新包。

### 内容与状态

| 方向 | 阅读入口 | 公开内容 |
| --- | --- | --- |
| X2D 像素超频 | [像素合成](x2d/CodeTests/pixel_shift_rgb/README.md) | 四帧／六帧合成、分批并行读取、后台写入与普通内存流水线；六帧目标输出约四亿像素 |
| X2D 选择与跟踪 | [X2D 索引](x2d/README.md) | 左右眼选择、灰度模板跟踪、预览和 EXIF 工具；不含相机后端 |
| X1D II 人脸优先 | [X1D II](X1D2/README.md) | 自写候选片段及 BSD 开源检测库；完整发布器仍缺依赖 |
| X1D 通用组件 | [X1D](x1d/README.md) | 引闪与设置策略、回放研究、声音路由、动画和离线资源工具 |
| X2D II | [X2D II](x2d2/README.md) | 机型资料索引；不提供已完成的机内适配 |
| 离线界面 | [引闪界面](x2d/flash-ui/README.md) | 原创图标和 QML 页面，无设备后端 |

X1D II 与 X2D II 是不同机型；二代人脸优先源码位于 `X1D2/`。历史候选不代表当前公开源码已经完成相机安装或功能验收。

### 离线验证

需要 Python 3.11+；编译示例使用已验证的 Zig 0.13.0。输出由使用者显式指定，测试不连接相机。

```sh
python -B scripts/CodeTests/test_build_contract.py
python -B scripts/build_core.py --compiler zig --driver zig --build-dir ./outputs/core
python -B scripts/build_pixel_research.py --compiler zig --build-dir ./outputs/pixel-research
python -B scripts/build_x1dii_detector.py --compiler zig --build-dir ./outputs/x1dii-detector
```

像素入口验证普通内存与固定文件算法的一致性，另运行十个 C 组件检查和十一项 Python 测试。X1D II 入口只编译开源检测库并测试自造空白图，不编译缺少依赖的完整发布器。详细输入见 [构建方法](BUILDABILITY.md)和[依赖清单](BUILD_INPUTS.md)。

### 公开说明

- [本次更新](PUBLIC_UPDATES.md)与[当前验证状态](PUBLICATION_STATUS.md)
- [公开范围](PUBLICATION_SCOPE.md)、[来源审核](SOURCE_REVIEW.md)与[贡献说明](CONTRIBUTING.md)
- [目录索引](DIRECTORY_LAYOUT.md)与[阶段成果](STAGE_DELIVERY.md)

当前文档使用简短主题说明，移除了历史固件地址、设备记录与内部施工过程。Git 历史仍保留；既有旧源码的全面权利审核也未因此自动完成。

原创部分采用 [MIT](LICENSE)。`X1D2/face-afs/vendor/libfacedetection/` 按其原始 BSD-3-Clause 许可发布，保留上游声明及公开模型参数；项目许可不覆盖第三方权利。本项目不代表厂商或获得厂商认可。
