# X1D 普通菜单与全部行常驻：离线内存评估

评估对象：X1D 1.25.0 固定原厂 GUI，SHA-256 `d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`。这是独立评估，不是新的装载策略或装机验收。此次设备请求为 0，冻结 a8、格式化修复包和其他任务模块均未修改。

在 Windows 64 位 Qt 5.15.2 宿主上，**全部 23 个普通页及全部功能行保留，相比 a8 增加约 16.60 MiB 私有提交内存**；5 轮配对差分为 16.14–16.71 MiB。工作集差分中位数 15.79 MiB。它证明该宿主夹具的增量数量级，不是相机 RAM 实测值或目标机上限。

若现在需要一个规划数字，可暂为普通菜单全行方案预留 **40 MiB 额外空间**，这是将本次约 16–17 MiB 宿主增量留出约两倍余量后向上取整的工程预算选择；不是统计置信区间，也不保证目标机足够。特殊工具、GPU、原生服务、拍摄与回放峰值仍须另计。

## 实测结果

每个策略启动 5 个独立进程；每个稳态点等待 400 ms 后，取间隔 100 ms 的 5 次采样中位数。表中再汇总跨进程中位数及最小–最大值。单位均为 MiB（2^20 字节）。所有测量结束时均关闭或隐藏页面，保留策略规定的对象。

| 策略 | 私有提交：中位数（范围） | 工作集中位数 | QObject 数 | 功能行 / 标题 / 菜单入口实例 |
|---|---:|---:|---:|---:|
| 原厂按需，遍历后关闭 | 45.78（45.74–46.08） | 61.33 | 15 | 0 / 0 / 0 |
| a8 两个通用实例，遍历后关闭 | 45.72（45.61–45.92） | 61.34 | 203 | 0 / 4 / 0 |
| 3 菜单＋23 普通页，默认虚拟化 | 60.47（60.30–60.81） | 75.41 | 5022 | 88 / 20 / 18 |
| 3 菜单＋23 普通页，全部行保留 | 62.32（61.86–62.38） | 77.06 | 5405 | 99 / 27 / 26 |

全页面但默认虚拟化，相比 a8 的私有提交增量中位数为 14.80 MiB。默认 ListView 只创建 88/99 功能行、20/27 标题、18/26 入口，因此“页面常驻”并不等于“全部行已就绪”。全行夹具仅在评估副本设置 `cacheBuffer=100000`，最终核对 99 个行 Loader 全部 Ready。它没有被写入生产 QML。

原厂/a8 的绝对内存接近，不能解释为 a8 无成本：a8 冷态已构造通用实例，原厂遍历后的分配器和编译缓存也会保留；微小差异小于跨进程波动。原厂最终 15 个 QObject；a8 为 203 个，功能行模型已清空但观察到 4 个分组标题残留。

## 范围和方法

- 使用真实原厂 QML、完整 Wedge 设置数组和原 `validCheck`/`enableCond` 筛选，提取并保留 267 个原始 PNG/SVG 资产（共 1,094,540 字节）。QtGraphicalEffects 使用真实模块；运行后端为软件、offscreen，不代表目标机 OpenGL/EGL 分配。
- 宿主通过 PyQt5 执行；所有 Hasselblad 原生 import 均已移除，原生代理完全为内存替身。QML 中的字体请求仍是原厂名称，但提取包不含目标字体，宿主可能回退字体。未复制完整 MainScreen/相机进程，仅使用其真实菜单 Loader 与 Connections 片段。
- 23 个普通设置页由三个菜单创建；30 个声明入口中去掉 4 个 demo 后为 26 个入口，包含 3 个特殊工具入口。普通页 126 条非 demo 记录中，99 条是功能行，27 条是分组标题；标题不是 ListModel 功能记录。
- 使用较宽能力夹具：手动模式、镜头能力开启、镜头版本占位值、隐藏 demo、显示 secret 项，使 99 个潜在功能行都进入模型。它不是实机当前能力快照，实际可见行可能更少；按钮存在不表示操作获准或执行。
- 原厂/a8 执行同一 23 页打开、关闭序列；全页面策略直接 populate 各独立页，然后隐藏，未经过原厂全部导航回调。没有构建一个可安装的多页路由或测导航加速。
- privateCommit 为 Windows `PrivateUsage`，workingSet 为 `WorkingSetSize`，不是 Linux RSS 的同义指标。QObject/视觉子树遍历在最后一次内存采样之后，减少 Python 包装对象污染采样；引擎、JS、缓存与替身仍在进程内存中。
- 所有 20 轮警告 0、模拟操作按钮调用 0。主脚本和汇总脚本检查危险弹窗与特殊组件实例，除 objectName 外还检查 QML 元对象类名；未执行格式化或其他工具动作。

## 预建副作用与未覆盖部分

真实 `SettingsGeneric.qml` 滑块的 `onValueChanged: proxy[name] = value` 在初始化时触发两次模拟属性写入：`crop_mode_opacity`、`BACKLIGHT_brightness` 各一次，四种策略均如此。此处是替身里的属性赋值，不能据此断言相机硬件值实际改变；但正式预建不能直接照搬本夹具，必须处理初始化回写、属性刷新、能力变化及隐藏时活动。

