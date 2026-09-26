# 原厂菜单接入的离线常驻容器

这是分阶段候选。用户已在原厂菜单确认“引闪”入口及点击进入；开机配置已写入并回读一致，冷启动、返回与半按退出仍待验收，详见 [实机记录](DEVICE-RESULT.md)。

`ResidentFlashHost.qml` 直接持有已有 `FlashPage`，默认隐藏，返回仅隐藏而不销毁。Bootstrap 已在临时原厂进程中接入模型和页面路由；开机配置已安装，尚待完整关机开机确认自动应用。组件未连接任何无线、相机或镜头操作。

在项目根目录运行桌面验证：

```powershell
py -3.11 -B x2d/CodeTests/temporary_af_speed_probe/original-menu-candidate/check_resident_flash_host.py
```

最终通过 100 次往返的同一实例检查、真实键盘嵌套返回、菜单退出及忙状态检查。测试使用现有本地 Qt，界面在 offscreen 后端运行；不表示原厂集成或机内性能已验证。首次绘制与内存开销也未测量。

完整固件依据见上级目录 `ORIGINAL-MENU-INTEGRATION-AUDIT.md`。

## 第十二格候选与验证范围

`FlashMenuModel.qml` 用 `DelegateModel` 包装原模型，在显示模型末尾加入一个未解析项。原模型本身仍为十一项，原来的角色更新继续传递。原厂网格除了读角色，还调用 `itemEnabled(index)`，适配层保留该方法。只接受十一项和四列布局；数量变化、布局不符或名称冲突时撤下扩展，避免覆盖原项目。角色变化导致的名称冲突也会重新检查。

`FlashMenuRoute.qml` 将扩展标识路由到常驻引闪页，原项目的名称和参数原样传出。它只是候选路由器，不是已装入原厂进程的拦截器。实机接入时必须在原厂查找子菜单之前分派，不能仅监听点击信号后仍让原厂处理未知名称。

```powershell
py -3.11 -B x2d/CodeTests/temporary_af_speed_probe/original-menu-candidate/check_flash_menu_model.py
python -B x2d/CodeTests/temporary_af_speed_probe/original-menu-candidate/prepare_stock_grid_fixture.py
py -3.11 -B x2d/CodeTests/temporary_af_speed_probe/original-menu-candidate/check_stock_grid.py
```

第二组验证从固定官方 4.2.0 提取十份资源到被忽略的 `.stock-host/`，记录哈希，直接执行未改写的 `MainScreen.qml`、原厂网格、导航和图标按钮组件。适配器使用原网格的 `delegate`；测试没有重做网格。已通过：

- 十一个原项目的实际鼠标点击仍发送各自名称；新增第十二项能用鼠标和键盘打开引闪页。
- 原厂不可选项的导航跳过、EVF 禁用触控、子菜单已打开时的重复点击门控仍生效。
- 引闪页二十次实际点击与 Escape 返回使用同一个实例；模型测试另通过一百次路由往返。
- 原模型保持十一项，稀疏三列布局撤下扩展，无 Qt QML 警告。

结果见 `model-validation.json` 与 `stock-grid-validation.json`。**这仍是桌面验证，不是实机部署。** `FavoriteModel`、主菜单状态与物理键码映射为替身；图像着色器换成几何占位组件，因此没有验证视觉一致性、机内性能、真正的半按快门或服务通信。

## 原厂进程接入与待验收范围

Bootstrap 在原厂 QML 引擎中创建扩展，保留原 delegate 的上下文，再将主菜单视图模型的显示模型指向适配层；同时接入原厂子页面分派与返回状态。实机入口与打开已确认，返回和拍照退出尚待验收。桌面脚本里的 `MainMenu` 替身不用于机内。

原厂可执行文件无需包含新按钮：在每次开机首次 GUI 启动时构造运行时扩展。持久保存的是扩展资源和加载配置，不能保存或复用上一次的内存地址。同次开机再次启动 GUI 时跳过扩展，避免失败后反复挂接。状态以实机记录为准。

`build_bootstrap_unit.py` 保留原字节码与函数索引，只追加 Loader 对象和其绑定。`host_cached_unit.py` 与 `host_cache_bridge.c` 是 Windows 桌面验证辅助，不能部署相机。`check_bootstrap_attach.py --packaged` 验证打包后的文件名、实际编译单元加载、自动挂接与撤回。

Qt 结构参考：[Qt 6.4.1 缓存单元注册定义](https://github.com/qt/qtdeclarative/blob/v6.4.1/src/qml/qml/qqmlprivate.h)。实机模块使用已绑定版本的原缓存结构，不向相机部署桌面回调桥。
