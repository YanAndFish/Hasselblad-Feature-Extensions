# 回放、引闪、AF 与常驻 UI 的组合接入

本轮只在 `replay-next` 离线实现，USB、设备服务启动、拍摄、AF 和照片访问均为 0。主任务报告的保护基线是引闪 `stable-success-20260912T125921Z`、AF `installed_observation_until_restart` 和 `joint-completion-20260912T131218Z`；这不是本任务对相机现态的读回。

后续主任务报告用户换电冷启动，旧 `/tmp/hbl-wireless-flash` 与 formal 临时 drop-in 已消失；上述快照仅用于历史恢复追溯。下一轮先由 root 针对本 boot 验证并重建正式引闪/AF链，回放 `--prepare` 才能捕获本次真实保护状态。回放不会依据旧快照假定 worker 仍在运行。

原独立 [会话包](SESSION_LOAD_RUNBOOK.md)保留原拒绝已有 drop-in/preload 的规则，**不能用于当前组合更新**。新增组合入口供 root 唯一协调器调用；不绕过原安装器，不自行卸载引闪或 AF。正式模块包已绑定 root 提供的冻结主资源与共同检查器，源码/证据也已冻结；尚未实机装载或验收。

正式交付为 [replay-module.tar.gz](artifacts/joint/fixed/module-57b90e6e02913758/replay-module.tar.gz)，665,763 字节，SHA-256 `57b90e6e0291375857add74ee9eda730bea1b4d6d285f28cf4a00d5e242a301e`。对应 [package.json](artifacts/joint/fixed/module-57b90e6e02913758/package.json)列出 11 个目标文件，[freeze.json](artifacts/joint/fixed/module-57b90e6e02913758/freeze.json)绑定源码、证据及文件摘要；其 SHA-256 为 `38ff7b28f1791dfabe5d752634389b935838534262e708f210ab21b00fd6fd1c`。root 从固定目录的 `files/` 以 `replay/` 前缀纳入总包，不将 `sources/` 或 `evidence/` 传入相机。

## 所有权与最小接口

| 内容 | 唯一负责方 | 回放侧约束 |
|---|---|---|
| `combined-ui.rcc` 注册、GUI 与 `msg2dbus-farm` drop-in、完整 preload 链 | root | 不注册 RCC，不修改这些 drop-in |
| `/tmp/hbl-x1d-combined/install-state` | root | 不创建、删除、写 pulse、释放或续期 |
| `hbl_combined_window_active()` | root 的 `x1d/combined-runtime/native/install_window.h` | 只读调用；构建时绑定头文件及传递依赖摘要 |
| `system-check` | root，固定 `/tmp/hbl-x1d-combined/system-check` | 后端每阶段要求 `--require-held-min-ms 90000` |
| 回放文件 | `/tmp/hbl-x1d-combined/replay` | 整包摘要验证后使用 |
| 回放状态 | `/tmp/hbl-x1d-combined/replay-state` | root 先创建 root:0700；回放只写自身 ui/gpu 和 backend 子状态 |
| configstore/jpeg-daemon | 回放阶段由 root 明确派发 | 只创建这两服务的 `90-x1d-replay-joint.conf`，从原厂程序切到配套候选 |
| 引闪/AF RAM、回调链及设备侧恢复 | root 与 AF 任务 | 本模块完全不写；前后证据由 root 串行核对 |

共同窗口采用新命名空间和 root 的只读接口，绝不触碰已释放/到期的旧 `formal-state`。编译器包含 root 共享头的只读定义，但产物审计要求没有旧引闪路径，也没有 `socket/bind/connect/sendto/recvfrom` 导入。

## 资源组合与 native 接入

`tools/compose_joint_resources.py` 提供 `compose(resources)`，输入字典必须含唯一 `/main.qml`，返回新字典。它在固定 `objectName: "mainRoot"` 根的最后闭括号前追加一个 `QtObject`，`Component.onCompleted` 只设置 `x1dReplaySession.resourceReady=true`。旧 root 正文、引闪曝光续行、电源段及其余资源逐字保留，重复应用、锚点缺失/重复均拒绝。没有活动 Timer、第二套 pulse 或额外曝光/输入动作。

root 合并引闪/电池/AF等资源后调用回放 compose；《X1D UI》最后执行常驻 UI compose，只允许改变其四份资源，`/main.qml` 摘要须保持。冻结后将最终主资源落盘并提供路径/SHA-256。示例输入仅用于离线组合测试，`artifacts/joint-tests/example-main.qml` **不是安装输入**。

组合库 `libx1d-replay-joint.so` 只导出：

- `_ZN21QQmlApplicationEngine4loadERK4QUrl`：对自有 `qrc:/main.qml` 核对实际 `:/main.qml` 摘要、原厂 GUI/Qt 文件及私有目录后注入 `x1dReplaySession`；调用 `RTLD_NEXT` 恰一次。其他 URL/engine 直接透传。
- `x1d_replay_session_admit`：沿用生产 provider 的准入接口，工作线程读原子状态，纹理工厂入口重新检查当前 GL 上下文。

