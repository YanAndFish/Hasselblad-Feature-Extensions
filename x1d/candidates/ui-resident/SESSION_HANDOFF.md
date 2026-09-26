# 独立 UI 会话包交付

主任务已于 2026-09-13 完成此独立原厂 GUI 会话包的实际安装，四资源、四组件和健康检查链通过；[安装事实与四阶段回执](INSTALLATION_A8_20260913.md)。实际菜单体验与性能仍待用户确认。本 UI 任务仅登记回执，未新增设备请求。

构建时的 ARM Qt5.5 编译、27 项真实脚本替身测试、12 项传输/解码检查、21 项最终归档检查均通过，共 60 项新增离线检查。冻结包及旧报告保持构建时内容不变。

## 固定包

- [ui-resident-session.tar.gz](build/session/packages/a8a78411c639f418/ui-resident-session.tar.gz)，41,432 字节。
- 包 SHA-256：`a8a78411c639f4182d87e79279886273f499d8ab5ebca7cfbf02a394b50ae177`。
- [完整包清单](build/session/packages/a8a78411c639f418/package.json)，9 个成员。
- `manifest.sha256` 自身摘要：`03ada019d34b8e1dff1df112a9abf183432987c404129f989c8477a16ab13de6`。
- 固定 RCC 仍为 `0456d37bc5ddbc57b97e8a9e8cc41b3eff0bd5efa192215bd9f3ae6022029994`，25,185 字节，旧固定目录全部成员均核验未变。
- 单库 `libhbl-ui-resident.so`：`fc738f1ae9dc2db0fc1daf10982041deb88e93c48a08a61b71d884c27d571b0c`。
- 只读健康检查器 `ui-health`：`6c503c33cf6316baf681c788ab45e553260d23907176ba4a47fb4004eed97f86`。

## 实际入口

完整前提、失败处理和重入限制见 [会话操作说明](session/README.md)。所有本机命令从 Hasselblad local 根运行。

```powershell
# 默认只离线校验。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py
# 以下仅由独占相机的主任务执行。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --stage
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase preflight
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase ui
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase status
# 恢复入口，不属于正常安装的自动后续步骤。
py -3 -X utf8 -B x1d/candidates/ui-resident/session/delivery.py --phase restore
```

Linux 临时根为 `/tmp/hbl-ui-resident`，只写一份 `/run/systemd/system/victory-gui.service.d/90-hbl-ui-resident.conf`。不写其他 drop-in，不含 AF/引闪/回放，不进行 FARM 内存操作或 msg2dbus 重启。

目前回放会话存在时，主任务可选择只暂存包；实际 UI 前置与装载会拒绝已有 GUI/configstore/jpeg 等 drop-in，包括未 daemon-reload 的文件。先使用回放自己的恢复流程回到原厂服务，再运行 UI 的 preflight/ui。不能把此库直接追加到回放的 preload；同时使用两者需另行形成组合装载与恢复方案。

相机 unit active 不表示相机 Active。健康程序分别核验系统、链路和 UI 电源状态，接受 `system=2/power=0` 或稳定 `system=4/power=1`；后一种通过原厂 GUI 重启初始化进入会话，未增加唤醒命令。基线摘要路径直接交 `sha256sum`，已经验证 `libstdc++` 的 `+`；脚本没有使用一概拒绝所有 `(deleted)` 映射的规则。

UI 阶段需确认四个生效 QRC 文件摘要、原厂根对象、四个组件 Ready、当前 PID 状态文件、本库映射、三份健康快照与总线 PID 未变化。失败时自动尝试仅恢复本包 GUI 覆盖，并保留非零安装结果。通信结果不明只用 `--observe ui` 观察，不重发安装或擅自清理锁。

## 证据

- [ARM 构建](build/session/native/build.json)：固定 Qt5.5 基线链接，ARM32、动态重定位段连续。
- [27 项事务检查](build/session/install-validation.json)：真实 shell，服务/进程/UID/原生健康为替身。
- [12 项传输检查](build/session/transfer-validation.json)：真实解码、完整字节覆盖、命令上限、摘要不符/响应不明停止。
- [21 项最终归档检查](build/session/package-validation.json)：实际归档、LF、权限、成员摘要、ARM 导出、11 项原厂基线和 `+` 路径。

这些证据不包含设备运行结果；不能标记目标编译、菜单交互或性能已通过。
