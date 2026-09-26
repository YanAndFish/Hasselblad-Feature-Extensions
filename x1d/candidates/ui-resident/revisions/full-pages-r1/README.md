# 全普通页常驻 UI 独立候选 full-pages-r1

状态：离线实现、构建、回归和归档审计通过；独立测试包已冻结。尚未暂存、装载或在相机上验收。本轮设备请求为 0。

候选只适用于摘要固定的 X1D 1.25.0 `victory-gui`，GUI SHA-256 为 `d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`。旧 a8、card-format-r1 包及其记录保持原样。该目录是新的独立候选，不能把过去版本的暂存、安装或 ready 当成本版结果。

## 本版行为

- 3 个菜单按类别分别保留，共 23 个普通 `SettingsGeneric` 页按名称分别保留，关闭后隐藏；菜单模型及行控件增量更新。
- 仅 `System.StateUp` 时顺序预热。隐藏预热不调用相机业务方法；实际进入 About 页时仍按原厂路径请求镜头信息。
- 格式化对话框继续临时创建并保留原厂处理；`text2` 空角色修正沿用。确认对话框记录当前拥有者，取消的保存配置/固件重试不得收到其他对话框的确认事件。
- Slider 的原生写入限定于可见、启用的用户编辑；后端更新继续通过原来的 value 绑定显示。语言、隐藏项及镜头版本过滤按当前值刷新。
- 特殊工具和 Profiles/FavoriteAdd 路由继续临时装载。宿主测试中的这几条路由使用明确替身，不能据此宣称真实特殊工具已验收。

覆盖 6 个资源：`mainmenu/MainScreen.qml`、`mainmenu/Menu.qml`、`mainmenu/ResidentLoader.qml`、`settings/SettingsGeneric.qml`、`settings/components/SettingSlider.qml`、`settings/scripts/MenuItemImporter.js`。实际路径以 [资源清单](build/resources/manifest.json) 为准。

## 启动就绪门槛

原厂 `main.qml` 创建一个 TouchWindow 和一个 EVFWindow；TouchWindow 只有一处 `guiconfig.mainMenuName` 装载点，EVFWindow 不另建主菜单。原厂三个布局资源的摘要记录在资源清单 `layoutProof`，因此门槛按唯一一套主菜单计数。

仍保留 6 个有效资源摘要验证和 5 个 QML Component 编译状态检查。成功标记进一步要求遍历已经存在的 QObject、QQuickItem 和 QQuickWindow 对象树，看到：

1. 一个 `MainScreen_root`、一个顶层池、三个子页池。
2. 无重复或意外 key 的 3 个 Menu 与固定目录中的 23 个 Generic 页；各原生 Loader 为 Ready，页面 `residentPrepared` 为真。
3. 每个 ListView 的实际行控件数量等于当时的模型 count；普通页的每个行 Loader 也为 Ready。动态过滤后的行数现场读取，不把宿主的 99 行硬编码为相机要求。
4. 以上状态连续 3 次采样完整，采样间隔 200 ms。该间隔属于策略参数，不是目标机性能或计时精度实测。

单池 Loader.Error、异常重复实例或相关 QML warning 判为失败；单调时钟达到 30 秒仍不完整则超时。检查不创建额外业务页面，也不发业务调用。生产 ARM 收集器已编译；宿主对象树测试使用明确的 Python 等价收集器，共用 C++ 策略单独执行。目标 Qt5.5 收集器的实机运行仍待验证。

最终成功标记为 `ui-resident-ready-resources6-components5-pools3-pages23-rows pid=<当前GUI PID>`。安装前要求原厂 System2/Power0；不主动唤醒待机设备。安装最多等待 40 次一秒轮询；明确失败立即恢复。原厂恢复检查仍接受正常待机，保持原来的 10 次轮询。

## 离线证据

| 验证 | 结果及边界 |
| --- | --- |
| [QML 功能回归](build/qml-validation.json) | 194 项；23 页重复进出及实例身份、滑块、过滤、语言、格式化取消和确认拥有者等；原生方法为内存替身 |
| [异步竞态](build/race-validation.json) | 11 项；关闭后晚到、临时页销毁、加载错误及继续导航 |
| [真实池就绪观测与策略](build/readiness-validation.json) | 10 项；实际宿主行控件、真实单池错误、延迟、永不完成、稳定性重置、截止优先 |
| [Qt5.5 标识符](build/qt55-identifiers.json) | 86 个 id 通过原版关键词分类器；不是完整目标 QML 编译 |
| [ARM 构建](build/session/native/build.json) | ARM32，链接固定 Qt5.5.1 库，重定位连续；目标执行未验收 |
| [事务脚本](build/session/install-validation.json) | 31 项；实际 shell 路径映射，服务/PID/健康/UID 为替身；含加载错误、超时、永久 pending 自动恢复及待机前检拒绝 |
| [传输算法](build/session/transfer-validation.json) | 12 项；离线 231 字节帧边界、全字节解码、重复及未知结果拒绝 |
| [最终实际归档](build/session/package-validation.json) | 26 项；实际 Qt RCC 读取、9 成员、13 项基线、ARM hooks、归档摘要与经典解码往返 |

## 内存测量

[五组配对结果](build/memory-summary.json) 使用 Windows64 / Qt5.15.2 / 软件离屏渲染、相同原厂资源及原生替身，对比 card-format-r1 与本候选。两版均遍历相同 23 页后关闭菜单，保留各自编译及图片缓存。

本候选的私有提交增量中位数为 **17.42 MiB**，工作集增量中位数为 **17.37 MiB**。本候选保留 23 页、99 个功能行和 26 个菜单行；上一版关闭后保留一套 Menu/Generic。各组没有非预期 QML warning。

这是已实现候选的宿主比较，不能转换成相机可用内存、流畅度或精确成本。ARM 就绪库未加载到宿主测量进程，特殊工具仍为路由替身；LCD/EVF 实机显示、预热耗时及相机内存余量待独立测试。

## 冻结交付物

- [包与绑定报告](build/session/packages/f2d398f8ea39b41b/package.json)
- [独立测试包](build/session/packages/f2d398f8ea39b41b/ui-full-pages-session.tar.gz)，56,110 字节。
- 包 SHA-256：`f2d398f8ea39b41b8dd0354a243844b750a18868f832167501d2154cc48a259d`。
- RCC SHA-256：`1c794a21fe7f61a4bdab50f40b5eb02bc428fcd584e9ed2d9d8119c97223b551`。
- 注册库 SHA-256：`72c0908eaf7f7d6a4ff770b8b327fe45ab11fcf04b220e740348e0c5c7d74181`。
- 独立远端目录预定为 `/tmp/hbl-ui-full-r1`。当前未访问该目录或向相机发送本包。

在仓库根执行 `python x1d/candidates/ui-resident/revisions/full-pages-r1/delivery.py` 仅离线核验绑定。设备阶段由主任务取得新一轮独占窗口、确认这一精确包和原厂干净基线后单独安排。旧 ready 因重启和其他模块测试已失效；本目录不能接替主任务自行安装、清理或叠加其他候选。

本包不含其他模块，也没有持久自启。后续合包约束见 [INTEGRATION_CONTRACT.md](INTEGRATION_CONTRACT.md)。
