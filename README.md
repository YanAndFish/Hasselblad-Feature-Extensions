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

## X2D highlights

### Pixel Overclock: approximately 400 MP

The six-frame research path reconstructs a **23326 × 17498** image: **408,158,348 pixels**, approximately **408 MP**. Six input frames describe the capture group, not a 600 MP output or a change to the sensor's physical pixel count. A four-frame reference path is also retained for algorithm comparisons.

The public source provides multi-frame synthesis, batched parallel reads, compute partitions, background writes, and plain-memory pipeline components. Synthetic-input comparisons verify algorithm consistency; they do not establish an equivalent gain in optical detail. Scene motion, lens resolution, sampling alignment and processing quality still affect the result. Actual camera capture, rendering, 3FR/HEIF saving and album integration are outside this public build. See [pixel research](x2d/CodeTests/pixel_shift_rgb/README.md).

### Autofocus optimization research

This work investigates controlled fast-sweep parameters, speed limits, transitions toward fine focus, and the associated mode/UI behavior. Historical candidates are not a universal autofocus upgrade: a speed-command multiplier does not imply the same improvement in total focus time, and lens compatibility, focus accuracy and on-camera stability require separate verification. This update supplies no firmware addresses, internal bindings or installation procedure. See the [AF research scope](x2d/CodeTests/temporary_af_speed_probe/README.md).

### Face and eye target behavior

The public eye-preference policy covers left/right choice, choosing the eye nearest a supplied position, delayed switching when an eye is lost, returning to a preferred eye after it reappears, and falling back to a valid face target. Missing eyes do not reuse stale coordinates or display a fabricated old eye box. This is target-selection logic, not a new face detector or an accepted camera AF controller. See [eye preference](x2d/CodeTests/face_edge_fix/README.md).

The separate [grayscale tracker](x2d/subject-tracking/README.md) retains a bounded target region and rejects stale observations; it does not claim neural face detection or identity recognition. X1D II's licensed detector is a separate module and does not establish X2D integration.

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

### X2D 主要研究内容

#### 像素超频：约四亿像素

六合一研究路径的目标图像为 **23326 × 17498**，共 **408,158,348 像素**，约 **4.08 亿像素**。六张指输入的拍摄组数，不是六亿像素输出，也不改变传感器的物理像素数量；源码还保留四帧参考路径供算法对照。

公开部分提供多帧合成、分批并行读取、计算分区、后台写入和通用内存流水线。自造输入对照证明算法结果一致，不等于光学细节也提高同样倍数；场景运动、镜头分辨力、采样对齐和处理质量仍会影响结果。实际相机拍摄、显影、3FR／HEIF 保存和相册接入不在公开构建范围，见[像素研究](x2d/CodeTests/pixel_shift_rgb/README.md)。

#### 对焦优化研究

研究受控快扫参数、速度限制、转入精扫的阶段衔接，以及相应的模式与界面行为。历史候选不能视为通用对焦升级：速度命令倍数不等于总对焦耗时提升倍数，镜头兼容性、合焦精度和机内稳定性仍需分别验证。本次不提供固件地址、内部绑定或安装流程，见[对焦研究范围](x2d/CodeTests/temporary_af_speed_probe/README.md)。

#### 人脸与人眼目标优化

公开的人眼偏好策略包括左右眼选择、按给定位置选择最近眼睛、丢失后的延迟切换、偏好眼重新出现后的恢复，以及回退到有效的人脸目标。眼睛丢失时不继续使用旧坐标，也不伪画上一帧眼框。这是目标选择逻辑，不是新增的人脸检测器或已验收的机内对焦控制器，见[人眼偏好](x2d/CodeTests/face_edge_fix/README.md)。

独立的[灰度模板跟踪](x2d/subject-tracking/README.md)用于有限时长的目标区域保持和过期观测拒绝，不宣称神经人脸检测或身份识别。X1D II 的开源检测库属于另一个模块，不能据此认定 X2D 已完成接入。

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
