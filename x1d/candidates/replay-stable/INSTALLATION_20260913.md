# 主任务装载结果：等待用户回放反馈

主任务已完成 `stable-r1` 实机装载。本任务只读核对了其本地证据，未访问相机；仅新增本记录和 [结构化记录](records/installation-20260913/installation.json)，现有归档、成员、源码、构建产物及交付清单全部冻结，不重建或增加功能。

归档仍为 812,519 字节，SHA-256：

```text
1df99fb712e23c10ada543b2b58ded609ad289d9c16993317cf7414b340469b0
```

主任务报告用户已手动正常重启，先测回放，原 AF 临时安装已清。主任务报告目标端 14 个成员逐字校验通过；本任务核对的是其 `staged=true` 证据和本地冻结归档，没有再次读取目标文件。

| 阶段 | 已记录结果 |
| --- | --- |
| 完整包传输 | `staged=true`，6267 请求，全部句柄关闭，`failed=false`。 |
| 最终安装 | `completed=true`；`ui-awake-r2=0`、`enable=0`；53 请求，全部句柄关闭，`failed=false`。 |
| 最终运行状态 | `replay-status recorded=enabled live-health=active live-services=match`。 |
| 其他候选 | AF、flash、resident UI 未装。 |
| 装载过程的相机操作 | 主任务记录拍摄、照片读取、FARM 请求均为 0。 |

来源为主任务的 [传输结果](../../combined-runtime/build/sessions/replay-stable-stage-20260912T182750263562Z/stage.json) 和 [最终安装结果](../../combined-runtime/build/sessions/replay-stable-continuous-install-20260912T184100365744Z/installation.json)。结构化记录绑定了七份阶段证据及全部冻结交付文件的 SHA-256。

## 安装前的活动状态门槛

当前 `--active` 接受的 System/UI power 状态是 `2/0`。传包后只读观察曾为 `4/1`；`ui` 和 `ui-awake-r1` 都在 preflight 明确退出 64。主任务报告当时会话 state 不存在、未改服务；失败记录保留，归档未重传，任何归档成员均未修改。

期间主任务进行过一次原厂 GUI 重载。初次 1 秒检查出现 property unavailable；稍后只读检查显示 active，但等待与安装分开后，`ui-awake-r1` 再次没有通过 preflight。最终把就绪等待和新阶段 `ui-awake-r2` 放在同一进程连续执行，进入该轮时三个采样已是 `2/0`，因此**最终轮**的 `guiRestartsBeforeInstall=0`。该字段不表示整个过程没有发生前述一次 GUI 重载。

`ui.sent/exit64` 和 `ui-awake-r1.sent/exit64` 按主任务报告保留；成功阶段有独立证据，不能将它们改记为原 `ui` 的成功，也不能抹去早期失败。

## 尚未取得的结果

用户正从原回放入口自行测试，目前尚无实际功能、时延或内存验收。以下状态均保持待验证：

- 多张 Full 后黑屏、挂 Hasselblad logo、界面无响应是否消失。
- 首次冷入约 6 秒和再次进入约 1 秒多的差异。
- Full 放大时延。
- 拍后自动回放时延。
- 真实 CPU/GPU 内存峰值与回收行为。

装载成功不能证明上述问题已修复，也没有新增 OOM 或崩溃根因证据。`releases/stable-r1/package.json`、原 README 和交接说明保留为离线交付时的快照；本文件记录后续装载事实，不回写历史的 `installed=false` 或离线验证字段。等待用户反馈期间保持现包不变。
