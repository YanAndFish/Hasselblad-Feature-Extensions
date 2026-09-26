# 常驻 UI 装载交接

最新独立原厂 GUI 装载包及实际入口见 [session/README.md](session/README.md)。该包固定使用 `0456d37b...` 修正版，具备单库资源注册、前置检查、四组件就绪检查、临时 drop-in 与失败恢复；下文旧组合交接保留为历史证据。

> **旧包已撤销可用状态。** 主任务首次目标 Qt 5.5 检查报告 `ResidentLoader.qml:19:67 Expected token numeric literal`，原因是旧 `transient` id 命中 Qt 5.5 保留字。下文 `589913...` 固定副本只作失败取证；最新最小修正与哈希见 [Qt 5.5 修正](QT55_FIX.md)。不得再装载旧包。

本轮结论：**固定候选已核对，可交主任务合成最终包并进入受控目标机验证。** 没有发现需要先改动本模块的已知失败项；尚未生成的引闪 / AF / 回放 / UI 最终组合包不在本次核准对象内。目标 Qt 5.5 尚未验收通过。本任务不连接 USB、不装载、不重启服务。

## 固定交付

固定目录：`build/fixed/ui-resident-589913e798229625/`。该目录按内容固定，重复建立只允许内容完全一致。`audit-source/` 是审计副本；组合接口仍使用工作目录内、下列哈希对应的 `tools/build.py`，不要把审计副本当成独立工程执行。

| 对象 | SHA-256 |
| --- | --- |
| `ui-resident.rcc`，RCC v1，25176 bytes | `589913e7982296250ae19d3d1ed7bf7af33789e7e258617c5c4681a3b2af9888` |
| 固定目录 `release.json` | `163109e1c0d2277e76fb5b79e81997d47888ca05f5226f2e5673e77dcf71a1ec` |
| 工作目录 `tools/build.py` | `915fdf996a40dc88a319c431a5b0402b9d37e2598de09470624e45d829002753` |
| 固定目录 `reports/validation.json`，59 项 | `117fc39b0173b8ea838eb5bde417b0515d64be704c70e6df3cdc55f30cfe5435` |
| 固定目录 `reports/original-pages-validation.json`，32 项 | `2da3618545263a213e76320bd9cd5795bf7959831426691f2439ebe0e08efcf6` |

两份报告均为 Qt 6.11.2 离线测试，其记录的工具、QML、测试源文件哈希已重新核对一致。此轮没有源码变化，因此没有把旧测试重新包装为 Qt 5.5 或装机测试。完整文件清单、审计副本、差异和哈希保存在固定目录 `release.json`；三项原厂输入绑定 X1D 1.25.0 原 `victory-gui`：`d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`。

## 四资源输入 / 输出哈希

这些是本次固定基线包的哈希。与主任务最新资源组合后，三项输入或输出如发生变化，必须另存最终清单，不能继续沿用本表作为最终包证明。文本哈希按 `compose` 使用的 UTF-8 字符串计算；CLI 读取文本时会规范化换行。

| QRC 路径 | 输入 SHA-256 | 输出 SHA-256 |
| --- | --- | --- |
| `/mainmenu/MainScreen.qml` | `b62c52a46f421af0d193b68444b7e0106ca62a3826d3451496a5b024e385f11a` | `552d546a679071669eb67b7cb02f4424c3c56ed020beaa00244bc7ae5f435433` |
| `/mainmenu/Menu.qml` | `354dd875a554103021f01d7d0ae1c9bf603fb604af8dcec911cb4c507ae33043` | `593344a502e333f24abefd30d28cac040c9c1b5d5be31814cb34292fd54c7961` |
| `/settings/SettingsGeneric.qml` | `de939714c79095a9075590234714114561ae6079319bfa922ea6ecb97c883c2a` | `fc6b8208c358dcdb685eda00d92d974e7219e801c4cac89c1ffb79be968f8955` |
| `/mainmenu/ResidentLoader.qml` | 新增；清单用空文本哈希 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `81c4ad1a560b87e2b28f416e553ec83a097185581482706c2ff7328758abd067` |

## 安全组合顺序

1. 主任务先完成 ISO、文字/图标、参数页左滑和原厂电池图标修改，冻结正式引闪 + AF + 回放的资源字典与来源哈希。使用**正式构建器的资源字典**，不要递归收集 `qml/` 目录：当前该目录还包含 `FormalRuntimeHarness.qml` 等测试内容。
2. 在全部其他候选组合之后调用本模块 `compose(resources)`。接口为 `dict[str, str] → dict[str, str]`，路径以 `/` 开头，值为 QRC 文本；保留所有非目标资源。输入缺失的三份原厂页面会取固定 1.25.0 基线，所以正式构建器必须已经提供这些页面的所有现有覆盖修改。重复常驻补丁、连接锚点冲突会拒绝，不能强行略过错误。
3. 核对 `main.qml`、`controlscreen/ControlScreen.qml`、引闪接线、回放与其他所有非四目标路径逐字未变。另审三文件差异，尤其其他候选追加的 `onItemValuesChanged`、临时面板和生命周期回调；保留文字不等于共同运行已经验证。
4. 用主任务已有构建器生成**一个最终资源包**，记录完整输入资源、输出资源和包哈希。不要依赖多个重名 RCC 的注册先后覆盖。注册发生在 QML 页面首次解析/创建之前；已创建或已缓存的页面不会因新增 RCC 自动替换。本任务不执行为应用最终资源所需的任何 GUI 重载。

