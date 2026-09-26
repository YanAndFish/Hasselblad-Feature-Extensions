# 1.25.0 页面生命周期审计

证据类型：下表是固定 1.25.0 `victory-gui` 内 QRC 文本的**静态审计**。实例复用与交互结论来自显式替身的主机 Qt Quick 测试，不代表目标相机实测。二进制哈希见 [README](README.md)；未改资源的文本哈希保存在 `build/validation.json` 的 `protectedResourceHashes`。

| 原 QRC 路径 / 入口 | 静态发现 | 本候选处理 |
| --- | --- | --- |
| `/mainmenu/MainScreen.qml` 的 `menu_loader` | 每次 active 关闭销毁 Menu；文件底部另建 SettingsGeneric 后立即清 source | 仅替换此加载器，并删除旧预加载块；MainScreen 的外层创建条件、状态切换和遮罩不变 |
| `/mainmenu/Menu.qml` | `populateModel` 取能力/配置；`subMenuAboutToShow` 间接触发 About 的设备版本读取 | 提前创建空菜单；仅用户进入时刷新和发进入信号。关闭断开能力/配置连接，停轮盘计时器，清模型与焦点 |
| `/settings/SettingsGeneric.qml` | 下拉、确认框、信息提示；原 `onFocusSizeChanged` 写 `Camera.focus_point` | 提前创建空页面。原业务信号以 `residentPresented` 门控；关闭清选项行、分节、lastIndex、下拉框、临时 Loader 和提示计时器；进入重读参数 |
| 同页 `versionID` / `fwUpdateRetry` / Service | 版本号点击调用隐藏入口；重试按钮打开 GenericConfirm，右侧确认调用 Upgrader | 原动作文本保留；只在用户打开列表后创建这些选项，未预热确认框或调用升级 |
| `/settings/DateTime.qml` | `Component.onCompleted → populateModel → SystemTimeControl.loadSystemDateTime()` | 留在临时 Loader；未把构造中的系统时间访问提前 |
| `/settings/SpiritLevelView.qml` | 创建 `SpiritLevel`，完成时调用 `setSpiritLevel()` | 保留原生构造与关闭边界，不预热传感器相关页 |
| `/settings/ProfilesView.qml` | 完成时 `fillModel()` 并 `forceActiveFocus()` | 保留按需创建；不把旧 ProfilesView 与使用通用页的 Wedge 自定义模式混为一谈 |
| `/components/GreyBalanceTool.qml` | 完成时切换 SortedContentModel 图像过滤、可能切换目录/加载图像；析构恢复过滤及界面标志 | 完全不常驻，保留原析构清理；主机测试不创建它 |
| 媒体浏览/删除与收藏夹编辑页 | 浏览涉及内容模型/照片；收藏夹编辑有自己的模型和输入生命周期 | 不加入常驻来源；未加载媒体页，不调用照片接口；收藏夹编辑通过临时 Loader 保持关闭销毁 |
| `/components/popups/PopoverError.qml` 与错误路由 | `showFWUpdateRetryCounter >= 5` 控制隐藏重试，应急按钮受 `showEmergencyButtons` 限制 | 文件、五击路径和原按钮条件未修改；错误 1000 / 1005 / 1008 等均无常驻改动 |
| 升级、格式化、日志采集、确认/通知 Loader | 由用户动作或业务事件按需 setSource，部分会操作设备 | 不预建，保持原有来源、动作与确认流程；关闭普通页时仅销毁该页原本会随父页销毁的临时对象 |

## 构造、呈现与关闭顺序

1. 原正常界面创建 `MainScreen` 后，常驻容器以 `residentPresented: false` 构造 Menu。Menu 内的常驻容器以同样方式构造 SettingsGeneric。二者选项模型为空，输入与连接关闭。
2. 用户打开时合并当帧请求，等待相应实例就绪；调用生命周期初始化，再执行原 `onLoaded` 的模型/标签刷新和焦点逻辑。收藏夹的暂时隐藏仍由子页就绪后解除。
3. 用户关闭/切换时先断开旧页面业务连接，清理临时状态，然后隐藏原生 Loader。页面实例保留。待处理的呈现任务取消；关闭后完成的预热不会自动弹出页面。
4. 不在常驻来源中的页面交给独立原生临时 Loader；不调用 `residentActivate`，关闭仍销毁。

保留的是两棵页面主体及其静态子控件，不保留所有设置行。此取舍避免隐藏行持续订阅配置、保留旧 proxy 或重用旧确认动作；收益与内存成本需在目标机测量。该候选没有额外无线提前量、原厂动态闪光修正或 AF 算法改动。
