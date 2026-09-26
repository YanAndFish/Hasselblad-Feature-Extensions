# Qt 5.5 保留字最小修正

**旧包 `589913e7...` 已在主任务的真实 Qt 5.5 编译检查中失败，应停止使用。新包只修正该已定位问题，尚待主任务重新进行完整目标组件编译与验收。** 此前 Qt 6 的 91 项检查没有捕获该差异，不能据此宣称目标兼容。

主任务回传：`MainScreen.qml:1127:9 Type ResidentLoader unavailable`，下层原因为 `ResidentLoader.qml:19:67 Expected token numeric literal`。本文件第 16 行才是 `useResident`；第 19 行第 67 列是下列 `transient` 的首字符：

```qml
(useResident ? retained.status : transient.status)
```

固定 Qt 5.5.1 源码 `qqmljslexer_p.h:115` 定义 `T_TRANSIENT = T_RESERVED_WORD`；`qqmljskeywords_p.h:781` 在 `qmlMode` 把该单词分类为这一 token。来源为本项目 `.research-cache/x1d-1.25.0/qt-public/qtdeclarative-opensource-src-5.5.1/src/qml/parser/`，哈希写入词法回归报告；也可核对 [Qt 5.5.1 原关键词分类源码](https://raw.githubusercontent.com/qt/qtdeclarative/v5.5.1/src/qml/parser/qqmljskeywords_p.h)。

修正只有：将 `ResidentLoader.qml` 中 **8 处标识符 `transient` 改成 `lazyPageLoader`**。声明和引用一并改名。没有修改业务行为、`objectName` 字符串、`compose(resources)` 或其他三份资源；没有修改主任务 `main.qml`、ControlScreen、引闪、AF、回放文件，也没有设备访问。

## 新固定绑定

固定目录：[build/fixed/ui-resident-0456d37bc5ddbc57](build/fixed/ui-resident-0456d37bc5ddbc57)。

| 对象 | SHA-256 |
| --- | --- |
| 新 `ui-resident.rcc`，RCC v1，25185 bytes | `0456d37bc5ddbc57b97e8a9e8cc41b3eff0bd5efa192215bd9f3ae6022029994` |
| 新 `/mainmenu/ResidentLoader.qml` | `fa24ea45fafe6927b103e9225e6923de2164a8695f5ab9d4757ac7f3d657a64c` |
| 旧 `/mainmenu/ResidentLoader.qml`，仅作精确升级来源检查 | `81c4ad1a560b87e2b28f416e553ec83a097185581482706c2ff7328758abd067` |
| 新固定目录 `release.json` | `030589fb58d6acd503c09dc7d61a9db3e199dd3a169ee0a4f111fad855689d2f` |
| 未变的工作接口 `tools/build.py` | `915fdf996a40dc88a319c431a5b0402b9d37e2598de09470624e45d829002753` |
| 新 59 项报告 `reports/validation.json` | `a04c3d676f24913dc03af97c3369554e98191ae2c8aee2db2f186a4fbd3a168d` |
| 新 32 项报告 `reports/original-pages-validation.json` | `f4259c4e10153fe59c83658d34112375c057072d01cfa69b7cbf9434401b5b19` |
| 词法回归 `reports/qt55-identifiers-validation.json` | `c12bca373ab1e54de1fb6fab92630f3c5133d82ba2e6fb3b76f86b5105c08f31` |

其他三份输出保持：MainScreen `552d546a679071669eb67b7cb02f4424c3c56ed020beaa00244bc7ae5f435433`；Menu `593344a502e333f24abefd30d28cac040c9c1b5d5be31814cb34292fd54c7961`；SettingsGeneric `fc6b8208c358dcdb685eda00d92d974e7219e801c4cac89c1ffb79be968f8955`。固定目录的 `manifest.json` 包含完整四资源输入 / 输出绑定。

## 验证性质

- `CodeTests/test_qt55_identifiers.py` 以原 Qt 5.5.1 `Lexer::classify` 函数体运行主机 C++ 测试，提供最小 ASCII QChar 适配和原 token 数值；确认旧名称为 `T_RESERVED_WORD=86`，新名称为 `T_IDENTIFIER`。四资源的 79 个 QML `id` 全部分类为普通标识符。
- 该测试同时断言新旧组件的完整差异只能是上述标识符替换，其他三资源的 SHA-256 必须不变。
- 原 59 + 32 项 Qt 6.11.2 主机检查已对新源码重新执行通过，报告绑定当前源码。
- **词法分类不是完整 Qt 5.5 QML 编译，也不是设备试运行**；报告明确 `targetQmlCompilePassed: false`。目标真实 Loader、上下文、Flickable、输入、业务单例与联合功能仍由主任务验收。

运行命令（只在本候选下生成主机测试文件与编译缓存）：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_qt55_identifiers.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_resident.py
py -3 -X utf8 -B x1d/candidates/ui-resident/CodeTests/test_original_pages.py
```

## 主任务重包

从尚未含常驻 UI 的最新正式资源输入重新运行原 `compose(resources)`，它会读取本次新组件。若主任务手头已经是上一轮完整组合字典，则先核对其中 `/mainmenu/ResidentLoader.qml` 的旧 SHA 为 `81c4ad...`，再仅替换这一项为新组件，并断言所有其他资源逐字未变；不能对已包含常驻 UI 的字典重复调用 `compose`。

必须重新计算最终联合包哈希，再按主任务已授权的串行流程重做 Qt 5.5 目标编译。不要复用失效包的可用状态或把词法修正等同于目标成功。本任务收到主任务“已恢复原厂 GUI、关闭本轮请求”的回报，但没有自行连接设备核验或重启任何服务。
