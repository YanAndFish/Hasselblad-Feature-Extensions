# X1D replay-next

仅面向第一代 X1D-50c 官方 1.25.0 的候选。目标保持为 JPEG 主图 8176×6128、文件内预览 1108×830/Q85，浏览读取预览、放大读取同一文件主图。已完成供其他会话执行的[临时装载包与操作说明](SESSION_LOAD_RUNBOOK.md)；本任务没有安装、相机访问或机内性能结论。

本目录接续固定的 `replay-v3`。v1/v2/v3 的源文件和组件产物均保留，逐项摘要复核见 [frozen-baseline-verification.json](artifacts/evidence/frozen-baseline-verification.json)。`x1d/wireless-flash` 不属于本候选范围。

主任务随后安排与引闪/AF及常驻 UI 的组合更新。新增[组合接口、正式固定模块包与部分失败恢复契约](JOINT_INTEGRATION.md)，已绑定 root 冻结的主资源和共同检查器；由 root 唯一协调资源、preload、共同窗口和本 boot 的基础链重建。原独立安装器不能直接用于已有引闪的环境，组合模块也不能自行独立装载。

## 本轮修改

- Full 像素配额使用非阻塞 `QSemaphore::tryAcquire(1)`。额度不足时交回原 provider，避免在串行图片工作线程等待旧工厂释放。原 provider 调用统一放在增强逻辑之外，增强分支的异常不会再触发第二次原 provider 调用。
- 已验证的预览使用两条共享 QImage 缓存，预算 8 MiB；两张当前尺寸图像占 7,357,120 字节。命中前仍重新检查 RAW 头身份、JPEG 前缀摘要和文件末尾。相同路径的新捕获不能复用旧像素。此预算只限制缓存保留的图像，不是整个 GUI/原回放/GPU 的内存上限。
- Adobe 显示转换采用 262,656 字节只读快速表。只有第三通道的整个区间都给出相同结果时才使用表值，否则执行原整数公式；输出与固定 v3 逐字节一致。
- 方位 2/3/4 直接交换像素；方位 5～8 对适合的尺寸使用原地分块排列，其他尺寸保留原位图循环。Full 转置 scratch 从 6,262,816 降至 547,729 字节，CPU 主像素仍为一张 200,410,112 字节缓冲。
- `QQuickTextureFactory::image()` 返回共享 QImage。像素和 Full 配额由最后一个图像引用释放；工厂可保留重建所需的 CPU 图像。完成记录的字段校验独立为 `recordValid`，文件路径、持久卷和实际文件读取逻辑保持原入口。

记录继续使用 `replay-v3` 格式与运行时路径 `/media/data/x1d-replay-v3`；本轮电脑上的构建和模拟不创建或访问该机内目录。未改变预览尺寸、Q85、主图压缩流、原厂颜色转换结果或无线闪光模块。

## 验证及边界

| 检查 | 证据及解释 |
|---|---|
| 宿主像素回归 | [pixels/validation.json](artifacts/pixels/validation.json)：所有 16,777,216 种 RGB 对照固定 v3；方位、边界及 Full 人工像素逐字节比较。性能数字只属于宿主 C 像素阶段。 |
| ARM 像素 | [arm-validation.json](artifacts/pixels/arm-validation.json)：56 个方位用例、6,260 组颜色及容量/边界检查；执行实际 ARM 指令，方位有 Pillow 独立对照。 |
| 预览缓存 | [checks/validation.json](artifacts/checks/validation.json)：共享生命周期、淘汰、预算及人工往返浏览。该宿主测试没有 JPEG/Qt/GPU。 |
| provider | [provider/validation.json](artifacts/provider/validation.json)：13 组检查、27 次原 provider 回退。实际候选 ARM、固定 Qt JSON/QImage 与原 TurboJPEG 解码；包括完整 8176×6128 JPEG（sRGB、方向 1）和最后引用归还额度。Storage、同步和窗口纹理创建使用显式替身。 |
| ICC 与失败边界 | [provider-edges/validation.json](artifacts/provider-edges/validation.json)：固定原厂 ICC 的预览/方向 6、未知 ICC、前缀及 Full 超时、codec 初始化与分配后解码错误。另观察原 codec 实际执行 NEON 指令。 |
| 写入准备 | [adapter-tests/validation.json](artifacts/adapter-tests/validation.json)：坏主图不提交、主解码分配失败不提交、可选预览失败仅提交一次原图、成功时只提交一次完整增强容器。实际写卡回执与记录发布不在本测试范围内。 |
| 接入与旧版保护 | [ABI 审计](artifacts/adapter/abi-audit.json)、[来源证据](artifacts/evidence/source-evidence.json)。静态审核与上述有界 ARM 执行分别记录。 |