原厂/a8 的 About 导航调用模拟设备信息读取。直接预建策略未触发它们（记录为 0），因此还需要保留用户实际进入 About 时的正常刷新语义。

本报告未实例化白平衡工具 `GreyBalanceTool.qml`、日期时间 `DateTime.qml`、水平仪 `SpiritLevelView.qml`，也未打开格式化/确认弹窗及下拉选择弹层。白平衡工具 `Component.onCompleted` 会设置图片筛选并可能切换目录；水平仪完成构造会调用 `setSpiritLevel()`；日期页会创建自己的日期时间模型。它们不能按一个 Generic 页平均值直接补算。未含回放页、照片/JPEG 缓存、AF 模块、传感器/服务缓存或整机峰值。

因此已经完成的是 **全部普通菜单和潜在行的离线差分评估**，并非“整个 GUI 所有页面全部常驻”的精确总预算；特殊页内存、目标 Qt 5.5/32 位 ARM、GPU、原生服务增量和长期稳定性仍未测量。64 位指针减半不能直接推导 32 位总内存减半，也不能给该差分一个可信的目标机上下界。

## 与已有相机快照的关系

只读复核既有 [内存快照](../../build/session/sessions/memory-snapshot-20260912T205420595640Z/observation.json)：Linux MemTotal 511,832 KiB（499.84 MiB），MemAvailable 242,808 KiB（237.12 MiB），MemFree 181,420 KiB（177.17 MiB），GUI RSS 59,364 KiB（57.97 MiB），Swap 为 0。这是此前 a8 状态的一次历史快照，不是本轮新读取，不代表当前状态或总物理 RAM。

该快照显示当时存在百 MiB 级可用空间，但其中不能全部分配给 UI。不能把 57.97 MiB GUI RSS 乘页面数量，也不能把 Windows 的约 16 MiB 差分直接加到 Linux RSS 后宣称装机安全。40 MiB 规划预算约为该次 MemAvailable 的 17%，仍需要拍摄、回放、AF 并行峰值下的目标验证。当前没有据此追加装载或设备访问。

## 各普通页的对象核对

| 设置数组 | 潜在功能行 | 默认虚拟化实例 | 全行实例 | 全行标题实例 |
|---|---:|---:|---:|---:|
| cameraSettingsExposure | 9 | 5 | 9 | 5 |
| cameraSettingsImage | 3 | 3 | 3 | 2 |
| cameraSettingsQuality | 3 | 3 | 3 | 0 |
| cameraSettingsAutofocus | 4 | 4 | 4 | 0 |
| cameraSettingsManualFocus | 2 | 2 | 2 | 0 |
| cameraSettingsSelfTimer | 4 | 4 | 4 | 0 |
| cameraSettingsInterval | 5 | 5 | 5 | 0 |
| cameraSettingsBracketing | 7 | 7 | 7 | 0 |
| cameraSettingsFocusBracketing | 7 | 7 | 7 | 0 |
| cameraSettingsCustomButtons | 3 | 3 | 3 | 0 |
| cameraSettingsConfiguration | 6 | 5 | 6 | 5 |
| generalSettingsWiFi | 2 | 2 | 2 | 0 |
| generalSettingsDisplay | 8 | 5 | 8 | 5 |
| generalSettingsTouch | 4 | 4 | 4 | 2 |
| generalSettingsProfiles | 3 | 3 | 3 | 0 |
| generalSettingsStorage | 4 | 4 | 4 | 2 |
| generalSettingsSound | 5 | 5 | 5 | 0 |
| generalSettingsPowerTimeouts | 3 | 3 | 3 | 0 |
| generalSettingsLanguage | 1 | 1 | 1 | 0 |
| generalSettingsService | 8 | 5 | 8 | 6 |
| generalSettingsAbout | 6 | 6 | 6 | 0 |
| videoSettingsVideoQuality | 1 | 1 | 1 | 0 |
| videoSettingsLiveView | 1 | 1 | 1 | 0 |

## 复现与证据

在仓库根目录执行（仅宿主，须已有固定输入和 `fixes/card-format-r1/build/python-qt515`）：

```powershell
python x1d/candidates/ui-resident/evaluation/full-pages/prepare.py
foreach ($round in 1..5) {
    foreach ($strategy in @('factory','a8','all_pages','all_rows')) {
        python x1d/candidates/ui-resident/evaluation/full-pages/measure.py $strategy "r$round"
        if ($LASTEXITCODE -ne 0) { throw 'measurement failed' }
    }
}
python x1d/candidates/ui-resident/evaluation/full-pages/summarize.py
```

- [输入提取](prepare.py)、[实际测量](measure.py)、[交叉核对及报告生成](summarize.py)。
- [汇总与完整输入/结果 SHA-256](build/summary.json)、[原始进程结果](build/results)、[固定输入清单](build/input-manifest.json)、[全部设置目录](build/catalog.json)。
- a8 输入来自冻结 `ui-resident-0456d37bc5ddbc57/overlay` 的四个 QML，已逐个对照 release 中 outputSha256；原厂输入绑定上述 GUI 摘要。测量脚本 SHA-256：`bcc563e2a22dbc2f7c24e3e08fa421419f8435b4fa10532ce1b9683523642615`。
