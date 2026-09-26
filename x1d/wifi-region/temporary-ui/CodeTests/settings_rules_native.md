# 设置规则原生候选与独立差分验证

本候选针对本仓库 `NativeSettingsPage.qml` 与 `SettingsPage.qml` 的当前自研适配规则。Qt 5.5.1 ARM 无窗口差分已通过，当前业务头文件、转换器、夹具和测试包已冻结。纯 UI 规则微基准仍比旧 QML 增加约 1.792–3.092 ms/次；不能将其写成“无性能影响”或实际触控延迟。

原厂接口来源为 X1D 1.25；规则模拟结果不表示当前相机配置、物理操作或机内界面效果。原始 QML 的 SHA-256 固定在 `settings_rules_native.py`，输入变化会拒绝构建，避免悄悄更换 oracle。

## 已迁移范围

| 规则块 | C++ 行为 |
| --- | --- |
| 设置规格 | 获取当前菜单规格；AF 与 MF 分节拼接；语言刷新后的规格与行更新 |
| 行生成 | demo/validCheck 筛选、enableCond、禁用文本隐藏、heading/toggle/choice/action/slider 分类 |
| 行内容 | Qt 原生标签翻译、原厂值显示调用、原单位抑制、toggle 说明文字、image_format 锁定后的真实值显示 |
| 特殊行 | WIFI_power 的模式、验证/忙状态、错误说明与选择器门控；EVF 三态与旧布尔值回退 |
| 编辑分派 | 按当前 entries 定位、重新检查有效/启用条件、普通 proxy 写入、动作/普通/无线/EVF 选择器分派 |
| 滑条适配 | 范围钳制、以 minimum 为原点的 step 量化、零 step 回退、pending 数值和 2000 ms 超时 |
| 滑条视图 | 拖动像素到值的映射、preview/awaiting/deadline 更新、数值回执或严格超时后的释放 |
| 列表同步 | 相同行指纹跳过 rows 赋值；已有 ListModel 行用 set 原位覆盖，必要时 append/remove，补齐默认角色 |

`settings_rules_core.h` 中的 `NativeSettingsRules` 继承 `QQmlPropertyMap`，无 moc；隐藏 context property 为 `_hblSettingsRulesCore`。业务分支与计算在 C++ 执行。`QJSValue` 用于访问原有 QML 对象/数据与调用固定 API，不运行自研 JS 源字符串、闭包或业务 eval。

## 保留的 QML

- 原厂 MenuItems 的 `validCheck` / `enableCond` 是依赖页面词法作用域的条件字符串。原有 `condition(value)` 是唯一保留的条件 eval 桥，不重写、不扩大表达式来源。
- `Settings` 的显示/单位/范围实现仍属于原厂 API。`property var nativeSettingsApi:Settings` 只暴露原对象，C++ 直接调用同对象上的原方法；每次操作仅缓存固定对象/方法句柄，不缓存动态结果。
- `MenuItems` 获取与原厂翻译刷新保留单调用薄桥。正常字符串标签在 C++ 调用 `QCoreApplication::translate("MENUS", utf8Source, "", -1)`；仅异常的非字符串标签保留 `nativeTranslate`，让原 `qsTranslate` 处理其类型错误。
- 布局、视觉属性、动画、手势/信号接线和 Timer 调度保留；`Date.now()` 仅把时钟值传入原生规则。
- 原厂 `focus_size` 网格兼容 `Connections` 未迁移。它含 `Camera.focus_point` 写入，与本规则候选的无硬件测试边界分开，不能声称整个设置文件已不含可读逻辑。
- `NativeSettingsActions.qml` 内部动作实现和原厂选择器内部实现不属于本候选，候选只保持其调用接口。

## 接入

父任务在创建 QML 前将 `new NativeSettingsRules(engine)` 注册为 `_hblSettingsRulesCore`。构建副本分别经过 `native_settings_rules.apply_native_settings_adapter(source)` 与 `apply_native_settings_page(source)`；不得直接覆盖两份原始 oracle。转换器遇到已转换输入或缺失锚点会失败。

