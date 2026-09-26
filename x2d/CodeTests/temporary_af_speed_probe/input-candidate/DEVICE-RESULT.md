# 输入联动候选：前次失败记录

后续状态：已核实原预览与新菜单的窗口类别差异，并安装修正版；运行中取景停止与恢复已实机通过，菜单显示成功，用户交互验收待完成。以 [窗口修正记录](WINDOW-ROUTING-FIX.md) 为当前状态。以下保留先前候选撤回的历史证据。

日期：2026-09-24。第一代 X2D 100C 4.2.0。

## 实际改动

- `menu_input_loop.sh`：独立菜单打开前通过原厂 D-Bus `set_live_view(false)` 请求停止取景，读取 `live_view_state` 等待 Off 后再显示窗口。退出先隐藏窗口，再恢复本次由加载器停止的取景；原厂恢复取景时，自动隐藏窗口。
- `CustomMainMenu.qml`：补全空白区域触控接收、焦点范围与导航；设备候选使用原厂 `com.hasselblad.keys` 映射。引闪仍仅展示 UI。
- `build_menu_candidate.py --input-route` 将本候选输出隔离在当前目录。
- `Update-MenuUi.ps1 -Variant Input` 保存 `.before-input-ui` 备份；独立暂存目录为 `/blackbox/x2d-input-stage`。

## 已验证

- 实际生命周期 shell 函数的边界模拟通过：停止后显示、隐藏后恢复、原本 Off 时不擅自启动、繁忙和转换状态跳过、调用失败与停止超时不显示、外部恢复不重复请求、退出清理恢复本次拥有的状态。
- 桌面 Qt 导航、引闪 UI 进入返回、默认隐藏与窗口复用通过。
- 实机安装回读一致，恢复系统只读，独立窗口 READY。原厂主 GUI 进程和启动时间未改变，相机与 GUI 服务均 running。
- 实机初始 `live_view_state=0` 时，诊断请求显示与隐藏成功，隐藏可见位为 0。

## 未通过项与证据范围

- 首次请求 `set_live_view(true)` 返回远端失败，随后只读回查仍为 Off；未当作成功或盲目重试。
- 后续在 Off 状态请求 `set_live_view(false)`，明确收到 `com.hasselblad.error.canceled: Ignoring set live view`。无法仅凭该结果判断取景 Active 时的停止调用一定失败，也无法证明开始/停止完整链已通。
- 当时回读：系统 Active、屏幕 Active、相机 Image 模式、`live_view_allowed=true`、无 active_error。不是已证实的权限拒绝或睡眠；拒绝具体条件仍待查。
- 固定原厂 `camera-service` 哈希 `fbcf828f73bca13f0c8b95e7dd0b95ac483ae36954ec06179098c8a1a65f9f82`：`CameraObjectImpl::doSet_live_view` RVA `0x198548`，`X2DCameraStateMachine::setLiveview` RVA `0x113c30`。上述错误文本位于 `LiveviewControlEvent` 析构处理，说明事件未按预期完成，不能归因为 D-Bus 权限被拉低。
- 没有模拟快门、对焦、发射或触发传感器测试。没有验证真实半按快门、摇杆和触控拖动后的最终用户行为。

## 撤回状态

- 候选正常停止，原前键映射恢复成功。
- 恢复引闪 UI 版的 QML、开机脚本及候选脚本，全部哈希对回旧版，系统分区只读。
- 重新启动旧版独立菜单，状态 READY；原厂 GUI 未重启。
- 本候选日志保存在 `/tmp/x2d-input-result`，关机后可能消失；相机上的 `.before-input-ui` 备份保留。
- 输入候选未留作开机默认，不能告诉用户“重启后已完全可用”。
