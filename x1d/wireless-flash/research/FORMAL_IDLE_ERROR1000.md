# 引闪组件更新期间的待机切换与错误 1000

2026-09-12。来源限定为本轮 X1D 1.25.0 临时装载及同一次启动的实时日志。用户回来后看到 1000，明确离开期间没有操作相机；不能将其写成按快门或试闪触发。

## 已确认的时间线

以下时间是相机本次启动以来的单调时钟秒数，不使用相机日历时间推断先后。

| 单调时钟 | 记录 |
|---|---|
| 8092.315947 | `victory-gui` 已停止，属于本任务继续更新步骤 |
| 8093.612936 | 系统管理器进入 `prepareActiveEnter`；此前为 Standby |
| 8093.637646 | `failEnter` 报 `1000 / 5 / 1`，来源为 `systemmanager.cpp` |
| 8096.447960–8096.838939 | FARM 消息转接服务停止并重新启动 |
| 8098.189267 | `victory-gui` 重新启动 |

故障进入日志明确为 `linkStatusDown` 触发 `Fail`。唤醒准备附近记录 `SUC: true FARM: false SPC: false`；后续状态日志仍为 `system_state: 6`。这些是软件连接检查，不能当作供电或控制器损坏的测量。

错误早于这一轮真正停止 FARM 转接服务，不能简化成“重启 FARM 服务后才报错”。当前证据指向更新中停止 GUI、待机退出与连接状态恢复的交互；尚未还原使 FARM/SPC 连接状态未就绪以及此次唤醒开始的完整事件链。

## 固定原厂代码的后续核对

离线重新核对固定 1.25.0 `system-manager`（SHA-256 `7bb4e33f13417f7c15dfcbfbb29d552f1c386429bad52da030acde489dc4dba5`）：`SystemManager::prepareActiveEnter` 在 `0x20538` 调用 `allLinksUp`，false 在 `0x20540` 跳至 `0x20704`，并于 `0x20708` 直接发出自身的 `linkStatusDown`。这与已取得的日志序列相符；该信号不要求在那个时刻另外收到一次外部断线通知。最初是哪项底层状态或待机行为造成连接未就绪仍未确定。

固定 GUI（SHA-256 `d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`）的 `/main.qml:129–143` 在 sleeping 变化时调用 `PowerClient.setState`，上报 Idle 或 Active；`/common/TouchWindow.qml:2252–2277` 由原厂活动计时器及活动通知参与此协调。因此 GUI 是电源协调客户端，不能在设计更新事务时仅视为画面进程。但这段静态代码本身不证明停 GUI 是此次唤醒的唯一触发源。

故障前的已保存日志还显示 `isReadyForStandby ui: 1 mo: 2 bo: 1 ph: 1 fa: 0`，随即 `readyForActive` 离开 Standby。这里只保留原厂数值；没有把这些客户端意愿值当作实际控制器连接值。旧继续安装程序在停止 GUI 后还会读取 FARM 采集区；该顺序与电源客户端交互需一起审查，不能仅把 FARM 服务重启移前或加一次延时就认定修复。

## 故障发生后的状态与边界

UI、观察器和 worker 的组件自检通过，只能证明组件加载。诊断时三个 Linux 服务均 active，worker 启动标记为默认关闭；系统层已经进入非可确认错误。安装成功记录不等于当前相机可正常使用。

没有新增拍摄、试闪、设置、重启、错误清除、FARM 写入、无线发射或驱动操作。AF 尚未装载，UI 常驻改动也未写入相机。此次只进行了有界筛选的日志和自有状态读取，各请求句柄均关闭。

诊断原始记录位于 `build/formal-flash-package/idle-error1000-*.json`。协议单次输出只有约 232 字节，首次 `events` 的长日志结果发生截断；随后改为短字段及少量行分别读取，时间线采用完整返回字段。空白错误筛选不能证明不存在错误。

## 用户重启后的核对

用户随后正常重启，并明确确认开机完成。2026-09-12 19:47（北京时间）三次只读请求确认：新启动 uptime 约 60 秒，`victory-gui`、`msg2dbus-farm`、`system-manager` 均 active；系统状态日志已经到达 `Active state / prepareActiveDone`；`/tmp/hbl-wireless-flash` 已不存在。对本启动最近 1500 条系统管理器日志的有限错误筛选没有返回报告，结合 Active 状态可确认本次核对时已恢复正常启动；空筛选本身不能证明任何后续时刻都无错误。

证据为 `build/formal-flash-package/after-error1000-reboot-state-20260912.json` 与 `after-error1000-reboot-errors-20260912.json`，全部请求句柄关闭。重启由用户完成，主任务没有重启、拍摄、试闪或重新装载。Linux 临时目录已清除；没有在本轮重新读取 FARM 全部 RAM，因此旧采集恢复记录不能作为当前驻留状态。上一轮安装成功记录仅保留为历史证据，AF 与回放任务均已收到新启动状态并保持不安装。

## 后续条件

用户随后明确要求修好并装载引闪与 AF；本任务负责串行实机安装，AF 源码修改仍由“研究哈苏 X1D”负责。旧 `u3`、`u4` 更新和继续安装程序绑定前一次运行中的包与回滚现场，不能在这次新启动上重新使用。

后续更新不能仅检查进程 active、自有采集空闲和组件解析。必须先验证系统整体处于稳定可用状态，完整核对待机/唤醒与服务切换的交互，并在完成后确认系统未进入失败状态。未经验证不能通过隐藏错误弹窗、伪造连接正常或清除错误属性来标记修复。

