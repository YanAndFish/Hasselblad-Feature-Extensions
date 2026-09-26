# X1D 持久化 Wi-Fi 空按钮探针

做法、启动链路、安装事务、回退及清理说明见 [PERSISTENCE_METHOD.md](PERSISTENCE_METHOD.md)。

2026-09-13 用户明确要求先试持久化小测试：第一代 X1D 设置的 Wi-Fi 页增加无操作按钮，关机再开机后仍在。当前任务限定于本目录内准备、验证和该探针；不涉及四包合并、打印、照片访问或 X2D。

状态：**独立空按钮探针的开机首次加载与关机重开验收通过，随后已按用户要求完整卸载。** 卸载后用户再次重启并确认正常，实读验证持久本体、启动覆盖和运行期暂存均不存在，原厂 GUI active、根分区只读。本地源码、冻结包和方法记录保留。此前用户明确确认安装状态下关机再开启后按钮仍在；该历史成功不代表当前仍安装。用户尚未逐项描述按钮点击/返回测试，不把“看到了”扩张为全部交互验收。参考基线为 X1D-50c 1.25.0；本轮实机 GUI SHA-256 与固定基线一致。

参考固件根分区默认只读；media-data.mount 排在 victory-gui.service 后面。不能直接令原厂 GUI 等待该挂载，避免形成启动依赖环。用户已明确选用首次 GUI 启动即加载，并同意在验证后修改只读系统分区的少量独立文件。本轮曾将本包放入 /opt/hbl-wifi-probe-v1，通过独立 GUI drop-in 接入原厂启动；现已卸载。该做法不依赖 data 分区，不改引导器或制作整包固件。

验收须分开记录：本地构建和界面验证、临时实机验证、持久安装、用户物理关机再开机后的按钮与健康检查。未经过的步骤不得标完成。失败回退机制须在持久安装前验证。

## 本轮记录