不导出或调用 `qRegisterResourceData`/`QResource::registerResource`。root 的资源注册器与 formal adapter 保持原职责。最终链中需要 `X1D_REPLAY_SESSION=1`，使用组合库；**不得同时载入独立 `libx1d-replay-session.so`**。`replay-owners` 是既有 `replay-check` 的相同二进制，只允许组合脚本调用其 `--owners configPID jpegPID storagePID` 分支，该分支不读取旧回放会话状态。

GPU 观察器由 native 的 250 ms Timer 接入实际 `QQuickWindow::beforeRendering`。首次接入请求一帧；后续仅在 root 共同窗口 fresh 时请求帧更新。`sceneGraphInvalidated` 清除准入。没有额外 QML 帧锚点，root 只需原健康保持段和上述被动回执。窗口释放后不再持续主动刷新，但正常发生的渲染仍更新能力状态。

`replay-joint-check --gpu <当前GUI_PID>` 要求实际 root 回执、同 PID 的 2 秒内 GPU 记录，三次采样时间戳必须递增；上限至少 8176，BGRA 和 NPOT 均支持。它证明上下文能力与持续样本，**不证明 Full 纹理分配、上传或最终显示**。GL 内存不足仍无自动回退，CPU Full 缓冲 200,410,112 字节也不是整机峰值。

## root 的阶段顺序

1. 确认引闪已关闭、无拍摄/编码/写卡/删除/更新及待机切换；保留固定恢复证据及当前 AF/引闪 RAM、回调读回。上传/大文件摘要核对在旧 GUI 仍正常运行时完成。
2. root 创建新共同窗口和回放私有目录，先启动**桥接 GUI**：最终同一 RCC、root/formal/AF 上下文及组合守护库，暂不加载回放 provider。root 检查新 GUI 正常、fresh pulse、默认关闭、全部组件编译与回放 GPU 检查。不得用旧 GUI 的过期 hold 代替。
3. 若 root 需要更新 `msg2dbus-farm` 的 Linux 配置，应在回放 `--prepare` **之前**完成并核对。正式 worker 位于 `msg2dbus-farm` 同一进程，**不存在独立 `hbl-wireless-worker` 服务**。回放固定保护 `msg2dbus-farm` 与 `storage-daemon` 的 PID、starttime、exe 摘要，并核对正式 worker 登记文件为 `same-process=1`、同 FARM PID、`master=0 radio-held=0 radio-busy=0` 和 ready/default-off 状态；之后不能重启受保护进程而仍声称同一准备快照有效。
4. root 派发 `sh /tmp/hbl-x1d-combined/replay/backend.sh --prepare`。该阶段只核包/74项原厂基线、共同保持、GUI GPU、原厂两个后端、DBus owner，并建立回放自身 backend 状态。不重启任何服务。
5. root 派发 `--config`，等明确结束并读回设备侧保护证据；然后派发 `--jpeg` 并再次核对。两阶段分别重启 configstore、jpeg-daemon，检查对应程序摘要与 owner；JPEG 还检查适配库 maps。每次启动前必须尚余至少 90 秒共同保持。阶段不重叠、不自动重试。
6. root 再重启 GUI，在已验证的**相同 RCC/上下文链**中增加 `libx1d-replay-provider.so`，检查 root/formal/AF/回放各自状态、GPU 及保护证据。只有 root 判定所有模块达到所需状态后才释放共同 hold。

本模块不会执行步骤 1–3、6 的 GUI/FARM/设备动作。AF 新功能的 RAM 更新与回调恢复由 AF 任务给出独立契约，root 在其规定的位置串行执行；回放的进程保护检查不能替代 AF/FARM RAM 核验。

`formal-worker.status` 在 worker 构造与停止时写入，**不是实时 master/busy 心跳**。以上字段核对只证明与当前 FARM PID 对应的登记快照符合要求；实时关闭、无忙任务与无用户干预仍由 root 在独占窗口内确认，不能将旧登记文件升级为当前无线状态证明。

## 部分失败与四模块保留

| 失败位置 | 本模块留下的状态 | root 的恢复责任 |
|---|---|---|
| 桥接 GUI 或 GPU 未就绪 | 后端尚未准备/重启 | root 恢复自己先前可用的 GUI 链；引闪/AF RAM不由回放处理 |
| `--prepare` 前置不满足 | 不创建 backend 状态、不重启服务 | 保留现有模块，停止推进 |
| config 已触及，JPEG 尚未触及 | config 的自有 drop-in/阶段退出码 | 保持桥接 GUI 健康，显式派发 `--restore`；只恢复 config |
| config/JPEG 任一后续失败 | 已触及标记、退出码和各自当前程序 | 先确认阶段已结束及保护快照仍一致，再显式恢复本模块后端 |
| 增加 provider 后 GUI 失败 | 两个后端候选仍可能运行 | root 先回到步骤 2 已验证的桥接 GUI，保持新窗口，再派发回放 `--restore`；不要先退到只有旧过期 hold 的 GUI |
| 后端恢复中失败/共同窗口失效/保护进程改变 | `restore.exit` 非零及每服务 restored 标记，绝不写 `restore.done` | 停止；root 根据实际状态与各模块恢复证据制定后续动作，不盲目重发或执行全局恢复 |

