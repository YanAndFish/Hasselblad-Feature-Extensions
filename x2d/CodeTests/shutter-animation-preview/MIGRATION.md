# Ciallo 本地迁移与版本边界

日期：2026-09-25。目标为本项目现有 `x2d/CodeTests/shutter-animation-preview/`，不新建平行功能模块。

## 来源与保留方式

来源是共享项目的本地备份分支 `codex/backup-before-own-reverts-91b48ce`，精确提交见 `baseline-400ms.sources.json`。读取 Git 对象，未从已回退的共享工作树复制源码，未改源项目或其分支。

备份共 18 个文件，目标原已有全部对应文件。12 个字节一致，5 个存在本地候选改动，README 仅换行不同。基线清单复用 12 个共用文件，仅内嵌这 5 个旧版本及历史 README 的原始 UTF-8 文本；逐文件保存原始大小和 SHA-256。无须保留第二套源码目录或依赖源仓库继续存在。

当前源码中的 800 ms 动画、三状态设置、设置服务和启动器候选全部保留。基线中的 400 ms 动画、原厂音频服务接口、预载、持久化与恢复生成器、素材转换和计时探针也可完整还原。

`verify_migration.py --materialize` 会在被忽略的 `outputs/baseline-400ms-review/` 中重建原始 18 文件，已有不同内容时停止覆盖。此目录仅供审阅：历史脚本的相对路径依赖原模块布局，不能直接从审阅目录执行设备暂存或安装。该命令不生成可安装发布包，不调用原脚本。

## 验证层级

| 版本/材料 | 已建立的事实 | 未建立的事实 |
| --- | --- | --- |
| X2D 4.2.0 / 400 ms / 原厂音频服务 / 旧约半秒素材 | 备份源文件可按哈希复原；来源任务转述用户已确认重启后自定义声音与原厂提示音共存 | 本轮未读相机，未重复实机验收；不据此证明所有固件兼容 |
| X2D 800 ms 与三状态候选 | 本轮 Qt 6.4.1 离线预热、状态切换、实例复用、看门狗、设置挂接检查通过 | 不是 400 ms 实机验收版本；设置服务与启动器的完整实机部署未验证 |
| 完整 Ciallo 原声 | SHA-256 与用户确认版本一致；59392 帧、48000 Hz、PCM16 双声道，约 1.237 秒 | 未在 X2D 安装验证；未确认再分发许可 |

历史 README 中的“尚待冷启动验收”是当时记录；后续用户关于旧短素材版共存的反馈在上表补充，不覆盖或伪造历史日志。旧直接占用 PCM 的实现不能作为恢复目标。

## 本轮实际检查与修正

- 18 个基线文件大小和 SHA-256 全部通过；当前与历史时长分别为 800 ms 和 400 ms。
- 7 项计时分析测试通过；这仍是软件事件间隔，不是光学黑屏测量。
- 所有模块 Python 文件通过语法解析；PowerShell 脚本通过语法解析。
- 现有动画测试的 Component 后多余分号、设置测试跨两层对象的无效 alias 已修正；只改测试夹具，没有更改运行 QML。
- 800 ms 动画与三状态设置两项 Qt 6.4.1 离线检查通过，测试显式关闭网络请求。
- 400 ms 基线和 800 ms 候选的音频 C 源码分别编译为 AArch64 ELF，通过符号依赖和段权限检查。使用已有 X2D 4.2.0 的 libc/libaudioclient；未使用 X1D 固件库。通用 Zig 编译器只作离线工具。
- 编译输出与依赖哈希在 `outputs/migration-validation/audio-build-verification.json`，不覆盖既有设备包。
- 原声按原字节复制到 `outputs/ciallo-callio.wav`。不截断、不伸缩、不重采样，也未替换历史 `ciallo-48k-full.wav` 安装输入。

## 依赖与复现入口

从本项目根目录运行以下离线检查：

```powershell
py -3.11 -B x2d/CodeTests/shutter-animation-preview/verify_migration.py
py -3.11 -B -m unittest discover -s x2d/CodeTests/shutter-animation-preview -p test_analyze_blackout.py
$env:PYTHONPATH = Join-Path (Get-Location) 'x2d/outputs/4.2.0/temporary-wifi-button/qt-runtime'
py -3.11 -B x2d/CodeTests/shutter-animation-preview/check_device_animation.py
py -3.11 -B x2d/CodeTests/shutter-animation-preview/check_effect_settings.py
```

这里的 Qt 路径是当前项目已有的本地依赖，不是可分发软件包。换电脑须自行准备 PySide6 / Qt 6.4.1。

| 依赖 | 用途及本轮检查 |
| --- | --- |
| `x2d/tools/firmware_image.py` | 已存在；离线读取 X2D 固件，不导入相机客户端 |
| 同级 `temporary_af_speed_probe/original-menu-candidate/Bootstrap.qml` 与 `menu-candidate/flash-ui/` | 已存在；原厂菜单挂接生成器的固定源基线，变化时须重新审查 |
| 同级 `temporary_af_speed_probe/Usb.ps1`、`AdbUsbCheck.cs` | 已存在；本轮未执行或连接设备 |
| Zig、pyelftools、capstone、dissect.extfs、官方 4.2.0 镜像或提取库 | 本地离线构建依赖，不随本次源码迁移发布固件或编译器 |
| numpy、soundfile | 素材转换的可选依赖；本轮复制已确认 WAV，无须再次转换 |

## 缺项与安装边界

没有缺失的备份源文件或已引用的本地项目依赖。旧半秒素材、旧构建产物和原始设备日志未迁入；当前素材转换与安装生成器仍使用历史文件名，缺少该输入时应停止，而非隐式替换为长素材。若要复现旧二进制包，仍需原始素材及对应工具版本；本轮未宣称二进制逐字节复现。

800 ms 设置候选的 `prepare_local_candidate.py` 明确输出 `installable=false`。既有安装/恢复生成器是按旧设备哈希编写的历史工具，不能因迁移完成就直接用于当前相机。后续安装必须单独核对当前设备版本、源包与恢复链。

本轮无设备操作、Git 初始化、提交、推送或发布；不修改 X1D 实现。未带入设备标识、原始敏感日志或其他无关研究。
