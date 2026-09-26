# 独立临时装载与精确撤回

工具已实现，离线事务、ARM 控制器和冻结归档检查通过，并已用于独立回放包的有界装载。本文件不新增后续设备授权，不合并四包。

## 输入与所有权

固定基线为离线 X1D-50c 1.25.0 victory-gui 及相应库，实际摘要由包内 baseline.sha256 核验。只接受五个原厂服务均健康、没有任何已加载或磁盘遗留 drop-in、没有额外 LD_PRELOAD/LD_LIBRARY_PATH 的干净状态。因此本工具不接受当前 AF/UI 覆盖，也不负责撤掉它们；未来需由协调方另行安排独立测试窗口。

暂存根固定为 `/tmp/hbl-replay-page`，权限 0700；本模块唯一 drop-in 为 `/run/systemd/system/victory-gui.service.d/90-hbl-replay-page.conf`，环境开关为 `HBL_REPLAY_PAGE_ENABLE=1`，加载 `libhbl-replay-page.so`。只运行期生效，不修改原厂程序、原服务 unit、启动持久配置或照片目录。暂存目录已存在即拒绝，不覆盖既有证据。

## 已实现阶段

入口 [delivery.py](session/delivery.py) 默认仅离线校验。未来明确获准后才可使用其设备参数；本次没有使用这些参数。

| 阶段 | 实现与判定 |
| --- | --- |
| `--stage` | 231 字节以内 ASCII 命令分块传输；核对编码、解码器、归档及逐成员摘要后才解包。不变更服务 |
| `--phase preflight` | 原厂基线、五服务、unit/drop-in/环境、GUI/Bus PID 和只读健康检查；失败无服务变更 |
| `--phase ui` | 原子取得本轮所有权和阶段锁，创建唯一 drop-in，只重启 victory-gui；异常进入本模块精确撤回 |
| `--phase status` | 校验当前 GUI PID、原生库映射、同 PID 的七资源/七组件/两个静默完整页面就绪标记、原厂 Bus PID 及只读健康 |
| `--phase restore` | 仅撤回本轮摘要匹配且无后来覆盖的 drop-in，恢复预检已确认的原厂状态；GUI/Bus/健康复核后写成功回执 |
| `--observe preflight/ui/restore` | 结果未知时只观察已有阶段回执，不重发动作 |

状态脚本可重复执行；动作阶段使用原子锁与 `.sent/.exit` 记录，拒绝重复、并发以及已有未知结果。传输异常立即停止，不自动重传。宿主最多观察 90 次后报告未知，不能把观察超时当成远端已停止。

实际服务命令通过 [control.cpp](session/native/control.cpp) 编译的 ARM 控制器：变更白名单仅 GUI start/stop/restart 与 daemon-reload；五服务仅允许限定的 is-active/show。正常等待上限 15 秒，超时仅向自己创建的子进程/进程组发送 TERM、200 毫秒后 KILL，再用非阻塞 wait 最多观察 1 秒。计数上限不是实时调度精度或服务已撤销的证明。健康程序有独立 8 秒 alarm，GUI 页面静默就绪观察为 10 秒。

原生注册库核验固定 GUI 和 RCC 摘要，链式调用原 Qt 入口，检查七个实际 QRC 摘要；编译七组件但不额外创建页面。主 GUI 加载后观察其原 LCD/EVF 两个完整 MediaBrowseView，要求已构造、未呈现、列表为空、放大 source 为空。实际目标 QObject 层级及完整 Qt5.5 执行仍待验收。

## 失败与撤回边界

应用失败只清理本轮已取得所有权的变更。drop-in 内容变化、出现后来覆盖、Bus PID 变化或原厂健康不符时拒绝宣告成功，保留状态和日志；不清理其他模块、不重启 Bus/配置/编码/存储服务、不自动重试未知结果。事务和撤回失败分别留证。

27 项 shell 替身检查覆盖正常安装/状态/恢复、失败启动、组件错误、缺失/过期就绪、健康失败、外来配置、包/基线篡改、并发、重复、未知结果及撤回期间所有权变化。47 项实际 ARM main 仿真另行验证有限命令、环境拒绝、退出码、信号、超时与无法回收子进程；libc 进程操作为内存替身，没有调用真实服务。证据位于 build/session/install-validation.json 和 control-validation.json。

原厂恢复成功后仍保留本轮临时证据，不自动删目录；同一目录不用于再次安装。当前第三轮装载成功且保持已装状态，未执行撤回；仍无照片下载、存储、原厂 provider/GPU 释放专项验收。完整用例见 [目标验收](FunctionalTests/TARGET_ACCEPTANCE.md)。

第一次设备尝试在安装事务开始前被第二次健康门禁拒绝，现场确认无 state、drop-in 或服务变化。第二轮按 [ATTEMPT_RECOVERY.md](ATTEMPT_RECOVERY.md) 原子保留旧证据后装载成功；相机后来重启，第三轮重新暂存同一冻结包并装载成功。最终 PID、回执摘要和用户手测边界见 [user-acceptance-20260913.json](artifacts/user-acceptance-20260913.json)。