ARM codec 用受控 `getenv` 选择原库的 NEON 路径；它是 CPU 指令模拟，不读取当前相机能力。完整 Qt 图片工作线程、取消/切图调度、DBus、记录原子写入、真实 GPU 及相机延迟仍未联调。

当前工厂仍调用固定 Qt 5.5.1 `createTextureFromImage`。源码确认其可能在超过 `GL_MAX_TEXTURE_SIZE` 时缩图；缺少支持的 BGRA 扩展时，通道转换可能使共享 QImage 分离并产生另一份 Full 像素。原厂使用专用纹理上传分支。因此，不能把“像素核心只用一张 Full 缓冲”写成整个实际上传路径只有一张，也不能宣称已有全分辨率 GPU 显示证据。

## 复现

已准备固定固件、Qt 5.5.1 公开源码与 Zig 0.13.0 后，在 `Hasselblad` 当前工作区使用现有 Python 运行：

```text
python -B x1d/candidates/replay-next/tools/generate_display_fast_tables.py
python -B x1d/candidates/replay-next/tools/build_replay_adapter.py
python -B x1d/candidates/replay-next/tools/audit_replay_adapter.py
python -B x1d/candidates/replay-next/tools/collect_evidence.py
python -B x1d/candidates/replay-next/CodeTests/run_pixels.py
python -B x1d/candidates/replay-next/CodeTests/run_arm_pixels.py
python -B x1d/candidates/replay-next/CodeTests/run_checks.py
python -B x1d/candidates/replay-next/CodeTests/run_provider.py
python -B x1d/candidates/replay-next/CodeTests/run_provider_edges.py
python -B x1d/candidates/replay-next/CodeTests/run_adapter.py
python -B x1d/candidates/replay-next/tools/verify_candidate.py
```

依赖使用项目已缓存的 Capstone/pyelftools/Unicorn 及 Python 的 Pillow。全部输入为固定官方包或人工图像，输出限于本候选 `artifacts/` 与生成的快速表。完整 Full ARM 模拟需要数分钟；模拟耗时不进入性能比较。

装载依赖、待验证项与设备协调顺序见 [REPLAY_NEXT_HANDOFF.md](../../research/REPLAY_NEXT_HANDOFF.md)。[会话装载包](artifacts/session-package/package.json)提供分阶段安装、受控服务重启和撤销脚本，由获授权的其他会话执行；不含设备发现、开启接口或刷写脚本。

当前源码、二进制与报告的一致性汇总见 [review-summary.json](artifacts/review-summary.json)。

用户要求暂不实机联调后的装载前准备见 [LOAD_PREPARATION.md](LOAD_PREPARATION.md)：配套补丁、每进程依赖/符号版本、服务装载与回退约束、GPU 条件及后续设备证据均已整理。离线检查结果见 [装载准备报告](artifacts/load-preparation/review.json)，该报告不表示已满足实机装载条件。

随后按用户“做到能直接装载的程度，装载由其他会话执行”增加独立会话守护库、QML 活动保持、实际渲染上下文 GPU 准入、检查器、传输和安装恢复脚本。完成通知的 Qt 返回地址现按 `QQuickImageBase::load + 0x1a8` 计算，支持库装载偏移；全部新 ELF 调整为 glibc 2.22 所需的连续 `.rel.dyn/.rel.plt`。生产模块重建后的核心 ARM 回归与 ABI 审计已通过。[会话操作说明](SESSION_LOAD_RUNBOOK.md)列出完整包、离线证据和真实装载验收边界。
