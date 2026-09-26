# 第一代 X2D 4.2.0 / 55V 临时快扫 1.5 倍实验

这是一份临时实验候选，不是固件或持久补丁。仅适用于第一代 X2D 100C 官方 4.2.0，以及本次现场确认的 55V。不能套用到 X1D、X2D II 或其他版本。

## 本轮结果

**后续实机更正：当前探针和提速入口已禁用。** 用户在六十秒全线程追踪期间观察到无法对焦、画面卡住；已主动停止本轮 strace，回读追踪/暂停线程数均为零，临时目录清理完成。未写入提速代码。此前“挂接和退出通过”只验证了进程层面的进入/退出，不能证明追踪不干扰相机。该轮空采集无有效最大速度，不能作为原厂基线。详见 `probe-safety-state.json`，待找到不干扰相机的观测方式后再评估。

- 已生成候选机器码、真实镜头发送数据的采集器，以及限时恢复工具。
- 1,330 组 AArch64 原函数对照通过；另有 13 项真实 shell 事务的模拟故障测试通过。
- 机上被动追踪确认挂接 105 个线程，三秒后退出，`TracerPid` 恢复为零，临时文件清理成功。
- 无人操作对焦，所以本次采到的快扫命令为零，**实际最大速度命令值未知**。
- 机上原函数回读 SHA-256 与官方函数相同。**本轮没有写入对焦机器码，没有提速，没有触发对焦或拍照。**
- `prepared-plan.json` 当前为 `PREPARED_NOT_UPLOADED`。自动恢复的机器上执行、暂停线程后读取 PC，以及提速后的物理行为尚未验收；不能把离线测试说成装机成功。

## 改动范围

`libaaa.so` SHA-256：

`feef8a8dc3a27395e47232c2b25a5da7a7ab335922fbb527e637c439e35bcec7`

函数区间：ELF VA `0xac380..0xac7ac`。候选只重排 `0xac5e8..0xac628` 和 `0xac70c..0xac718` 两段，合计 76 字节；没有寻找或占用未知“空闲内存”。运行工具在暂停进程后写入完整的 1,068 字节函数副本，所有未改动字节保持原样。

只在动态速度模式、type 0 拍照快扫有效计算分支乘 1.5。type 3 录像快扫、type 1/2/4/5、其他模式、获取失败的回退、原有 FPS 调整及后续相位分支均保留。

离线示例为 5170 → 7755，其余五种类型不变。该例使用固定模型输入，**不是本次对焦实测速率，也不是保证镜头机械速度提高 50%**。相机后续的限制或倍率仍可能影响最终发送值。

## 测速测的是什么

官方静态调用链：

```text
librcam: _DjiLensDrv_HBMOUNT_aaa_focus_scan_move_motor (0xd4e38)
  → _SendCDFocusRequest (0xdc4c0), subtype 5
  → DjiLensDrv_HB_SendCDFocusRequest (0xdee68), command 0x1b
  → DjiLensDrv_HBMount_NET_QueueToSend (0xe19c8)
  → _DjiHBMountNetTsk_Send (0xe2860)
  → libduml_hal: duss_hal_x2bridge_write (0x18930)
  → backend write (0x53828), write@plt at 0x53858
  → /dev/lens
```

原厂 `strace 4.21` 连续记录 `/dev/lens` 的 `write`，只解码完整成功写入的 40 字节帧：头 `0a f8 00 00`、command `1b`、subtype `05`，速度为第 9、10 字节的大端有符号 16 位数。索引从零开始。subtype 6 和 10 是位置操作，不能把它们的大数误记为速度。

结果是**采集窗口内内核接受的快扫速度命令最大绝对值**，不是镜头回执确认，也不是实测转速、焦平面速度或帧率。没有快扫命令时返回 `null`。追踪本身会增加负载，不用于证明完整对焦耗时变快；性能对比应另做不带追踪的手动测试。

## 工具与使用顺序

全部命令从本目录执行，所有写入限于本目录及相机本轮专用的 `/tmp` 目录。需要独占 USB，不应与其他任务同时操作。

```powershell
# 离线构建、机器码和恢复状态机测试；不接触相机。
powershell -NoProfile -ExecutionPolicy Bypass -File .\Build.ps1

# 只读确认当前固件、55V、ASLR 映射、进程身份、原函数；生成本地计划。
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Experiment.ps1 -Seconds 20

# 先测原厂基线：用户在提示出现后手动半按对焦。
powershell -NoProfile -ExecutionPolicy Bypass -File .\Capture-Scan.ps1 -Seconds 10
```

基线文件 `last-trace.txt` 和 `last-capture.json` 会被下次采集覆盖；对照实验前保存到本目录不同名称。不要仅比较两次不同场景或不同快扫次数的最大值。

提速入口是 `Start-Experiment.ps1 -UserPresent -Seconds 20`，**本轮没有执行它**。它会重新核对现场、传输并验算 RAM 文件、暂停并检查所有线程、拒绝在函数执行中改码、启动一个自动恢复窗口，再开始被动测速。它不发送对焦或快门命令。用户在场时才进入这一项验证，不要无人运行。

窗口结束后相机端脚本自行恢复；主机回读原函数验证，成功后清理专用临时目录。USB 中断也不会取消已经启动的相机端恢复计时。若结果不确定，禁止重复派发，先读 `last-window-status.txt` 和 `prepared-plan.json`。

`Restore-Experiment.ps1` 是额外恢复入口：绑定同一次开机、同一进程、同一地址，拒绝与仍活动的事务并发，拒绝覆盖未知字节。若原厂函数已在运行，它不写入。若恢复写入失败，不会把部分机器码继续运行；报告会明确指出暂停状态，此时需要在场处理。该极端恢复路径仅做了离线故障测试。

## 校验与限制

- `offline-results.json`：原函数、候选函数、按预期行为建立的参考执行结果三方对照；外部配置 getter 是模拟输入，原有 FPS 函数实际执行。
- `transaction-test-results.json`：预检、冻结、执行位置、原字节不符、部分写失败、候选校验失败、等待中断、恢复失败等 13 项。
- `last-capture.json`：本轮真正挂接和退出的证据。
- `candidate.json`：固定官方哈希、原字节与候选字节，不能跳过版本或现场校验。
- 不修改系统文件、镜头固件、MCU、FPGA、校准或拍摄配置；不读取照片。重启会丢弃进程内存修改。

ARM64 指令缓存处理参考的是 Linux 4.9 的 `copy_to_user_page → flush_ptrace_access` 实现。相机内核报告为 `4.9.130-rt125-g34abb7a5`；上游源码与厂商构建不是同一份验证结果，实际 RAM 修改及执行仍须在场验收。

参考：[Linux 4.9 ARM64 flush.c](https://github.com/torvalds/linux/blob/v4.9/arch/arm64/mm/flush.c)、[Linux 4.9 memory.c](https://github.com/torvalds/linux/blob/v4.9/mm/memory.c)、[strace 4.21 pathtrace.c](https://github.com/strace/strace/blob/v4.21/pathtrace.c)。
