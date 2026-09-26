# 正式无线业务离线测试

运行 `python x1d/wireless-flash/CodeTests/formal_policy_build.py`。脚本仅使用当前项目已有 Zig 工具链，在本目录临时子目录内编译、运行和清理测试及缓存，不访问相机或无线设备，不安装程序。结果打印检查数与 `hardware-requests=0`，并保存 `formal_policy_output/validation.json`。该报告绑定测试期间保持不变的业务源码、worker、桥接协议、无线层及测试替身哈希；任一编译或测试失败时，报告保持 `passed=false`。

被测对象是正式 worker 实际使用的 `native/formal_policy.h` 与 `native/formal_bridge.h`。替身只为无线动作提供延后的完成、失败和取消结果；不会把动作提交冒充为发送完成。原生 Qt adapter 与实际无线固件另由集成构建和无线层测试检查，本测试不能证明物理闪光时序。

覆盖三项开关的八种组合、严格包结构、五组功率与关闭波形、界面调节合并、冻结快门快照、每次功率后恢复并核实同步波形才继续、最后恢复前不返回成功、重复快按、令牌与新会话、超时和晚到完成、关闭及异常清理、取消与已经提交的不同结果、固定 ACK 环、手动试闪资格，以及一万步确定性的异步事件交错。

`formal_policy_adapter.test.cpp` 将真实 `FormalPolicy`、`FormalRadio` 和 worker 共用的取消转接连接起来，单独控制 Qt 完成回调到达时机。它覆盖已确认取消后重复取消返回 Empty 的竞态、已提交后的真正失败、取消证明不跨 Fire 复用、普通功率的 off→on 不复活旧 Select、取消旧 flush 后开始新 flush，以及安全停止锁在新 UI 会话中仍生效、Close 失败不能报告安全停止。

真实 worker 以安装闸门锁定状态启动。只有安装端在核验 FARM 与默认关闭后提供固定 `formal-enable.ready` 文件才能解锁；解锁前的启用意图和迟到请求不会自动重放，用户必须发送新请求。`formal-enable.confirmed` 只由 worker 在已解锁且未停止时写出。测试覆盖闸门、迟到请求、新会话和停止锁的优先顺序；该确认文件只证明完成了解锁，不声称此后的当前开关仍关闭。

机械同步使用已记录的十三档名义曝光查表与原机械 core，源为 B。电子同步沿用既有公式并使用 GFS3 携带的本次曝光参数。两条路径均检查模式、epoch、到达时间、事件顺序、结束取消与一次资格；新快门不会接纳前一 trial 的迟到消息。
