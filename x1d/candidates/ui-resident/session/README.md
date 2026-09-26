# 独立 UI 会话装载包

此入口供独占相机的主任务串行执行。本任务只完成本地 ARM 构建、离线事务测试和固定包交付，设备请求为 0；目标 Qt 5.5 QML 编译、真实页面交互及性能仍需在装载时验证。此包不表示已通过实机验收。

## 固定内容

- 来源为 X1D 1.25.0 的 `victory-gui`，SHA-256 `d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`。装载前核验原厂程序和所链接库的摘要，不能凭固件名称代替。
- RCC 为不可变修正版 `0456d37bc5ddbc57b97e8a9e8cc41b3eff0bd5efa192215bd9f3ae6022029994`，25,185 字节，只含 `ResidentLoader.qml`、`Menu.qml`、`MainScreen.qml`、`SettingsGeneric.qml`。未改 `main.qml`。
- 一个 ARM32 Qt5.5 资源注册库 `libhbl-ui-resident.so`，加一个独立的只读 `ui-health` 程序。包中没有其他功能模块、FARM 内存装载器或总线注入库。
- 相机临时目录 `/tmp/hbl-ui-resident`；唯一 service drop-in 为 `/run/systemd/system/victory-gui.service.d/90-hbl-ui-resident.conf`。整个包只允许 `victory-gui` 的 restart/stop/start；不重启 `msg2dbus-farm`、configstore、jpeg-daemon 或相机。

`ui-health` 复用已核对的正常 D-Bus 属性协议，查询系统状态、三条链路状态及 UI 电源状态，禁用服务自动启动，不写属性、不设置安装保持、不发心跳或唤醒。一次检查取三份状态、核对 UI PID 稳定，整体设置 8 秒进程超时。这里的 linkstatus 查询不是 FARM 内存读写请求。

前置健康同时接受原厂 `system=2/power=0`（Active）和 `system=4/power=1`（稳定 Standby），要求 suc/farm/pwr 链路均为 0。`systemctl is-active` 只是服务状态，不能代替这些相机状态。稳定 Standby 可进入 UI 阶段，由重启后的原厂 `main.qml` 执行其正常初始化；其他状态会被前置拒绝，不自动发送唤醒操作。

## 本地构建和核验

所有命令从 `.` 运行，只写 `x1d/candidates/ui-resident`。

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/session/build.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_delivery.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_session.py
py -3 -X utf8 -B x1d/candidates/ui-resident/session/package.py --build
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_session_package.py
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py
```

最后一行默认离线：校验固定源、报告、包及摘要，返回 `readyForRootStaging`，不初始化 USB。冻结包的位置与 SHA 由 `../build/session/current.json` 指向的 `package.json` 给出。不要编辑已冻结的 `0456d37b` 资源目录。

## 主任务实际阶段入口

以下显式选项会访问相机。仅由当前独占设备并具有本轮装载授权的主任务执行；本任务没有执行这些命令。

```powershell
# 只传输到新的自有临时目录、摘要核验、解包，不重启 GUI。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --stage
# 原厂程序/Qt 库摘要、服务、drop-in、进程环境、健康检查；不改 service。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase preflight
# 写本包 drop-in，重启 GUI，核对资源、组件、PID、库映射、健康和总线 PID。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase ui
# 可以重复的当前健康检查；不会重新安装。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase status
# 用户或主任务要求恢复时，移除本包原样 drop-in 并启动原厂 GUI。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase restore
```

单个 Linux 阶段的直接入口是 `sh /tmp/hbl-ui-resident/run.sh preflight|ui|status|restore`。远程协调器已按 231 字节命令上限拆分传输，使用逐段摘要、经典 `od -v -c` 分行解码、完整 archive 摘要后解包。它只在显式阶段中延迟导入已固定来源的 Linux 命令传输类，所有本机证据都写本候选目录。

每个非 status 阶段只派发一次，远程 `phases/<阶段>.sent/.exit/.log` 和原子目录锁记录结果。`--stage` 不能复用已有目录，也不自动覆盖/清理旧阶段。

发生 USB 读响应不明时，协调器立即停止且不重发。由主任务先确认通道状态，再使用只观察入口：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --observe ui
```

`pending` 不等于成功或失败。保留证据，检查已有进程与锁，不删除锁来强行重装。已知失败且本包安装进程退出后，才使用本包恢复入口；不能对结果不明的安装派发第二次 UI 阶段。

## 就绪检查的含义

注册库只在固定原厂资源表地址首次注册时先加载 RCC，并核对运行程序与 RCC 摘要；随后使用 Qt 的 `QFile` 对四个有效 `qrc:` 路径逐一核验摘要，避免只看 `registerResource` 返回值。原厂根 QML 建立正常上下文后，对以下组件检查 `QQmlComponent::isReady`，不额外 `create()` 页面：

1. `qrc:/mainmenu/ResidentLoader.qml`
2. `qrc:/settings/SettingsGeneric.qml`
3. `qrc:/mainmenu/Menu.qml`
4. `qrc:/mainmenu/MainScreen.qml`

成功标志是 `ui-resident-ready-resources4-components4 pid=<本次 GUI PID>`。脚本还要求原厂根对象存在、服务 active、本库进入该 PID 的映射、健康检查 PID 一致、总线 PID 未变化。组件错误写入 GUI stderr/journal，状态文件仅包含类别和 PID。此就绪状态仍不等于菜单交互或实机性能验收。

之后主任务按既有 UI 验收项目检查菜单首次打开、再次打开、通用设置切换、退出与返回、主菜单滑动和休眠后恢复。关于/维护页面只检查显示与取消，不调用升级、重试升级、拍照或传感器操作。此包不加入额外 UI 功能。

## 失败恢复与会话协调

UI 安装在写 drop-in 后出现可知失败，会自动调用本包恢复脚本：只停止 GUI、删除与本包记录逐字一致的 drop-in、启动原厂 GUI并重新检查健康。原始 UI 阶段仍记录非零退出，不因恢复成功而标记安装成功。若发现 drop-in 被修改、另有新 drop-in 或恢复检查失败，保留文件与证据并返回 `recovery-required`，不接管其他会话。

当前回放会话存在时，可以由主任务决定是否只暂存此包；UI 的 preflight/ui 会拒绝回放对 GUI、configstore、jpeg-daemon 等服务的 drop-in，即使它们还未 daemon-reload。不能将此库追加到别人的 `LD_PRELOAD`，也不能覆盖同一配置。要走本包已验证的原厂入口，先由回放自己的恢复流程完成收尾、确认其服务已回到原厂，再执行本包 preflight/ui。

若未来要在同一次会话同时启用回放与 UI，需要主任务单独形成共享 GUI 装载包，固定两者资源顺序、单份 drop-in 和完整恢复责任，再进行组合验证；此独立包没有把那条路径标为已验证。原厂 GUI 重启会重新执行原厂初始化和正常连接流程，这是实际装载的既有副作用；本包没有改写该流程。

脚本不会自动清理相机临时目录或更改开机持久配置。断电/重启后 `/tmp`、`/run` 的会话状态失效；不能拿上次的本机成功记录代替本次前置核验。
