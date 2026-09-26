# X1D 普通 UI 常驻候选

格式化入口回归已有 [独立最小修复包](FORMAT_FIX_HANDOFF.md)：175 项离线检查通过，尚未安装。只修正 `text2` 角色初始化，旧安装包保持不变。

最新目标状态：2026-09-13 主任务已成功安装原厂 GUI 专用 `a8` 包，四资源、四组件及健康检查通过；实际菜单体验与性能待用户确认。见 [安装回执](INSTALLATION_A8_20260913.md)。本页下文保留最初候选与离线验证的历史说明。

独立会话装载入口见 [装载包与阶段命令](session/README.md)：固定使用修正版 `0456d37b...` RCC，只作用于原厂 GUI，包含前置检查、四组件检查和失败恢复。设备仍由主任务独占；目标验收状态以下述说明为准。

已安装 AF r3 且已应用固定 GUI r4 修复时，使用另行交付的 [AF r4 共存包](AF_SESSION_HANDOFF.md)。该包保留 AF 配置与逻辑，97 项离线检查通过；目标加载与交互仍待主任务验证。

已实现 **一个可复用的主菜单实例和一个可复用的通用设置页面实例**：正常 `MainScreen` 创建后异步预建，关闭时仍保留，下一次打开刷新模型、标题和焦点。CAMERA / GENERAL / VIDEO 共用前者，各个 `SettingsGeneric` 设置列表共用后者。选项行进入时重建；没有为每个设置名称各建一份控件树。

状态：**主任务首次目标 Qt 5.5 编译检查发现旧 Loader id 使用保留字，旧包停止使用；已作最小重命名修正，新包待主任务重新验证。** 原 91 项为主机 Qt 6 离线检查，未覆盖此兼容错误，不能用作目标通过证明；详情见 [Qt 5.5 修正](QT55_FIX.md)。这不是全部页面常驻的声明。生命周期例外见 [审计矩阵](LIFECYCLE.md)。

## 来源与边界

来源固定为 X1D 1.25.0 原包 `usr/bin/victory-gui`，SHA-256：`d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`。原 QRC 文本由本项目 `x1d/tools/binary.py` 离线提取；不推定当前相机正在运行此版本。

本轮所有输出只在 `x1d/candidates/ui-resident/`。相机、USB、无线、照片请求均为 0；没有修改引闪、AF、回放、冻结候选、Git 历史或远端。错误 1000 / 1005 / 1008 等页面、遮罩、错误路由和恢复资源均不在补丁写入范围。

## 行为

- `ResidentLoader` 将对外 `active` 解释为“本次页面呈现”。内部原生 `Loader.active` 保持为 `true`，真正的页面对象持续存在。
- 构造参数直接设 `residentPresented: false`；预热时不运行 `onLoaded` 里的进入页面动作。原 `SettingsGeneric` 临时预加载后清空 `source` 的块已移除。
- 打开请求在一个事件循环内合并。关闭取消未呈现的请求，快速切换只交付最后一组参数；同一种页面已经打开时也能刷新新列表。
- 关闭先断开页面业务 `Connections`，再停菜单计时器、关闭下拉框/临时弹窗、清理选项行与选择状态。`FocusSizeChanged` 写回 `Camera.focus_point` 的原处理器仅在设置页呈现时连接。
- 非白名单来源使用原生临时 `Loader`。`DateTime`、`SpiritLevelView`、`ProfilesView`、`GreyBalanceTool` 和收藏夹编辑等仍按需创建、关闭销毁；内部确认/维护弹窗也按需加载。
- `versionID → wantToSeeFWUpdateRetryClicked()`、Service 隐藏通知、`fwUpdateRetry → GenericConfirm → Upgrader.upgradeNodes()` 的原动作保留。`PopoverError` 感叹号五击应急/重试入口的资源未修改。

Qt 5.5 没有 `Connections.enabled`，本候选以 `target: ... ? 原对象 : null` 断开连接。官方文档说明 `enabled` 从 Qt 5.7 才引入，`target: null` 会停止连接：[Qt Connections 文档](https://doc.qt.io/archives/qt-5.15/qml-qtqml-connections.html)。

## 构建与组合

从 Hasselblad 工作区根目录执行：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/tools/build.py
```

输出位于 `build/overlay/`：

| 资源 | 作用 |
| --- | --- |
| `mainmenu/MainScreen.qml` | 接入主菜单常驻容器，移除旧编译缓存预加载块 |
| `mainmenu/Menu.qml` | 通用页常驻容器、进入刷新和关闭清理 |
| `settings/SettingsGeneric.qml` | 页面生命周期与连接门控 |
| `mainmenu/ResidentLoader.qml` | 常驻/临时加载的呈现调度 |
| `changes.patch` / `manifest.json` | 可审阅差异、输入与输出哈希 |
| `ui-resident.rcc` | 仅以上四项资源，Qt RCC v1 格式 |

**协调方应对最新资源组合补丁，不能用基线生成的整文件覆盖同一文件中的新修改。** 此目录从不输出 `main.qml`。若协调方维护资源字典，可导入 `tools/build.py` 的纯函数 `compose(resources)`：它保留输入的 `main.qml` 和其他资源，只补丁三文件并增加 `ResidentLoader.qml`；未提供的三个原厂文本取固定 1.25.0 基线。函数不会写回输入字典。

若最新资源已导出到本工作区的目录，可传 `--input-dir <最新资源目录>` 和 `--output x1d/candidates/ui-resident/build/composed`。输入目录只读，缺失的三个原厂文件取固定基线；输出仍只有四资源。工具拒绝重复应用、关键锚点缺失/重复、输出越界或写回输入目录。新增连接按原厂 target/handler 组合定位，不批量改写其他候选追加的 `Connections`。

`ui-resident.rcc` 是候选资源包，不包含加载/安装脚本。组合后的单一资源包、其他候选新增控件的构造副作用和最终资源注册顺序仍需协调方共同审核、联调。

## 验证

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_resident.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_original_pages.py
```

本机复用只读的 `x1d/wireless-flash/build/ui-test-python/PySide6`，Qt **6.11.2**，offscreen/software 模式，禁用 QML 磁盘缓存。没有加载固件业务插件或设备客户端。

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 实际常驻容器、实例身份、输入隔离、请求竞争、信号计数、组合保护、RCC 注册与逐字回读 | 59 项通过 | [validation.json](build/validation.json) |
| 原厂 Menu / SettingsGeneric / 子控件，与原 MainScreen 加载器和滑动区域组合 | 32 项通过 | [original-pages-validation.json](build/original-pages-validation.json) |

第二组保留实际页面行为，业务插件、菜单数据和按键映射采用显式替身；只在测试副本中转换 QRC URL、替代旧图形效果和少量图标。覆盖预建唯一实例、后台事件静默、参数刷新、分节清理、焦点、返回键、收藏夹直达、同页切换、About 进入动作、隐藏版本入口、确认后单次重试、提示计时器、两级右滑和对象复用。两个“升级”计数只是主机替身动作。

Qt 6 对原厂旧式 `Connections` 的弃用提示单列记录，其他 QML 错误使测试失败。目标 Qt 5.5 的定制 Flickable、嵌入式输入、原生单例初始化副作用、启动资源占用与性能变化未由上述主机检查验证，仍是实机联调缺口。
