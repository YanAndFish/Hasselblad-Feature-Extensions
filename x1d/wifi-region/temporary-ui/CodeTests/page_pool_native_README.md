# PagePool 原生迁移交接

本候选只处理 X1D 页面缓存、选中、准备状态、一次投递与临时页面释放。冻结基线为 `temporary-ui/PagePool.qml`，SHA-256：`f492f585d872ba8130b68461c4ce36acd65d037590074b967e461cc36b58fd59`。编译使用本项目离线缓存的 X1D 1.25.0 库与 Qt 5.5.1 公开头文件，不把 X2D 4.2.0 结论套入本实现。

## 接入

- 在 `entry.cpp` 包含 `page_pool_core.h`，在载入相关 QML 前安装：`engine->rootContext()->setContextProperty("_hblPagePoolCore", new NativePagePoolCore(engine));`。
- 资源生成时调用 `native_page_pool.apply_native_page_pool(original_source)`，把返回文本写入原来的 `PagePool.qml` 资源路径。适配器核对固定基线，拒绝未知或已经转换的输入。
- 每个 QML 池仍保持 `active`、`asynchronous`、`slots`、`selected`、`delivered`、`item`、`status` 及原有方法、信号接口。`slots` 中的对象仍是真实 Loader，原主菜单的标题更新和身份比较可继续工作。
- `_createSlot`、`_setSource`、原有公共属性与信号，以及页面的 `residentPrepare`、`residentDeactivate`，是 C++/QML 交界名称，资源处理不能单边改名。
- 本子任务没有修改 `entry.cpp`、`build.py`、`build_flash_preview.py` 或冻结的 `PagePool.qml`。主任务负责最终 context 接线、合包和成品验证。

## 责任与生命周期

`NativePagePoolCore` 是无 moc 的 `QQmlPropertyMap` 入口，每个 host 对应独立的 C++ `Pool`。C++ 持有缓存键、保留标记、选中项、准备成功/失败、投递代次和原生零延时 `QTimer`；没有把 JavaScript 函数或闭包字符串放入 `eval`，也没有持有用于业务状态的 JS 回调。

薄 QML 保留 FocusScope、Loader 布局、原有 item/status 输出绑定，以及固定参数转发。真实 Loader 在设置 source 前已经登记到 native 缓存，因此同步 `onLoaded` 也能找到条目。初始 properties 对象原样传给 Loader，保持 `Component.onCompleted` 前应用初始值的语义。

准备过程对同一个实际页面依次调用 `residentPrepare → residentDeactivate`。前一步抛错则不执行后一步；任一步失败都阻止成功投递。公开 `loaded` 直接传 Loader 的对象，不依赖 Qt5 上可能尚未更新的 `item` 绑定。活动与选中改变会更新投递代次；回调返回后不会覆盖新的选中或展示状态。

Loader 的 `closeMenu()`、`closeMainScreen()` 留在原 factory 的词法作用域，继续转发 `backRequested`、`controlRequested`，兼容原厂特殊页面的非限定调用。native 调用的只是公开 Qt/QML 接口；无 private Qt ABI。

对象存活由 `QPointer` 检查；池/条目回调使用 Qt `QSharedPointer/QWeakPointer`，避免引入 Zig libc++ shared_ptr 与机上 libstdc++ 的 ABI 依赖。退出或切走非保留页面时，先从缓存与投递资格中移除，再 `deleteLater()`，不在点击或 `onLoaded` 栈内同步删除对象。旧条目的迟到事件不能访问同键新实例。host 销毁后原生定时器停止、池被注销；销毁过程中迟到的 QML 桥通知不能重新注册池。

## 明确改变的 9 个边缘行为

以下单独作为修复用例，未计入严格等价比较。夹具同时断言旧基线缺陷和候选结果。