一次开始前的 Active 检查仍不足以覆盖较长上传期间以及停服后的状态变化。新版流程已实现：先完成 Linux 文件上传，再用固定版本的 D-Bus 缓存属性确认系统 Active、SUC/FARM/SPC 连接与 UI PowerClient；首次仅重启 GUI，独立 QML Timer 使用原厂 `idleWakeupOrForceOff(true)` 通知活动，产生同 UI PID 的新鲜脉冲后才允许首次 FARM 基线读取。随后准备无线并重启转接服务，再确认连接恢复。FARM 安装各阶段和最后均检查系统与脉冲。未改原厂电源配置、未强制唤醒睡眠界面、未伪造正常状态。截止时间由目标 CLOCK_MONOTONIC 一次建立，最多二十分钟；重启 GUI 不续期，释放或到期即停止活动通知。

离线通过安装/恢复模拟 73 项、真实注入 Timer 的 QML 替身 13 项、原运行接线 QML 72 项与编排 5 类测试（22 阶段失败停止和 AF 联装保留门控）。Qt 主机替身不等于目标 Qt5.5 全部实测。

新包 SHA-256 `a57af6e4ed383daa59e58ba4b33e5d2ee54f40f79e2bceb2e309d30e347f6327`，147174 字节，固定快照 `build/formal-flash-package/stable-install-20260912T123138Z/`。已完成 Linux 上传并校验，记录 `staged-20260912T123138Z.json`，1207 次 Linux 请求、全部句柄关闭、0 FARM 请求、未重启服务。随后三次请求核对 system-manager 原字节哈希、执行自有 `--check` 并读状态；自检成功，状态为 `system=4 suc=0 farm=0 pwr=0 ui-power=1 hold=0`，即本次读取时正常待机。记录 `stable-checker-target-20260912T1237.json`。尚未建立 hold、重启 GUI、修改无线或装入 FARM/AF；等待用户手动点亮屏幕后重新检查实时状态，不能拿过去 Active 状态继续安装。

## 无需手动点亮与本启动实际装载结果

用户指出以前可黑屏安装后，重新核对原厂 `/main.qml:446–460`：初次进入主界面会依次请求 PowerClient Idle、Active，并执行 firstActivate。由此修正过严的前置条件：仅 UI 首阶段允许从三项连接全部正常、UI PowerClient Idle 的稳定 Standby 开始，正常重启 GUI 后再检查实际 Active 与新鲜脉冲；任何 FARM 阶段仍不允许 Standby。前段“等待用户点亮”是当时的过严限制，已撤销，不应继续要求用户执行。

第二版首轮尝试 [installation-20260912T124429Z.json](../build/formal-flash-package/installation-20260912T124429Z.json) 在自检后、建立 hold 前返回 64 并完成本阶段恢复。4 次 Linux 请求、0 FARM、全部句柄关闭。目录权限实读为 root/700，却没有生成 deadline；也没有 GUI/FARM drop-in，未执行实际服务重启。原因是新保持代码用了现代工具链 stat/lstat/fstat，与固定 ARM glibc 2.22 的结构版本不兼容。改用同项目既有 `__lxstat64(3,...)` 和配套 `__fxstat64(3,...)` 后，机内 `--check-files` 成功；现代 stat 对照确实返回 `-1 / errno 22`。未放松权限、类型、链接数、完整读取或固定路径检查。

成功记录为 [installation-20260912T125921Z.json](../build/formal-flash-package/installation-20260912T125921Z.json)，固定包 `d7e06ad983915f77c1ffe87893457703f5b8ec6d6e706ff028590536f71feef9`、148364 字节。GUI 首阶段实际从上述正常 Standby 成功进入 Active，并确认同 PID 的新鲜安装脉冲；随后才读 FARM 基线，再准备无线和观察器、装八处采集入口、验证使能。31 次 Linux、4753 次 FARM 请求（948 写），全部句柄关闭，自动拍摄/试闪为零；最终系统 2、全部连接 0、UI PowerClient 0、hold 1。未出现上次的 prepareActive/linkStatusDown 故障。新流程完成了这一次实机安装验证，但不据此宣称所有将来的待机、更新和恢复场景都已验证。

本启动已确认失败或未执行的旧包分别原样保留在 `/tmp/hbl-flash-stage1`、`/tmp/hbl-flash-stage2`；成功包、原记录、恢复记录及哈希快照在 `build/formal-flash-package/stable-success-20260912T125921Z/`。为接续 AF，引闪成功后曾保留二十分钟硬截止的活动保持与用户引闪门控。截止不自动续期，AF 每段均通过固定最小剩余时间准入检查。

2026-09-12 21:12（北京时间）联合装载已收尾。AF 观察版证据 `x1d/af-experiment/recovery/native-observe-20260912-210755.json` 的 26977 项追加事件链完整，终态 installed、全部句柄关闭且无在途缓存/写入；原厂精扫与引闪代码保留，预测执行和速度覆盖关闭。独立 [联合收尾记录](../build/formal-flash-package/joint-completion-20260912T131218Z.json) 确认 7 次 Linux 请求均关闭，用户引闪门控取得 worker 确认后才退出保持，最终 `system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0`。本轮未触发对焦、拍摄或试闪。原成功记录不改写，所有安装连接已释放，可以断开 USB；这只证明本次装载和退出保持时的实际系统状态，不代表后续所有待机场景已覆盖。
