# X1D 首次开机加载独立 QML 按钮的方法

本记录对应第一代 X1D-50c，分析及实际 GUI 基线为官方 1.25.0。2026-09-13 已完成独立临时装载、持久文件安装，以及用户正常关机再开机后按钮仍可见的一次验收。不是 X2D 方案，也不代表四模块合包、打印或长期稳定性已完成。

**当前状态：已按用户要求卸载并通过卸载后的重启核验。** 以下加载链路是已验证的方法记录；相机现在没有该按钮、本体或自启覆盖。本地方法与冻结工件保留，后续使用按当轮授权重新验证。

## 目标与实际改动

在设置的 Wi-Fi 页面底部显示 `Persistence test` 空按钮。仅有按压外观，无点击动作，不新增相机设置、照片读取、拍摄或联网操作。

原厂 `/usr/bin/victory-gui` 保持原文件。只增加独立补丁目录和一份 systemd drop-in。持久补丁存于系统根分区，避免依赖排在 GUI 之后挂载的 `/media/data`，因此不用先启动原厂 GUI 再重启一次来加载。

## 加载链路

1. 正常开机，systemd 读取原厂 `victory-gui.service`，再读取 `/etc/systemd/system/victory-gui.service.d/91-hbl-wifi-probe.conf`。
2. drop-in 只清空并重设 `ExecStart`，指向 `/bin/sh /opt/hbl-wifi-probe-v1/launch.sh`；其余原厂环境、调度优先级、Wayland 参数和 `ExecStartPost` 保留。
3. `launch.sh` 原子创建 `/run/hbl-wifi-probe`。此目录是本次开机仅尝试一次的标记；如果已存在，本次启动直接执行原厂 GUI。
4. 核验本包清单，以及原厂 GUI、Qt 和依赖库的固定摘要。校验失败直接执行原厂 GUI，不注入补丁。
5. 将加载库、RCC 和健康检查器复制到运行期目录，然后以单次进程环境 `HBL_WIFI_PROBE=1` 和 `LD_PRELOAD` 启动原厂 GUI。没有改全局 `/etc/ld.so.preload`。
6. ARM 注册库在固定原厂资源表注册时先注册独立 RCC，再调用原厂资源注册函数。只覆盖 `/settings/SettingsGeneric.qml`；Wi-Fi 页面用 `itemValues === "generalSettingsWiFi"` 控制按钮可见性。
7. 保留原厂 QML 根对象与业务上下文，检查生效资源摘要和目标 Qt 的页面编译；成功记录绑定当前 GUI PID。
8. 有限监护核对当前服务 PID 和连续三份健康快照，状态稳定后退出。成功标记和库映射用于实机回读，不能单独替代用户看到按钮的验证。

原厂 GUI 固定 SHA-256 为 `d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`；资源表地址 `0x1ec7f0` 仅绑定这一份非 PIE 程序，不能套用其他固件。

## 状态检查与本轮修正

沿用已有独立 UI 装载器的两种一致状态：Active 为 system2/power0，稳定 Standby 为 system4/power1；SUC、FARM、PWR 三条链路状态必须全部为0，GUI PID 连续一致。查询禁用服务自动启动，不设置唤醒、安装保持或心跳。

本轮早期版本错误地只接受 Active，并在首份健康检查失败后立即撤回，造成不必要的唤醒要求和过早失败。修订版恢复上述原有条件，允许有限时间内的启动过渡，但仍拒绝混合态和链路异常。第二次实机装载实际记录到 UI 状态尚未完成、system4/power0，随后才稳定到 system2/power0。

GUI 重启仍会执行原厂初始化，不能把这一步称为完全无副作用。仅菜单操作不需要持续实时取景。

## 持久文件安装

先临时验证同一份代码，再执行 `persist.sh install` 的固定文件事务：

- 校验包、原厂基线、健康状态、无其他 GUI 覆盖，以及目标路径不存在。
- 根分区原本为只读；只在文件事务期间正常 remount 为可写。如果拒绝则停止，不修改安全机制。
- 在独立 `.installing` 目录复制并校验完整内容，然后改名为正式目录。
- 最后原子放入启动 drop-in，确保不会先启用一个未复制完的包。
- `sync` 后恢复根分区只读，再次校验持久文件。

本轮新增 `/opt` 及 `/opt/hbl-wifi-probe-v1`，新增 `/etc/systemd/system/victory-gui.service.d` 及其唯一探针配置。没有替换原厂程序、原厂 unit、内核、引导器或控制器固件，没有制作 CIM。安装操作未重启当前 GUI 或设备，下一次用户正常开机才采用新入口。

已安装的冻结包与临时验收包相同，清单见 `build/packages/1e2171827553e3846/package.json`。后续修改应生成新候选并重新验证，不在已冻结包或已装文件上直接改写。

## 回退与卸载

- 校验失败：启动器直接运行原厂 GUI。
- 加载失败或健康状态在时限内未稳定：有限监护请求重启 GUI；运行期的一次尝试标记仍在，下一次 GUI 启动直接走原厂，避免本次开机内反复注入。
- GUI 自身退出：原厂 `Restart=always` 再启动时同样遇到一次尝试标记，从而走原厂。
- 持久安装失败：只处理本事务创建、且仍符合本包内容的路径，并恢复根分区只读；不删除其他模块或目录。
- 卸载：经用户要求后，从独立临时副本执行已校验的 `persist.sh remove`，移除精确匹配的持久 drop-in 和本包文件，恢复只读。该文件事务不会自行终止当前 GUI，当前会话是否重载/重启另按当次要求处理。

回退设计不等于所有系统故障都可恢复。本轮已验证离线失败分支和第一次临时装载自动恢复原厂，未故意在持久开机过程中制造故障。若固件后来改变，摘要门禁会阻止注入。

## 验收证据

用户确认安装后正常关机再开启，Wi-Fi 页面底部按钮仍在。实读的新启动标识与安装时不同；持久 drop-in 已生效，同一份库映射到当前 GUI，页面就绪和健康标记绑定同一 PID，没有失败回退标记，五项服务均 active，根分区仍为只读。

详细事件与限制见 `README.md`；汇总见 `build/persistent-install-result.json`；原始受限设备证据见 `build/sessions/`。记录不包含序列号、照片或密钥。

## 清理与最终卸载

用户要求清理后，逐项检查了本轮四个 `/tmp/hbl-wifi-probe-stage*` 暂存目录及 `/run/hbl-wifi-probe-temporary-evidence`，均已随重启消失，无需再执行删除。

上述第一次清理仅针对暂存，仍保留持久插件，与用户实际意图不符。用户进一步明确要求删除测试按钮和自启后，已从独立暂存副本执行 `persist.sh remove`，校验移除持久本体和 drop-in、恢复根分区只读，随后重载服务配置并恢复原厂 GUI。

用户再次手动重启并确认正常；最终实读 `/opt/hbl-wifi-probe-v1`、`/run/hbl-wifi-probe`、`/tmp/hbl-wifi-probe-stage-r4` 和持久 drop-in 均不存在，GUI active 且无 DropInPaths，根 ext4 为 ro。证据见 `build/sessions/uninstalled-after-reboot-20260913T091818121824Z.json`。没有删除共享父目录或本地方法、源码及验收记录。
