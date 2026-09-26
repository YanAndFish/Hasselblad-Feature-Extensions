# 第一代 X1D 本地增强候选

**公开候选说明：下文保留原开发版本的研究状态，不代表本独立目录已经完成构建或安装验收。原厂输入、素材、工具链及部分待审生成资源未随本目录提供。当前可复现范围见 [构建核对](../BUILDABILITY.md)。**

X1D 的「Ciallo」快门动画与声音见 [shutter-effects](shutter-effects/README.md)。旧版已有安装和启动回读；新版换用用户确认的 1.237 秒完整原声，并修正扬声器路由，拍摄声音仍待实机验收。下文其他模块状态不因这项安装而改变。

范围固定为 X1D-50c 官方 1.25.0。新拍 JPEG 使用 Full 8176×6128 取代 Quarter；同一文件内嵌 1108×830（约 920K 像素）、Q85 预览，浏览取预览，放大取主图。当前是可审查的本地组件候选，尚未运行原相机服务联调或安装。

当前回放优化和新验证从 [replay-next](candidates/replay-next/README.md) 进入；[候选版本登记](research/CANDIDATE_VERSIONS.md)区分固定 v1/v2/v3 与 next。[装载条件及设备协调](research/REPLAY_NEXT_HANDOFF.md)明确列出本轮尚未验证的 GPU、DBus 和机内时序。下列早期核心材料仍保留各自原始版本范围。

| 成果 | 状态与证据 |
|---|---|
| 编码错误传播 | 实际 ARM 补丁及 24 个离线场景，见 [JPEG_FAILURE_PATCH.md](research/JPEG_FAILURE_PATCH.md) |
| X1D Full 配置 | 仅 Wedge 分支修改，5 个测试方法、24 个场景，见 [FULL_JPEG_CONFIG_PATCH.md](research/FULL_JPEG_CONFIG_PATCH.md) |
| 920K 分段预览、颜色和方向 | C/ARM 核心验证通过，详见 [PREVIEW_920K.md](research/PREVIEW_920K.md) |
| 写完发布与统一回放 | 两份原生适配 `.so` 已编译并通过静态 ABI 审计；Qt/DBus/FARM/GPU 联调尚未完成 |
| 安装、官方更新与恢复 | 尚不能承诺，见 [INSTALLATION_FEASIBILITY.md](research/INSTALLATION_FEASIBILITY.md) |

代码位于 `native/`，历史构建脚本位于 `tools/`，验证代码位于 `CodeTests/`，证据位于 `research/validation/`。原开发环境使用固定官方包及公开依赖；该环境的研究缓存不包含在本独立目录中。下述早期测试使用内存人工生成图像。

回放颜色表由 `tools/generate_display_tables.py --icc <输入ICC> --output <本地构建目录>/display_tables.h` 生成。输入须由使用者自行合法准备，并与待显示图像的 RGB 色彩空间一致；工具仅接受 RGB/XYZ 矩阵 ICC v2/v4、三个一致的单值 gamma `curv`，明确拒绝 LUT、参数曲线和其他未验证配置。输出保留 `display_pixels.c` 使用的三个表名，但生成表不随源码分发。离线输入测试为 `CodeTests/test_display_table_inputs.py --output-dir <已存在的私有目录>`，只使用自造 ICC。

已有环境下，先运行 `tools/build_jpeg_container.py` 和 `tools/build_replay_adapter.py`，再运行相应 `CodeTests/jpeg_container/test_*.py` 及 `tools/audit_replay_adapter.py`。首次取得公开工具链与 Qt 头文件分别使用 `prepare_native_toolchain.py`、`prepare_qt_headers.py`；这些是本地构建步骤，不是安装相机的命令。原两份 ARM 补丁由 `patch_jpeg_failure.py`、`patch_full_jpeg.py` 生成，其测试保持独立。

第一代 X1D-50c 官方 1.25.0 的 [replay-next 会话包](candidates/replay-next/SESSION_LOAD_RUNBOOK.md)已提供临时装载、受控服务重启和撤销脚本，由其他获授权会话执行；实际装载和失败恢复尚未实机验证。本目录没有可刷 CIM，不要把用户态会话包当作固件更新。
