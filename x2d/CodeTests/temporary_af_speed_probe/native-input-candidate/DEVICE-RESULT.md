# 原生菜单控制：实机补充记录

用户重新连接 USB，要求小范围探查，随后明确要求本轮原生版本持久化，并尽早随原厂界面加载。没有拍摄、对焦、闪光、射频操作，也没有重启原厂 GUI 或相机。

## 已验证

- 维护通道先确认原厂 4.2.0 文件哈希、稳定两步菜单版本和只读系统分区。原页面 PID4018/start641527 仍在，累计 20 次切换。
- 实机 libc/libdbus 与离线链接依赖哈希相同，输入设备名称为 gui_buttons。
- 旧 shell 独立查询 live_view_state、exposure_status 各约 30ms、40ms；仅本轮样本，不是长期统计。
- 新原生库在原厂允许的独立 camera-test --version 宿主中执行 inspect。只读两属性，第一对 5ms，第二、第三对各 2ms；记录 INSPECT_OK_NO_WRITES。此测量不包含按键输入或屏幕显示。
- 正常停止旧自有加载器，确认原前键恢复、旧两个进程退出后，将本轮旧日志归档 `/tmp/x2d-input-before-native`。
- 原生候选创建隐藏页面，状态 READY_NATIVE；自有页面 PID7970/start923401，控制进程 PID8132/start923529。原厂 GUI 仍 PID364/start61，原厂两项服务 running。
- 原生准备、激活事务已执行成功，系统恢复只读。所有新文件和两份旧配置备份均回读匹配。
- 最终回读：安装用 ADB 已停止，USB 已恢复 `rndis,mass_storage,bulk,acm`；原生控制仍 READY_NATIVE、窗口隐藏。此时才交给用户手动重启验收。

## 当前持久化文件

| 文件 | SHA-256 |
|---|---|
| `/system/lib64/libx2d_menu_input.so` | `5d942911dac34a090347cc8a1c66adcb246c1351b826f6b932b605b17c088729` |
| `/system/etc/x2d-preview-native-code.bin` | `112c43e8e2e331a9673ce1d531ba5a51b2a5796f6214a9c34ae1d58a36224c72` |
| `/system/etc/x2d-preview-loader.sh` | `46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb` |
| `/system/etc/init/x2d-preview-loader.rc` | `d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc` |

备份后缀为 `.before-native-input`：加载器应为 `059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721`，启动配置应为 `8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67`。原有其他历史备份没有覆盖。

## 安装过程的两次前置拒绝

1. ADB su 域无法读取原厂 camera-test 文件，第一次 prepare 在写系统前停止。只读确认无新增目标文件，原系统仍只读。将原厂文件哈希检查保留在能正常读取它们的维护通道执行；没有修改访问策略。
2. ADB su 域无法读取自有私有运行日志，第一次 activate 在写配置前停止。只读确认两个原配置未变、无新备份。由维护通道读取 inspect 和 READY 证据，再由原有 ADB 安装事务校验待装文件、写入自有配置。没有改变私有日志权限。

## 尚未完成

- 用户真实按键及多次切换的原生计时。当前仅确认隐藏就绪，没有用程序自动弹页替代用户验收。
- 完整关机开机验证。较早触发采用原厂 GUI service running 属性，实际触发时刻仍待开机日志证明。
- 屏幕实际首像素／可交互时刻测量；不能根据 5ms 回调或 2ms 属性读取宣称整页 20ms。
- 初次创建窗口与首帧渲染的差异、提前加载对首次取景的影响。

`Deploy-NativeMenu.ps1 -Action Rollback` 只恢复自有两份配置，保留惯性加载的候选库文件；运行中控制器应先正常停止并核对恢复原前键，避免同时存在两个监听实例。调用之前仍须确认设备与当前文件身份，不盲目重试不确定写入。
