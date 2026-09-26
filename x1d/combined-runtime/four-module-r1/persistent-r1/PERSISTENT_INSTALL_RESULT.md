> 最新：底层装载冷启动已通过，随后发现的[设置恢复循环等待已修复并安装](SETTINGS_RESTORE_REPAIR.md)，整套启动仍待再次验收。

> 最新：已安装[装载超时与恢复修复](BOOT_TIMEOUT_REPAIR.md)，冷启动仍待验收。

> 最新状态：2026-09-14 已安装[无线启动时序修复](RADIO_STARTUP_REPAIR.md)，仍待下一次正常开机验收。下文为首次安装历史记录。

# 四模块永久启动文件安装结果

2026-09-14（北京时间）：**永久文件安装及校验完成；冷启动验证未进行。** 当前相机仍运行已验收的临时版本，安装没有重启 GUI、消息服务或相机。

## 已验证

- 相机独立包 `/opt/hbl-four-module-v1` 和两个 `92-hbl-four-module.conf` 已安装，包内容、原厂基线和 drop-in 与本地构建一致；启用标记在两份配置校验后最后写入。
- 根分区恢复只读，GUI 与消息服务 PID 前后相同；最终系统状态为 Active，SUC、FARM 和电源链路状态正常。
- 安装前后各执行 AF 733 次、HFS1 618 次只读核验，全部通过，没有 FARM 内存写入。安装会话的 Linux 诊断请求为 2666 次，全部关闭句柄。
- 机内 C++ 重定位自检与三个合法地址的独立链接结果一致。
- 机内设置文件自检通过完整往返、非法设置拒绝、异常长度拒绝和符号链接拒绝；仅使用自有 `/tmp` 测试目录，完成后清除自有测试文件。
- 新 observer 的 10 个自有消息样本与 544 个正常转发样本自检通过，没有真实相机或无线发送。
- 23079 项机内装载核心故障模型检查、6 类安装文件事务检查、6 类启动编排检查通过。离线及自检不代表实际冷启动通过。

## 下次开机预期

原厂服务第一次启动即调用新版 wrapper，加载合包界面。界面显示装载状态，待 UI/回放校验、AF 与 HFS1 机内串行装载及设置恢复完成后开放使用。设置修改保存到相机 `/media/data/hbl-four-module/settings.bin`。

需由用户正常关机再开机，然后只读核对启动状态、内存代码/入口、设置恢复与服务健康。该次验证尚未发生，不能把它记为已完成。不要重放 `install_persistent.py --run`，也不要在当前临时版运行期间通过手动重启消息服务来代替正常开机验证。

## 固定交付身份

- 包摘要：`d89ba33cc67fad823872939ee7c527b233c3d9b96e3f74044e79e8836662a5d9`
- 包内清单摘要：`59fe1bb52519ae428abcf35be711dd2e78d9d10e007f11b69f2a22e43a55997c`
- 原始安装记录：`build/persistent-install/installation.json`
- 前后内存核验：`build/persistent-install/preservation-before.json`、`preservation-after.json`
- 相机安装脚本原始日志：`/tmp/hbl-persistent-r1/install.log`

启动未完成时，先读取相机 `/run/hbl-four-module/boot-loader.status`、`coordinator.log` 及 `/media/data/hbl-four-module` 中本模块记录。部分写入或未知 SGI 完成状态禁止盲目重试、自动服务重启或直接删除未完成标记；须按实际阶段独立核对。原厂服务二进制、引导器和升级链均未覆盖。
