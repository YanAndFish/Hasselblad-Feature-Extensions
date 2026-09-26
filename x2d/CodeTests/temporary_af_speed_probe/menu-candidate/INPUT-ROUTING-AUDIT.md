# 菜单与取景输入联动：未完成

范围：第一代 X2D 100C 原厂 4.2.0 `camera-gui`，SHA-256 为 `16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0`。本页结论来自固定固件离线读取，不是新增实机测试。

## 用户要修复的问题

自定义菜单已经显示时，拖动或摇杆仍能移动底层对焦框，半按快门仍进入取景对焦，而自定义菜单未同步退出。用户要求沿用原厂菜单处理方式，不是新写取景界面。引闪页仅展示 UI，仍不连接无线或相机控制。

## 已核对的原厂链路

- `MainViewState.qml` 中，进入 `main_menu_state` 的转换会调用 `stopLiveview`，后者通过视图模型调用 `Camera.doSet_live_view(false)`。这属于状态转换，不是单纯绘制窗口。
- `MainScreen.qml` 在菜单焦点范围内处理并消费导航按键。
- `LiveviewViewModel.qml` 中，触控和按键移动对焦框分别进入 `setFocusPointFromTouchPoint` 与 `moveFocusPointWithKey`；最终焦点坐标通过 `Camera.focus_point` 写入。不能把输入穿透当作纯视觉问题。
- `KeyFocusHandler` 的焦点变化回调 RVA `0x33a298` 会检查聚焦对象及父对象的 `keyOverride`，再调用相机代理虚表槽 `0x7d8`。固定版本虚表解析确认该槽是 `CameraProxyDbus::setForward_input_events`（RVA `0xa8dcd8`），不是仅在窗口里吞掉 Qt 事件。
- 原厂 `GuiProxies::camera` 在 RVA `0xaae050`，静态代理指针槽 RVA `0x21ce888`。`CameraProxyDbus::live_view_state` 在 RVA `0xa93018`，读取代理对象偏移 `0x275` 的状态字节。这些是静态布局；尚未用于当前实机状态同步。

## 尚不能直接当作修复的做法

- 给独立预览增加焦点或全屏触控区域，不能证明相机服务侧快门和对焦控制随之改变。
- 原厂测试页会设置输入覆盖并在退出时恢复，但测试页不是正常主菜单；不直接照搬全输入覆盖。
- 只把前键绑定临时切到 Menu，也没有解决第二次按键退出、原厂取景恢复、自定义窗口隐藏和快速连按的同步。
- 不能对全部关闭菜单调用统一弹出自定义菜单；错误、拍摄、取景切换也会走关闭路径。

## 交付状态

已确认缺少原厂菜单状态与独立窗口生命周期联动；本轮没有新增相机写入，没有安装输入拦截修复。需要接通菜单进入/退出、触控及导航归属，并核对半按返回取景时窗口同步隐藏，才能称为修复完成。
