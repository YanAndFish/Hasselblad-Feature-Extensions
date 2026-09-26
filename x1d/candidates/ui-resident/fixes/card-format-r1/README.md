# 格式化入口 text2 角色修复

独立修复包已冻结，175 项离线检查通过，尚未安装相机。包仅修正普通设置模型的 `text2` 缺省初始化；格式化页、格式化动作、警告文字、动画、主菜单与设置页常驻范围均保持。

## 根因与修正

主任务从已装 `a8` 的当前 GUI 日志确认 `SettingsGeneric.qml:603` 与 `:617` 各发生一次 `ReferenceError: text2 is not defined`，分别对应 Card0/Card1 的 `subDialog.setSource(..., {subText:text2})`。参数求值抛异常，下一行 `subDialog.active=true` 未执行，吻合按钮亮一下但弹窗未出现的反馈。证据：[错误符号](../../build/session/sessions/format-entry-reference-20260912T204220344561Z/observation.json)、[错误行号](../../build/session/sessions/format-entry-lines-20260912T204311660355Z/observation.json)。本任务没有连接设备。

离线使用原厂 Wedge 的完整 `generalSettingsLanguage` 与 `generalSettingsStorage` 数组复现：先进入不含 `text2` 的语言页，再进入存储页，常驻 `ListModel` 已接收到警告文字，但已有委托上下文取不到后加入的角色。原厂临时页面没有此复用路径；旧 `a8` 的两个入口均产生同类异常。

修正只替换 `populateModel()` 内一个表达式：

```javascript
"text2": (v.text2 === undefined || v.text2 === null) ? "" : v.text2,
```

这让首次填充就建立字符串角色，后续页面仍使用其原始文字。没有在入口吞掉异常或绕过确认，也没有删除警告。除 `SettingsGeneric.qml` 这一处表达式外，其余三个资源逐字等于已装 `a8`。

## 固定包与边界

- [ui-format-r1.tar.gz](build/session/packages/43389409e183e3af/ui-format-r1.tar.gz)：41,452 字节，9 个成员。
- 包 SHA-256：`43389409e183e3af8c90a58deb3f8cad973b5e101d9f41478f93e6ea39967486`。
- RCC SHA-256：`5c59876df74eb25a8dafa22dcdc44f626abac9c0ebbf1da44543e9e3214e7c64`。
- ARM 库 SHA-256：`7b4895a284f0897b2fdc6a12c91bc01b78044007de2db3e1e86a6267053a29c6`。
- `SettingsGeneric.qml` SHA-256：`648edfe475ddba4adb261ba25a77a9f383738a92e5c37e5af09279ad9469bd41`。
- manifest SHA-256：`65553938827af9f55633ddd5de42ddbe890d1d25636039f4b9c531a14f6e236b`。
- [完整摘要与证据绑定](build/session/packages/43389409e183e3af/package.json)、[单处差异](build/session/resources/changes.patch)。

原厂固件基线仍严格绑定 X1D 1.25.0 的 11 个文件。新 Linux 目录为 `/tmp/hbl-ui-format-r1`。原 `a8` 包、`83b` 包、原 `session/delivery.py` 及其默认记录没有改写。

本包是原厂 GUI 环境专用完整包，不含 AF、回放、引闪或 JPEG 缓存。当前如果已有 AF/r6、回放或其他覆盖，前置检查会拒绝；不自动卸载其他模块。不能将本包直接追加到现有 AF preload。

## 主任务串行入口与恢复

从 Hasselblad local 根执行，默认只离线核验：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/fixes/card-format-r1/delivery.py
```

当前返回 `readyForRootStaging=true`、`targetValidated=false`、`hardwareRequests=0`。仅主任务取得设备独占和用户当前授权后执行：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/fixes/card-format-r1/delivery.py --stage
py -3 -X utf8 -B x1d/candidates/ui-resident/fixes/card-format-r1/delivery.py --phase preflight
py -3 -X utf8 -B x1d/candidates/ui-resident/fixes/card-format-r1/delivery.py --phase ui
py -3 -X utf8 -B x1d/candidates/ui-resident/fixes/card-format-r1/delivery.py --phase status
```

正常重启不作为环境干净的证明，仍须通过前置检查：五个原始服务配置、磁盘和已加载 drop-in、进程 preload、基线及稳定健康状态；接受稳定 Active `2/0` 或 Standby `4/1`。若仅旧 `a8` 仍在且主任务决定更换，先通过旧 `session/delivery.py --phase restore` 撤销旧 UI，再使用本包 preflight/ui。若 AF/r6 等仍在，由其负责人按已有合同处理并串行交接；本包不会删除这些配置或重启 bus。

新包仍只创建一份 `/run/systemd/system/victory-gui.service.d/90-hbl-ui-resident.conf`，其中 preload 指向新目录。四份 shell 仅将旧远程根替换为新根；原安装、失败恢复与所有权检查逻辑不变。恢复命令：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/fixes/card-format-r1/delivery.py --phase restore
```

只移除本包原样配置，回到原厂 GUI；不是回退到有故障的 `a8`。失败时按相同合同尝试恢复原厂 GUI，保留失败结果与证据。未知结果使用 `--observe ui`，不重复派发。阶段锁、sent/exit 文件与新目录内回执保留。

安装仅做正常根创建、四实际资源摘要、四组件 Ready、本 PID 标记、三次健康快照与 bus PID 不变检查；不会为验证主动进入菜单、回放或格式化页。`isReady` 不代表真实首帧时延，用户要求的首次进入观察仍留给用户操作。只需要验证入口与取消，无需执行真实格式化。

## 离线证据

| 检查 | 数量 | 结果 |
| --- | ---: | --- |
| [原厂/旧包负例/修正版 QML](build/qml-validation.json) | 132 | 通过 |
| [新路径实际 shell 事务](build/session/install-validation.json) | 17 | 通过 |
| [最终归档、Qt 回读、ARM、传输](build/session/package-validation.json) | 26 | 通过 |

页面回归使用 Qt 5.15.2 主机：原厂真实语言和存储列表、双卡及分别单卡、首次直接进入和换页后进入、两轮关闭隐藏后复用、实际鼠标点击、原厂按键取消、正确卡槽、原警告文字、焦点返回。旧 `a8` 负例必须重现 `text2` 异常；修正版没有此异常。全部进入/取消检查的存储替身 `format` 调用数为 0。

Qt 6.11.2 主机在旧 `a8` 与修正版完整列表销毁时都出现访问异常，因此没有把该环境标为通过。正式回归采用 Qt 5.15.2，正常关闭与销毁均通过；它仍不能替代目标 Qt 5.5 的实际验收。原生业务插件、状态栏、图形效果使用显式主机替身，主机统计不作为相机性能或内存结果。

新原生库用固定 Qt 5.5.1 头文件与目标原厂库离线编译为 ARM32，动态重定位布局已检查；健康检查器与旧版逐字相同。包审计还实际注册 RCC 并用 Qt 回读四文件、执行完整归档的经典解码流程，检查新路径命令不超过 231 字节，错误摘要和未知结果停止且不重试。

重建入口依次为本目录 `build.py`、`CodeTests/run_qml.py`、`CodeTests/test_session_paths.py`、`package.py --build`、`CodeTests/test_package.py`。构建和测试只属于离线交付，不代表本包已安装。