主任务通常已有名为 `build` 的模块，应以唯一名称导入：

```python
from pathlib import Path
import hashlib
import importlib.util
import sys

tool_dir = Path("x1d/candidates/ui-resident/tools").resolve()
entry = tool_dir / "build.py"
assert hashlib.sha256(entry.read_bytes()).hexdigest() == "915fdf996a40dc88a319c431a5b0402b9d37e2598de09470624e45d829002753"
sys.dont_write_bytecode = True
saved_path = list(sys.path)
try:
    sys.path.insert(0, str(tool_dir))
    spec = importlib.util.spec_from_file_location("hbl_resident_ui_fixed", entry)
    resident = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resident)
finally:
    sys.path[:] = saved_path

# resources 必须是主任务已经冻结的正式资源字典。
before = dict(resources)
combined = resident.compose(resources)
touched = set(resident.PATHS) | {"/mainmenu/ResidentLoader.qml"}
assert resources == before
assert all(combined[key] == value for key, value in before.items() if key not in touched)
assert set(combined) - set(before) <= touched
# 由主任务的正式构建器消费 combined；此示例不写文件、不装载。
```

## 目标 Qt 5.5 需要验收的实际组件

| 层次 | 实際对象 / 依赖 | 目标验收 |
| --- | --- | --- |
| 资源与创建时序 | RCC v1、`MainScreen`、两个 `ResidentLoader`、Menu、SettingsGeneric | 没有 type unavailable、未知属性、QRC 路径或 binding 错误；正常 UI 出现后两个页面预建，菜单未自动弹出 |
| Qt Quick 基础行为 | QtQuick 2.0 的 Loader / FocusScope / Timer / Connections；`setSource` 初始属性、异步就绪、target=null | 关闭不抢输入，预热过程中打开又关闭不弹回；快速切换不重放旧参数；目标端确认对象实际复用 |
| 原厂图形/输入扩展 | QtGraphicalEffects 1.0、BoundsEffectGradient、定制 `Flickable.CustomBounds`、实体键与原厂 Keys.js | 普通滚动、上下边缘、长列表、分节、返回键和两级右滑；主机测试替代了这些扩展中的一部分 |
| 原生业务对象 | config、settings、camera、cambody、bodysync、suc、lens、storage、systemmanager、upgrade、video、globalstateinfo 的原插件/单例 | 预建不引入额外动作；关闭设置页不额外响应 FocusSizeChanged 写焦点；进入 About 才运行原版本读取；不为测试启用新调试接口 |
| 内部弹窗 | ListSelectorSettings、GenericInform、原 subDialog / confirmDialog Loader | 关闭时无旧弹窗/旧计时器；重进选项正确；临时页仍关闭销毁 |
| 联合界面 | 主任务最新 ControlScreen、引闪面板、AF 观察、回放 | 参数页全区域左滑、ISO、文字/图标、电池、回放进出、实体键焦点都沿用联合包检查；不能只看本模块单独的 91 项结果 |
| 维护与错误 | About 隐藏入口、Service 通知、fwUpdateRetry、PopoverError 五击与原错误路由 | 先做资源差异证明；实机如检查入口，只到显示/取消确认，**不为验收执行升级、格式化或故意制造错误** |

## 主任务需配合的具体项

- 给出最终正式资源输入或目录、生产资源清单及冻结哈希；此时才能确认“最终组合包”，当前仍在修改的引闪文件不算固定输入。
- 确认当前实机基线与本候选 1.25.0 的对应关系，统一串行装载与必要重载，沿已有流程保存上一个可用组合及撤回入口。不要让本任务的资源包覆盖刚修好的主任务文件。
- 在首次目标试用检查创建/资源错误、输入/返回、两级菜单和弹窗，然后测量启动与首次/再次打开耗时、驻留内存、休眠唤醒。白平衡工具、水平仪、DateTime、旧 ProfilesView、媒体页本轮没有常驻，不需要为验证强行激活它们的副作用。
- 回传最终包哈希、目标 Qt 版本和实际通过/失败项目；遇到白屏、菜单打不开、焦点失控或持续内存增长，停止该候选试用并由主任务按既有方案撤回。以上实机项目仍未实测。
