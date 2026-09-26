# full-pages-r2 实机安装记录（2026-09-13）

## 结果

固定包 `0669df8606b91a6bd8876b6066be9fa31259a9d21924e989669ae1d35e9a8f14` 已在新的独占 UI 设备窗口中装载成功。目标端成功标记为：

`ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1 pid=2642`

启动门禁在约 28.884 秒时通过。最终诊断看到 1 个 MainScreen、1 个顶层池、3 个子池、26 个 Native Loader 全部 Ready、3 个菜单、23 个普通设置页；26 页均 prepared 且各有一个列表。当前能力条件生成 121 个模型项和 121 个 delegate，其中 95 个普通设置行 Loader 全部 Ready。Loader error、行错误和受监控 QML warning 均为 0。

本结果验证固定 1.25.0 目标上的本次启动与结构门禁。它不能证明 r2 的 Loader `item` 修订是 r1 超时的唯一原因。

## 用户验收

R2 包装载成功后，用户对本轮普通 UI 手测明确反馈“可以，没问题”。该反馈绑定本记录中的固定包、PID 2642 和同一成功会话，记为本轮普通 UI 用户验收通过。

用户没有逐项说明测试路径，因此该反馈不扩张为对特殊工具、卡格式化、所有菜单分支、量化性能、峰值内存、长期稳定性、持久跨重启或与 AF、闪光、回放模块组合运行的验证。当前仍是会话级独立模块测试结果。

## 阶段与恢复边界

首次前检发生在相机待机态 `System=4 / Power=1`，在写入前以 62 拒绝。用户进入实时取景后，新前检输出 `ui-health-self-test-pass` 和 `ui-resident-preflight-ready`，随后只执行一次 `ui` 阶段。`ui` 与 `status` 均成功，没有运行恢复。

前检包装脚本最初只接受单行成功标记，因此把包含上述两行正常输出的本地 `completed` 记为 false；对应目标命令的退出码为 0。后续 `ui`、`status` 和最终审计独立确认安装成功，这一记录异常不表示目标失败。

候选 GUI PID 为 2642；精确 drop-in 为 `/run/systemd/system/victory-gui.service.d/90-hbl-ui-resident.conf`，进程 maps 包含 `/tmp/hbl-ui-full-r2/libhbl-ui-resident.so`，owner 为 `hbl-ui-resident-v1`。`victory-gui`、`msg2dbus-farm`、`configstore`、`jpeg-daemon` 和 `storage-daemon` 均保持 active，msg2dbus-farm PID 268 未改变。成功后相机自然回到 `System=4 / Power=1`，此时状态复核仍通过。

本次续装共 56 个有线命令请求，全部句柄关闭；FARM 请求和总线重启均为 0。没有读取照片，没有触发拍摄，也没有执行 AF、闪光、回放或设置写入。当前装载位于 `/tmp` 与 `/run`，属于会话级独立测试，不是持久合包；不得在其上直接叠加其他模块的 drop-in。

## 证据

- [实时前检](build/session/sessions/liveview-preflight-20260913T000311904313Z/result.json)，SHA-256 `e02db14d91f26e32ac17ed1d3f1d89f56d2e1006485feb75bf4332a848068fd6`。
- [UI 阶段](build/session/sessions/ui-20260913T000325794755Z/result.json)，SHA-256 `0021b36e25abfa4510d4e7957fd507c47b2ecd53576e6338819441e2ee169280`。
- [状态阶段](build/session/sessions/status-20260913T000413712296Z/result.json)，SHA-256 `007a1d9e84e45a842d88ea5822f25e7ade479786df315c2457f464c5b0a51263`。
- [完整诊断审计](build/session/sessions/ui-final-audit-20260913T000507945271Z/result.json)，SHA-256 `a2d56abd28f7e07cc638a54a4318143daec221d75d662582c262c57a33b05b8c`。
- [精确 owner 与映射审计](build/session/sessions/ui-exact-owner-audit-20260913T000530429306Z/result.json)，SHA-256 `8e31fa0eb502ae9b7e45ec2dc3f9cced7648f6ac3c9456675c431901afd216a9`。

目标端 `ui.diag` 为 27 行、3,630 字节，SHA-256 `21aadcb5fd05b36bbd4eed07ddd9430c2b66e55efee018ba00a1a2053e18a5ad`。其首行汇总和 26 个逐池记录已在完整诊断审计中核对；逐池的 Loader、item、prepared、列表及错误条件均通过。