同步请求为 `[targetQObject, operation, args]`，返回值通过同一 map 的 `result` 读取。页面操作 1/2/3/4/5/6 分别为重建、规格刷新、toggle、编辑分派、滑条选值和语言刷新；视图操作 20/21/22 分别为模型同步、拖动预览和异步回读等待解除。C++ 不拥有相机接口、文件、定时器或传输对象。

本子任务不改 `entry.cpp`、现有 QML 或构建入口；其接入、最终合包及完整发行验证由父任务处理。

## 验证方法

从 Hasselblad 根目录运行仓库已有 Python，关闭 bytecode 写入：

```text
python.exe -B x1d/wifi-region/temporary-ui/CodeTests/settings_rules_native.py --build-arm
```

所有输出仅写入 `x1d/wifi-region/temporary-ui/build/settings-rules-native/`。Python 脚本从原始/转换后的 QML 中提取相同函数和 handler，替换为相同的无窗口夹具；Qt `ListModel` 仍真实执行，原厂 Settings/MenuItems 与代理对象由模拟实现替代。代理延迟写回时保留旧值，同时记录请求数值，以验证旧回执不能让拖动回跳。

主机 Qt6 只生成并验证旧 QML oracle；`host-result.json` 的 `candidate: not_run` 不能解释为候选通过。已完成 11 个 case、1211 条逐事件记录、78 项明确断言；覆盖行类型/说明/单位、编辑后滚动数值保持、禁用条件二次校验、WIFI/EVF、语言、AF/MF 拼接、空列表、拖动期间不刷新、延迟/错误顺序回执、超时边界、负值半步量化和三组固定种子交错轨迹。

`test.tgz` 内含 Qt5.5.1 ARM `runner`、`baseline.qml`、`candidate.qml`、`events.json` 和纯模拟 singleton 的 `settings-api.qml`。入口是 `runner <directory>`，生成 `result.json`，失败时另有 `failure.json`。`build.json` 记录包/输入及源文件哈希。目标执行由父任务统一安排，本子任务没有连接 USB、启动相机接口或操作硬件。

## Qt 5.5.1 兼容修复与额外验证

- **属性类型：** 目标诊断已证明 `QObject::setProperty` 不能把 `QVariant<QJSValue>` 直接写入 typed `string` 属性，失败时会保留旧字符串。写 `var` 时保留 `QJSValue`，写 typed 属性时先转换为实际 QVariant；`lastRows` 因此正常更新。
- **QObject 包装与所有权：** `QQuickItem*` alias 不能依赖 Qt 5.5 的通用 QVariant 转换成为可访问的 QObject。对借用对象显式包装，并保留原所有权，避免 `newQObject` 改变隐式所有权。
- **GC 与模型同步：** 早期目标崩溃被固定大小诊断环定位到 `syncRows` 遍历/分配路径。Qt 5.5.1 `QJSValueIterator` 私有结构含未作为持久 GC root 保存的当前/后继属性字段；候选改为先生成 `QVariantMap` 数据快照，再分配输出对象或调用 `ListModel.set/append`。移除该遍历路径后，完整差分以及每 17 条事件强制 GC 均通过。此处记录的是定位证据和修复后的验证，不把推断写成对全部 Qt GC 行为的证明。
- **翻译：** 按本地 Qt 5.5.1 `qqmlbuiltinfunctions.cpp` 的 `GlobalExtensions::method_qsTranslate` 核对两参数调用，保留空 disambiguation 与 `n=-1`。额外安装真实 `QTranslator` 派生实例，5 条逐事件差分、13 项断言比较中/英文与 Unicode、AF/MF 标题、语言刷新、未译原文和移除翻译器后的 fallback；同时比较两边翻译器收到的参数与顺序。
- **Settings singleton：** 按 Qt 5.5.1 `qqmltypewrapper.cpp` 核对 singleton 属性访问会落到该实例的 `QObjectWrapper::getQmlProperty`。额外用 `qmlRegisterSingletonType<QObject>` 注册纯模拟服务，9 条事件逐步强制 GC，并比较状态及 API 调用顺序/参数；目标上对象与方法均有效。测试未实例化原厂 Settings 服务，也未以 Qt6 mock 通过替代 Qt5 验证。