| 用例 | 旧基线 | 候选 |
|---|---|---|
| `repair-preparation-failure-reopen` | 异步准备失败后，重开已 Ready 对象仍能投递成功 | 保留失败状态，重开继续失败并解除菜单打开状态 |
| `repair-synchronous-preparation-failure` | 同步准备失败发生在 selected 设置前，会丢失失败并投递成功 | 先登记条目并记录失败，选中/激活后报告失败 |
| `repair-deactivation-failure-reopen` | 准备阶段 deactivate 失败后，重开可能投递成功 | 保留该失败，阻止后续成功投递 |
| `repair-switch-already-ready` | active 中改选已准备页面不会重置 delivered 或调度 | 每次实际选中变化建立新的一次投递 |
| `repair-switch-transient-release-late-loaded` | 切走 keep=false 页面后隐藏缓存仍保留，迟到 loaded 再执行准备 | 移除并延迟释放隐藏临时页；忽略已退出条目的 loaded |
| `repair-loaded-callback-selects-ready` | loaded 回调直接修改 selected 后，新的已准备页不投递 | 原生选中监听正确安排新页面投递 |
| `repair-prepare-callback-selects-ready` | 准备回调改选已准备页时可能没有下一次 dispatch，菜单仍 opening | 在选中变更时重新调度，回调后的旧页不能夺回投递 |
| `repair-duplicate-onloaded` | 同一对象重复 loaded 会再次执行 prepare/deactivate | 每个实际对象准备一次，重复 loaded 不重做生命周期 |
| `repair-selected-loader-destruction` | 选中 Loader 被外部销毁后可能留下活动中的空页 | 清除条目并报告失败，菜单可继续打开其他页面 |

原有正常路径另外严格比较同步/异步装载、预热、重复 show、保留实例重开、同 key 忽略新 URL/properties/keep、非保留页隐藏释放、原 factory 返回函数、载入/激活失败后再次导航、回调隐藏/重新激活，以及装载中和回调内销毁 host。prepare 中的销毁用例先撤销 active，再发出 QML 的延迟 destroy；不会把发出 destroy 请求误认为 QObject 已经销毁。

## 验证与证据

构建命令（从仓库根目录）：

```powershell
py -3.14 -B x1d/wifi-region/temporary-ui/CodeTests/page_pool_native_regression.py --build-arm
```

生成物都位于 `temporary-ui/build/page-pool-native/`。`test.tgz` 包含独立 `runner`、冻结基线、候选、两个 Harness、Dummy 和 events。`build.json` 绑定目标、输入源码与包内文件 SHA-256。获授权执行环境的命令为 `./runner <解包目录的绝对路径>`，输出 `result.json`、`trace.jsonl`；失败另有 `failure.json`。构建脚本不上传、不连接或操作设备。

主任务执行的真实 Qt 5.5.1 纯 UI 夹具已经通过，主任务保存的 [validation.json](../build/page-pool-native/validation.json) 绑定该次源码与产物：

- 23 cases，136 records。
- 84 次严格状态比较，207 条明确断言。
- 9 个单列的行为修复用例，23 次 host 销毁后原生池清理检查。
- `cameraRequests=0`；不创建窗口，不实例化相机对象、照片 provider、D-Bus 或传输层。

第一次目标执行停在基线与候选共有的 status 绑定重入 warning；当前 `target-result.json` 与 `validation.json` 已记录第二轮通过结果。第二轮 runner 只准入以下已知警告，并完整写入 `allowlistedWarnings`：

1. `source-failure-unlocks-next-page` 的 event 1 中，固定缺失材料 `Missing.qml` 的加载错误。
2. 同一 case/event 中，`BaselineHarness.qml` 或 `CandidateHarness.qml` 的 71:9，精确文本分别为 `QML BaselinePool: Binding loop detected for property "status"` 和 `QML CandidatePool: Binding loop detected for property "status"`。

第二条源于保留的 `onStatusChanged` 在 Error 时立即设置 `active=false`，两版行为一致，后续正常页可打开；本迁移没有改写该原有输出绑定。其他用例、位置、属性或文本的 warning 均失败，未使用宽泛忽略。

`--host-oracle` 另在 Windows Qt 6.11.2 上检查旧基线的 23 cases / 136 records / 98 条期望，退出码 0。宿主使用 `QQmlApplicationEngine` 管理内部组件，规避本地 PySide6/CPython 3.14 暴露的 `QQmlComponent` 析构崩溃，并仍显式销毁 root/engine。这份结果只证明旧基线材料与期望匹配，不能替代实际候选的 Qt5 检查。

这些测试覆盖 Loader 与业务生命周期，没有验证最终合包 GUI、实际原厂页面画面/动画、物理触控时延或 RAW 回放/取景性能。本候选不接触这些通路；成品与性能保持由主任务继续验证。