`--restore` 只验证并移除本模块的 config/JPEG drop-in，以 config→JPEG 顺序恢复本轮触及的原程序。未知内容保留并退出，GUI、常驻页、引闪 observer/worker、AF RAM、回调、共同 hold 和原恢复记录均不由此脚本修改。已产生的照片/记录与已保存的设置也不属于卸载可撤销内容。

每阶段用 noclobber `.sent` 登记，退出码通过 `.exit.next→.exit` 原子发布。存在 sent 而没有 exit 时，后续阶段和恢复均拒绝；收到不明确传输结果后 root 只读观察，不重发。成功或失败的 restore 都不允许盲目第二次执行。`--status` 输出记录阶段、config/JPEG 当前原厂/候选/未确认状态、三个退出状态及受保护进程是否仍匹配，输出有界；它不是四模块功能验收结论。

root 若在回放准备之后有意改变受保护 Linux 进程，必须视为旧事务前提已变；当前脚本不提供“接受新的 PID”或清除 sent 的快捷路径。root 应提前安排这类更新，或显式结束当前事务再设计新事务。

## 最终冻结与打包

root 已提供并完成绑定的输入：`x1d/combined-runtime/build/fixed/main-7adb70915d798fbf/main.qml`，SHA-256 `7adb70915d798fbf24004c512c3fa0ffaf3e331a1721416172b45250bb23ea76`；`x1d/combined-runtime/build/fixed/install-window-e373262db5b23f56/system-check`，SHA-256 `e373262db5b23f567b22060f1a61687c723cbbbae3c1e237e60728015d3ccca0`。本模块不冻结全 RCC，AF 独立页面继续由 root 合成并断言最终主资源仍一致。最终 RCC 路径为 `/tmp/hbl-x1d-combined/combined-ui.rcc`，root 状态位于 `/tmp/hbl-x1d-combined/ui.status`；回放不覆盖这些路径。

复现构建与后续重新冻结时运行：

```text
python -B x1d/candidates/replay-next/tools/build_joint.py --main-qml <最终主资源路径> --main-sha256 <完整摘要>
python -B x1d/candidates/replay-next/tools/build_joint_package.py --joint-manifest <刚生成的manifest路径> --system-check <共同检查器路径> --system-check-sha256 <完整摘要>
python -B x1d/candidates/replay-next/CodeTests/run_joint_package.py --package <模块包package.json路径>
python -B x1d/candidates/replay-next/tools/freeze_joint_package.py --package <模块包package.json路径>
```

产物在 `artifacts/joint/<main摘要前12位>/`，模块包在其 `module-package/`。root 可直接把 `module-package/files/` 以 `replay/` 前缀纳入自己的组合包；本模块包不含 RCC、GUI drop-in、FARM程序或设备传输器，也不能独立调用原 `Transfer` 装载。构建器验证最终主资源、共享头、核心产物及测试报告当前摘要；构建期间输入变化会拒绝输出有效清单。

## 验证状态和目标验收清单

资源组合保护、宿主实际 QML 被动回执、实际 shell 后端契约、实际 ARM 共同窗口/权限/时效/GPU条件检查及新 ARM 库/检查器静态审计分别记录。当前后端用例数量与结果见[后端验证报告](artifacts/joint-backend-tests/validation.json)，包含无独立 worker 服务、同进程/PID及登记字段拒绝条件。服务、DBus、文件系统、时钟及 GPU 边界依各报告明确采用替身；原 Qt5.5 loader/QML 全链仍待目标执行。[固定恢复证据核对](artifacts/joint-tests/coexistence.json)逐项核对既有快照；AF journal 的既有链头取主任务审计结果，本任务未重跑设备链审计或改变它。

root 的真实 Qt5.5/GPU 验收至少包括：

- 当前 `/main.qml`：实际构造、root健康保持、formal默认关闭、回放被动回执；新增 AF 上下文由其任务列出精确依赖。
- `/controlscreen/NativeFlashPage.qml`、`/FormalExposureGate.qml`、`/controlscreen/ControlScreen.qml`：沿用 formal 的 compile-only 验收，并按 root 的 UI 修正检查显示和手势。
- `/mainmenu/MainScreen.qml`、`/mainmenu/Menu.qml`、`/settings/SettingsGeneric.qml`、`/mainmenu/ResidentLoader.qml`：真实 Qt5.5 编译、原厂菜单/设置生命周期与输入；AF 新页面按最终清单补充，不能猜文件名。
- 同一 GUI 的真实 GL 能力、场景图失效重建；后续按授权材料验证预览/Full、颜色/方位、放大/离开/切图/取消、纹理 bind 上传、内存/配额归还及机内耗时。
- 实际 DBus owner、CloseFile 成功回执与 v3 记录发布；root 在每服务/设备阶段保存引闪与 AF 的不变或已批准转移证据，最后验证部分失败恢复。

目标验收缺口不能由主机帧计数、模拟器指令执行或静态包摘要代替。旧独立回放包的离线证据继续有效，其安装契约没有为组合更新而放宽。
