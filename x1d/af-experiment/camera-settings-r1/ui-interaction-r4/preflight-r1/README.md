# r4 GUI 预检 61 的限定继续入口

旧 apply 在 GUI 改动前因 `--require-active` 拒绝 `system=4 / ui-power=1` 而退出。固定 e373 检查器已有 `--require-ui-stage`：允许 Active `2/0` 或三个链路均正常的 Standby `4/1`，要求三次合格快照与稳定 UI owner PID。本次仅把 GUI 前置及 GUI 恢复/就绪检查的两处调用改用该模式。它不宣称所有亮屏菜单必为 `4/1`，也不放宽 FARM gate。

原 r4 的 57728 字节包、UI 库、RCC、90/95 配置契约及旧失败证据均保持不变。本入口只追加 2188 字节的继续脚本包，复用已经传好的 GUI 产物。

主任务在仓库根目录直接执行一次：

```powershell
python -B x1d/af-experiment/camera-settings-r1/ui-interaction-r4/preflight-r1/main.py continue --evidence ./x1d/af-experiment/camera-settings-r1/ui-interaction-r4/build/sessions/af-ui-r4-apply-20260912T173356108139Z/result.json
```

入口要求同一原包的完整 stage、明确的 `61\nsystem-active-hold-not-ready`、0 AF RAM 写入且全部主机句柄关闭。设备端再次校验旧 `apply.sent`、`apply.exit`、`apply.log` 的精确 SHA，以及没有 touched、applied、恢复标记、bus PID/备份或 95 配置；检查原包、原 GUI/bus 和现成 GUI 健康 gate 后，才执行新 `apply-preflight-r1` 阶段。旧 apply 的 sent/exit/log 不删除、不修改、不重发。

GUI 失败时只调用本继续版的 AF GUI 恢复脚本。若需要显式恢复，用同一命令把 `continue` 换成 `restore`，仍传上述原失败证据；它使用独立 `restore-preflight-r1` 阶段，保留全部旧记录。阶段结果未知就停止，不能重发命令。AF RAM、bus 和相机设置不由本入口修改。

微型包 SHA：`8f7c7b9980ec5edbfe2dc1185feaba46e3d00f58dc1e363a82a2d9de3895a92c`；验证文件 SHA：`59cbb95c36d25d6dc041e20c474e28f0862a3376baea6f162541c8a7d56d4ebd`。

已完成 10 项限定检查，包括原检查器源/二进制身份、仅两处 GUI gate 差异、有效继续、旧日志/退出码变更、已有触动、PID备份、其他配置、未完成阶段和重复阶段拒绝；另验证微型传包逐字回读模型和所有主机命令不超过 231 字节。没有重编 ARM、重跑 AF 测试或操作设备。默认 `report` 离线已返回就绪。