- 原厂 GUI 未替换；起始五项服务 active，DropInPaths 为空，根 ext4 为只读，/media/data 为可写。
- 初次暂存包被前检拦截：生成文件含 Windows 换行。未重启 GUI。已修正 Linux 载荷为 LF，并增加字节一致检查。
- 第一次真正临时装载：资源和目标 Qt 页面编译已通过，但启动后健康检查失败；保护流程撤回本包，实读原厂 GUI 恢复运行、DropInPaths 为空、原厂哈希未变。第一次监护未记录足够状态，不能断言其精确根因。
- r3 包只暂存，未执行 GUI 装载。原先过严的 Active-only 条件错误拒绝稳定 Standby，用户指出后，恢复已存在的独立 UI 装载标准：Active(system2/power0) 或稳定 Standby(system4/power1)，三链为0，连续三份状态与 GUI PID 一致；混合态和异常链路仍拒绝。不主动发唤醒或保持请求。
- 第二次实际临时装载使用 r4 包：启动日志出现未完成的 UI 状态和 system4/power0 混合态，随后在第三轮得到 system2/power0；有限等待后装载成功。独立 status 复核通过，五项服务 active，总线 PID 未变。
- 当前包 SHA-256：1e2171827553e3846abe15c5cfe21e75a97a4234cff34ade8cd0ebdbfb7455b6。冻结归档位于 build/packages/1e2171827553e3846/。
- 临时装载时相机暂存为 /tmp/hbl-wifi-probe-stage-r4；运行期状态为 /run/hbl-wifi-probe；临时 drop-in 为 /run/systemd/system/victory-gui.service.d/91-hbl-wifi-probe.conf。首次失败现场曾保留在 /run/hbl-wifi-probe-temporary-evidence；用户重启后这些临时内容已确认消失。
- 设备证据在 build/sessions/；离线 UI、启动保护、事务、传输证据在 build/*validation.json。未访问照片，未拍摄、对焦或试闪。

## 持久安装结果

用户确认临时按钮可见，主动重启后再次明确要求做成开机启动。重新核验原厂哈希、无临时覆盖、只读根分区和空间后，重新暂存同一固定包。

本轮持久改动仅为新建 /opt（原先不存在）、其下 hbl-wifi-probe-v1 独立目录，以及 /etc/systemd/system/victory-gui.service.d/91-hbl-wifi-probe.conf。未替换 /usr/bin/victory-gui 或原厂 service unit，没有改 bootloader、内核、data 分区或相机设置。

persist.sh 先校验固定包及原厂文件，在根分区短暂可写期间复制并校验完整目录，最后原子放入独立启动配置，sync 后恢复只读并再次核验。安装过程未 daemon-reload、未重启 GUI 或整机。安装后原 GUI PID 与安装前相同，仍 active。

- 持久包仍为临时验收的冻结包：1e2171827553e3846abe15c5cfe21e75a97a4234cff34ade8cd0ebdbfb7455b6。
- 持久事务脚本 SHA-256：8a790c3e533f4f26e916624c756f9bc48090a44c4512d8f68a53c5ce1874238c。
- 7 项实际脚本隔离事务测试通过：安装/移除、复制失败、启用文件失败、恢复只读失败、拒绝可写重挂、已有外来目录、卸载前文件被修改。服务、挂载、权限元数据为替身，不当成实机故障恢复保证。
- 实机安装返回 persistent-files-installed-next-boot，独立 status 返回 persistent-files-verified-root-readonly；实读根 ext4 为 ro，原厂 GUI 哈希不变。
- 安装时启动标识摘要为 7e6a6720f3f92095662bc352386c25032f2124175dc0b1d71668f4ba35382f49。下一次核验应确认该摘要变化；它不是相机序列号。
- 安装后用户正常关机再开机，明确反馈底部按钮仍在；本探针的跨关机显示已验收，详见下节。

启动时先核验固定包与原厂基线，再直接以补丁启动第一份 GUI；同次开机再次启动则绕过补丁。有限监护等状态一致后退出；异常时请求原厂 GUI 重启一次。这个保护已离线验证，第一次临时装载的自动撤回也已实测；不能保证覆盖所有系统或存储故障。

## 当前入口

`python -X utf8 -B x1d/candidates/persistent-wifi-button/session.py` 默认离线；--phase status 只核验本包，--phase restore 撤回本包运行期 GUI 覆盖。所有实机入口仍须符合当轮授权，阶段结果不明时只观察，不重复装载。已有 r4 temporary 阶段已经执行成功，不能再次派发。

`persist_session.py --status` 校验已安装文件及根分区只读。`--remove` 仅在获得卸载要求后，从已验证的独立临时副本撤下精确匹配的持久文件；它不停止当前 GUI，后续是否重载或重启按当轮要求处理。安装/卸载结果不明时不得重放。

## 安装后关机再开机验收

- 用户先反馈相机能够启动，随后明确确认“关机再开启之后，下面那个图标在了”。
- 启动标识摘要变为 39d31470c5d68cdbc7b267c74b58ee0737bbefb03c4e163561a98ea4afefeb07，与安装时不同，证明不是沿用旧运行期。
- 当前 GUI 从持久 drop-in 进入，PID 206；ui.status 与 verified 均绑定这个 PID。
- /run/hbl-wifi-probe/libhbl-wifi-probe.so 的摘要仍为临时测试通过的 0cc9447833dbd6d3d0a7748665fa7524886519f5a6f10243a2b65b04c214cf68，并确实映射到当前 GUI 进程。
- 没有 fallback.reason；独立三份健康检查得到 system2/power0，五项相关服务全部 active；持久文件和根分区只读检查通过。
- 证据见 build/sessions/persistent-cold-boot-readback-* 及 build/persistent-install-result.json。

已完成的是这个独立无操作按钮的正常开机自动加载和一次关机重开验证。四模块合并、四模块持久化、打印功能、长期稳定性和所有故障恢复情况均不在本次完成声明内。保留原厂 GUI，不自动继续其他相机施工。

## 按用户要求卸载并重启验证

最初将“清理临时包”理解为只清暂存、保留持久按钮，与用户意图不符。用户指出重启后按钮仍在后，明确同意撤掉测试按钮及其自启配置。已从独立临时副本执行校验后的卸载事务，移除持久包和启动覆盖，恢复根分区只读，再重载服务配置并重启一次原厂 GUI。

用户随后手动重启并确认按钮消失、启动正常。最终只读核验确认 `/opt/hbl-wifi-probe-v1`、`/run/hbl-wifi-probe`、`/tmp/hbl-wifi-probe-stage-r4` 和持久 drop-in 均不存在，GUI 为 active 且 DropInPaths 为空，根 ext4 为 ro。证据为 `build/sessions/uninstalled-after-reboot-20260913T091818121824Z.json`。共享父目录未清除；本地方法、源码与历史验收证据保留。
