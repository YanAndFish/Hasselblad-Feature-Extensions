# AF r4 GUI 实机加载通过

2026-09-13（北京时间），主任务通过冻结的 `preflight-r1` 限定继续入口，成功加载 r4 AF GUI。模块任务只读核对完成记录、后续观察和来源 SHA；未操作设备。

已通过范围是实际 Qt 5.5 GUI 启动、资源及新库加载、状态端点就绪和 GUI-only 安装 gate。**尚未验证用户在实机上的按钮操作、query/reply、配置保存或对焦效果。** 主任务已请用户进入 AF 页点加减确认，本记录不代替其反馈。

| 项目 | 结果 |
|---|---|
| 微型脚本包传输 | 32 请求，全部关闭句柄 |
| 继续装载 | 12 请求，`completed=true`、`0 / af-ui-r4-ready` |
| 后续只读观察 | 4 请求，均匹配、成功、关闭句柄 |
| AF RAM 写入 / bus 重启 | 0 / 无；原 bus PID 保留 |
| 系统观察 | `system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0` |
| 新 GUI 状态 | `stage=ready pid=2434 bound=1` |
| 页面状态 | `shown=0 width=0 height=0 connected=0` |
| 查询 / 保存 / 回复 / 编辑计数 | 0 / 0 / 0 / 0 |

观察时尚未打开 AF 页，因此页面尺寸和请求计数为零符合该阶段，但不能据此声称通信已通过。以上为当时的观察，不是持续监测状态。

旧 apply 的 61 失败记录与新继续阶段分开保留，未删除或重发旧阶段。原 r4 大包、UI 库、RCC、90/95 配置契约和所有冻结执行源均未修改；继续版仅使用已有的 GUI-stage 健康检查能力。AF RAM 和 bus 保持原安装，未执行回滚或清理；主任务继续作为唯一设备执行者。

证据：

- [微包传输](../../build/sessions/af-ui-r4-preflight-r1-stage-20260912T174258896227Z/stage.json)
- [继续装载完成](../../build/sessions/af-ui-r4-preflight-r1-continue-20260912T174258688081Z/result.json)
- [后续只读观察](../../build/sessions/af-ui-r4-installed-observe-20260912T174336401312Z/0000.json)
- [原 61 失败](../../build/sessions/af-ui-r4-apply-20260912T173356108139Z/result.json)
- [结构化结论与来源 SHA](result.json)

默认冻结报告的 `physicalGuiVerified=false` 保留发布时的离线状态。后续状态说明应同时引用本次结果，区分“实机 GUI 加载通过”与仍未验收的交互和通信。
