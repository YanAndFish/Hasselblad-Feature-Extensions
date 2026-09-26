# 同一冻结包的新尝试方案

本方案曾用于第二次经 root 明确安排的设备窗口；整根归档及同包新轮装载均成功。旧冻结包仍为 SHA256 `8d960d2309f18923d80cb7b5e1fe452fc6f225260da15d5fc87b2bb1545611ad`，没有重建或替换。相机后来重启清除了运行期状态，第三轮直接按原 stage/preflight/ui/status 流程重新装载成功；不再复用 a1 归档流程。

## 为什么归档整根目录

第一次尝试已经在 `/tmp/hbl-replay-page/phases` 留下 `preflight` 与 `ui` 的 `sent/exit/log`。删除这些文件会绕过一次性门禁，也会失去失败证据。只移动 `phases` 需要两次 rename 才能换入新目录，中途状态更复杂。

[attempt.py](session/attempt.py) 采用单次同文件系统 rename，把整个 `/tmp/hbl-replay-page` 移为模块专属 `/tmp/hbl-replay-page-a1`。归档内完整保留原包、manifest、解码证据和六份 phase 文件。随后原 [delivery.py](session/delivery.py) 才能按原逻辑在 `/tmp/hbl-replay-page` 新建同一包，不需要重启机身，也不删除旧 `sent`。

归档前必须同时满足：包及逐成员摘要仍为固定值；原厂干净 preflight 当次通过；旧 phases 为 0700 普通目录且无锁；六份记录名称精确匹配；`preflight.exit=0`、`ui.exit=62`；没有 state、回放 drop-in、replay.status、已有归档或符号链接。任何一项不符都不执行 rename。曾进入安装事务、曾成功安装或有 restore/status 记录的轮次不能使用这份 a1 工具。

## 下一轮顺序

root 在新的设备窗口确认当时状态和执行权后，顺序为：

1. `attempt.py --archive`：重新做上述只读门禁，再执行唯一一次整根 rename。
2. 如果归档命令结果未知，只运行 `attempt.py --observe`；不得重发 `--archive`。observe 会区分归档存在、原路径存在和新 stage 已重建原路径三种明确状态。
3. 归档确认成功后，运行原 `delivery.py --stage`，由其在原路径暂存同一 SHA256 包。
4. 依次执行新的 `preflight → ui → status`。任一阶段失败仍按原合同停止；不会自动开第二个归档或再试安装。

归档操作不改变 systemd、服务或相机业务状态。若归档成功而新 stage 失败，旧尝试仍完整保存在 a1，原路径由 stage 自己的一次性创建规则约束。工具没有 `rm`、覆盖归档、通配清理或其他 `/tmp` 目标。

## 健康诊断边界

本次历史 `replay-health` 只能返回总体失败码 65，无法事后证明是 `system_state`、三个 link status、UI power、owner/PID 稳定性或 D-Bus 回复中的哪一项。后续健康恢复只能证明后来快照通过，不能把历史失败归因为睡眠或某个具体属性。

离线构建了独立的 [health_diagnostic.cpp](session/native/health_diagnostic.cpp) 候选。它仍只用 `Properties.Get`，禁止自动启动服务，最多三次快照并受 8 秒总超时约束；失败会标出 sample、field、reason，全部字段读到但状态不合格时输出五个状态值和 UI PID。它不读取序列号、文件名或照片信息，也不写 D-Bus。

诊断 ARM 二进制位于 `build/session/diagnostic/replay-health-diagnostic`，其 SHA256 为 `d244d1e8d20d0cc83c0711117ae418cffc1e8c215ed0d5a0a0392f14cb5386ab`。它明确不在旧冻结包内，也未在目标执行。若下一轮坚持使用完全相同的旧包，仍只能得到总体健康失败码；要在设备上获得细分原因，必须另行审核一个包含诊断程序的新包或独立只读诊断交付，不能暗中替换旧包成员。

离线证据为 `build/session/attempt-validation.json`（18 项）和 `build/session/diagnostic-validation.json`（10 项）。前者含模拟传输与实际本地原子目录 rename；后者检查实际 ARM32 ELF、固定依赖、只读方法、字段覆盖和敏感信息边界。两者均为 0 device，不能代替下一轮现场门禁或目标运行。