Qt 源码证据位于仓库 `.research-cache/x1d-1.25.0/qt-public/qtdeclarative-opensource-src-5.5.1.tar.xz`，涉及 `qjsengine.cpp`、`qjsvalue.cpp`、`qjsvalueiterator.cpp`/私有头、`qqmlbuiltinfunctions.cpp`、`qqmltypewrapper.cpp`。没有改动该源码。

## 冻结结果与性能边界

当前目标结果：Qt **5.5.1**，**11 个 case / 1211 条记录 / 78 项断言**通过，强制 GC 间隔 17；翻译器 **5 / 13** 与 singleton **9 条事件**均通过。父任务验证记录显示 GUI 服务仍为 `active`，相机业务请求为 **0**。这里的零业务请求不表示没有由父任务执行测试传输。

微基准使用同一组 14 行输入，预热后各做 8 组、每组 8 次，baseline/native 的先后顺序交替。默认编译未定义诊断 trace；没有在计时阶段写诊断环。计时器是 `QElapsedTimer`，以下均为墙钟耗时，不是线程 CPU 时间。

| 输入情况 | 旧 QML 平均 | 原生平均 | 增加 | 原生/旧 QML |
| --- | ---: | ---: | ---: | ---: |
| rows 不变，跳过模型更新 | 8.118 ms | 9.910 ms | 1.792 ms | 1.221× |
| rows 改变，包含模型同步 | 10.949 ms | 14.041 ms | 3.092 ms | 1.282× |

8 组中“每次调用的组内平均值”范围：原生 sameRows 为 **9.698–10.080 ms**，changedRows 为 **13.504–15.062 ms**。这些范围不是单次调用的最坏延迟，也不是触控/渲染帧时间。

页面 Timer 的条件仍是 `visible && presented`、间隔 250 ms；`adjusting` 为真时，`rebuild` 在行生成前返回。若按非拖动可见页每秒 4 次定时刷新折算，平均增加约 **7.169 ms/s** 或 **12.367 ms/s** 墙钟占用，分别为每秒 **0.717 / 1.237 个占用百分点**。此折算不包含用户操作/语言刷新等额外触发，不能标为实测 CPU 百分比；拖动数值路径和真实画面帧率也未由此微基准测量。

保留的开销包括逐行动态条件与代理读取、Settings 调用、Qt/QML 值封送、JSON 指纹和发生变化时的原位模型同步。已减少固定桥层和重复分配；为了继续保留动态条件、代理副作用和语言行为，本轮没有跨操作缓存条件、代理值或自定义说明文字。

证据均在 `../build/settings-rules-native/`：

- `validation.json`：父任务保存的目标通过结果、GUI 状态、业务请求数及源/包哈希绑定。
- `target-result.json`：runner 原始差分、额外测试与 8 组计时数据；`run.json` 记录目标退出码和分发构建。
- `build.json`：本地冻结输入、源码和产物哈希。`executed:false` 是构建当时状态，目标执行状态以 `validation.json` 为准。
- `host-result.json`：Qt6 旧 QML oracle 验证；不能单独证明候选通过。
- `fallback-optimized-r1/`、`fallback-optimized-r2/`：此前已通过的源码、包和结果快照，未覆盖。

冻结测试包 SHA-256：`84049e3dbc931aadfce758c0e62b42ab8a80375d16123bee2e396f1085d1ae2f`。本说明更新后没有重建测试包或变更业务源码；后续生产接入与合包由父任务处理。

无窗口规则差分可验证模型原位更新及 scroll 状态不被业务代码重置，不能替代真实 ListView 手势、渲染位置、动画、帧时延或相机异步总线联调。当前完整设置文件仍含上文列出的原厂条件桥、兼容 hook 和显示接线；不能声称整页已经没有可读逻辑。
