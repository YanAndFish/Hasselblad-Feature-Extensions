# 保留 AF r4 的常驻 UI 会话

本版本只用于固定 f325 AF Linux 会话已经安装、AF r3 RAM 安装已经完成且 hold 已释放，并已应用 AF owner 的 GUI r4 修复的环境。它不适用于原厂 GUI，也不应覆盖回未修复的 AF 页面。设备由主任务独占，本目录内的构建与测试不访问设备。

已绑定 AF owner 固定 r4 归档 `0448c022ed474effc5130b3c541cf95a75c05cbf1dffea2f9ee7f5bb1c53435e`。最终共存归档为 `83b87e750248014e83fa90c543babe6f7defe36f460ad008a364caaca304d28d`，46,523 字节；固定路径、阶段命令与验收边界见 [交接单](../AF_SESSION_HANDOFF.md)。97 项离线检查通过，`delivery.py` 默认核验返回 `readyForRootStaging=true`、`targetValidated=false`；本任务未装载相机。

绑定文件为本目录的 `r4-binding.json`，记录固定归档、SHA 和 95 配置字节；任一输入变化都会拒绝交付，不能用仍在修改的源文件代替。

## 资源与加载链

当前 f325 AF 七资源里只有 `SettingsGeneric.qml` 与常驻 UI 重叠。对它应用既有常驻补丁，并逐字保留 `cameraSettingsAdvancedAF` 分支与 `afCloseRequested` 返回连接。新增覆盖 RCC 仍只有四资源：这个合并后的设置页，以及修正版固定包中的 `MainScreen`、`Menu`、`ResidentLoader`。AF r4 的 `SettingsPage.qml` 来自其固定 RCC，另外六个 AF 资源必须与 f325 逐字相同。

加载顺序固定为：

```text
libhbl-ui-af.so
  → 原 libhbl-af-only.so
  → AF owner 的 r4 libhbl-af-ui.so
  → Qt5.5
```

本增量库首先注册 `/tmp/hbl-ui-af/ui-af.rcc`。随后原 AF-only 库请求注册旧 AF RCC 路径，r4 库将且只将该路径重定向到 `/tmp/hbl-af-ui-r4/af-only-ui.rcc`，最后注册原厂资源。Qt 5.5.1 的注册操作将资源放到列表末尾，文件解析采用首个匹配数据；见 [Qt 5.5.1 原始实现](https://raw.githubusercontent.com/qt/qtbase/v5.5.1/src/corelib/io/qresource.cpp)。因此先注册本增量，但就绪判断仍逐一使用 Qt `QFile` 回读全部十个生效资源摘要，不依赖顺序推测或 `registerResource=true`。

`QQmlApplicationEngine::load` 仍经过原 AF-only 和 r4 AF-ui 的两个 hook，由它们各自提供 `hblAfInstall` 和 `hblAf`。本库不创建第二份上下文；通过 `dladdr` 核对下一跳确实是固定原 AF-only 库，并在正常根创建后检查两个不同的上下文对象及 hold 已释放。目标还检查八个实际组件 Ready，不独立 create 额外 AF 页面。

离线 QML 检查执行了正确/错误注册顺序、十个资源的实际 Qt 回读，以及真实 `SettingsGeneric` 分支和 ControlScreen 中央按钮插入块。外围原厂业务插件为显式替身，图形效果只在主机副本中适配；这些不是目标 Qt5.5 或 AF 后端实测结果。

## 独立配置与恢复责任

保留以下原配置原样：

- `90-hbl-af-only.conf`：原 AF GUI 和 AF bus 配置。
- `95-hbl-af-ui-r4.conf`：AF owner 的 GUI 修复配置。

本版本只新增 `/run/systemd/system/victory-gui.service.d/99-hbl-ui-af.conf`，设置 `HBL_UI_AF_ENABLE=1` 并将本库放到已有 preload 之前。AF r4 开关及其文件保持。恢复只移除本包原样 99 配置，重新启动 AF r4 GUI；不调用原厂独立包的 restore，也不撤销 90/95。

GUI 正常停止且旧 PID 已退出后，允许清除其遗留的 `/tmp/hbl-af-settings/ui.sock`，要求该文件确实为本用户 0600 socket。原 AF UI 库自身不会在 bind 前覆盖旧 socket，因此此步骤是 GUI 重启所需的清理。后台 socket、bus 进程、AF RAM 和持久配置均不操作。

前置检查核对原厂基线、f325 包、r3 已完成收据、hold.release、r4 包及两套精确配置、实际进程 preload、AF bus 状态和系统健康。unit active 不等于相机 Active；健康检查接受稳定 Active 或稳定 Standby。陌生配置、错误库、未释放 hold、不同 AF 收据都会在停止 GUI 前拒绝。安装前记录保护摘要和总线 PID，安装后与恢复前后再次校验。

同时核对 AF r4 的 `ui-r4.status`：20 个有序字段、当前 GUI PID、`bound=1`、`applying=0`。错误绑定、旧 PID、正在提交或格式异常会拒绝停止 GUI；集成启动后的检查失败则恢复到 AF r4。

本版本不发送 apply、read 或 visible 命令给 AF 后端。正常 UI 重启会创建原 AF 上下文；常驻预建过程不会呈现 AF 页面。用户之后打开 AF 页面，仍由原 AF r4 逻辑处理其交互。

## 构建与阶段入口

从 Hasselblad local 根运行：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/build.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_af_coexist_qml.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_af_coexist_install.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_af_coexist_delivery.py
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/package.py --build
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_af_coexist_package.py
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/delivery.py
```

最后一行始终只离线核验。取得固定包后，由主任务使用同一 delivery 命令的显式选项：`--stage`、`--phase preflight`、`--phase ui`、`--phase status`。仅需要撤销本轮 UI 时执行 `--phase restore`，其目标是 AF r4 GUI。

远程根 `/tmp/hbl-ui-af` 与旧原厂 UI 包隔离。Linux 实际入口为 `sh /tmp/hbl-ui-af/run.sh preflight|ui|status|restore`。脚本只 stop/start `victory-gui`，不会重启 `msg2dbus`、清除 AF RAM、修改 AF 设置，或加入回放/引闪。

发生通信结果不明时只使用 `--observe ui` 查看已有阶段结果，禁止再次派发安装。阶段锁和 sent/exit 文件保留；发现后台 PID、AF 配置或依赖文件变化时停止并留证，不擅自恢复其他负责人控制的状态。
