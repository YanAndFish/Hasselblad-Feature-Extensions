# 常驻前键预览的开机装载核对

2026-09-24；对象第一代 X2D，4.2.0。用户选择开机自动装载、不依赖电脑。本轮仅执行针对启动链的读取，没有新增持久相机文件、修改分区挂载或开启 ADB。

## 实机读取

- 当前 `/system`、`/vendor` 为只读 ext4；`/data` 和 `/blackbox` 可写并持久保存。
- 原厂 `start_dji_system` 服务执行 `/system/bin/start_dji_system.sh`，为 oneshot。脚本末段检查 `/data/aging_test.sh`，存在时用 `nohup` 直接执行该文件。
- 当前 `/data/aging_test.sh` 不存在，没有覆盖现有文件。
- 原厂脚本带 `start_dji_system_exec` 标签，原厂策略从 init 转入 `start_dji_system` 域。不能把它与当前 USB shell 的 `hbl_camera_service` 域视为相同。
- 当前 USB 功能组合不包含 ADB，`adbd` 为 stopped。原厂配置包含独立 ADB 功能组合和 root 服务标签，但尚未验证可用会话或重挂载能力。
- 原厂 `camera-test-mode` 只加载两个驱动，不读取自定义页面脚本，不是加载器入口。

## 官方策略静态证据

使用 `inspect_ui_load_permissions_4_2_0.py` 的哈希固定 CIL 输入和属性展开器检查：

- `start_dji_system` 对 `system_data_file` 有 `execute_no_trans`，没有 `execute`；缺少直接执行该类型脚本所需的完整许可。
- 该域对 `hbl_camera_service` 进程没有 `ptrace` 许可。当前加载器依赖 `/proc/<pid>/mem`，所以不能直接复用。
- 没有找到该域到原厂 GUI 域的进程类型转换，也没有找到该域 permissive 声明。
- 这是原厂固定策略静态证据，不是对正在运行内核策略的完整导出；当前通道读取 enforce 文件被拒绝。

## 未完成事项

没有安装自动启动。持久保存图片、脚本本身不能解决启动执行上下文问题。下一条候选是独立的 init 服务，但该候选涉及系统分区和启动校验，不能把“临时重挂载”解释为“写入会随重启消失”。

若继续该候选，应先在获授权的 USB 调试会话中只读核实权限、启动完整性配置和恢复入口；不关闭启动校验或 SELinux。正式实现还需包含版本校验、动态运行地址解析、就绪超时、失败退出、禁用标记、按键映射恢复及卸载清单。不能保存本次运行地址供下次启动复用。

现有临时驻留方案不受本轮核对影响；其安装证据见 `RESIDENT-PAGE-RESULT.md`。

## 后续：获授权的 USB ADB 只读核对

用户随后明确同意临时开启 USB 调试，仅核验，不写系统文件。

- 通过原厂已有 USB 功能组合临时加入 ADB，Windows 枚举出正常的 ADB Interface，使用 WinUSB 驱动，无驱动安装或替换。
- 使用本目录 `AdbUsbCheck.cs` 建立标准 ADB 连接，发送固定的只读查询。若收到 AUTH 则退出；不生成、猜测或传入认证凭据。没有调用 root 切换、remount、安装、重启服务。
- 实际会话返回 uid 0，SELinux 域为 `su`；这与原维护命令通道的 `hbl_camera_service` 域不同。两次查询均成功。
- `system` 和 `vendor` 仍为只读物理 ext4 挂载。
- 官方固定策略中 `su` 对 `system_file` 有写入许可，对 `labeledfs` 有 remount 许可，具备 sys_admin；这是候选安装路径的静态依据，没有实际验证可写重挂载。
- 读取 SELinux enforce 文件仍被拒绝；固定策略也只为 su 提供该类文件的 getattr，root 不代表不受 SELinux 限制。
- 常见 verified boot 属性、所筛选的内核启动校验字段没有返回值；没有找到所检查的 avbctl/vbmeta/dm 名称。缺失这些信息不能证明未启用启动完整性校验，不能据此承诺写系统后仍可正常启动。
- 临时切换脚本在相机自身计时后恢复原 USB 组合。第一次恢复已实测，原维护通道与常驻预览仍正常。

没有安装开机加载器，没有重挂载分区或改变启动校验、安全策略、原厂文件。ADB 联通只解决操作通道，尚未解决自动加载的完整安装与撤回验证。

工具协议参考：[Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)。官方工具下载遇到 TLS 连接失败，因此改用已安装 WinUSB 驱动上的固定只读 ADB 检查器；没有执行来路不明的下载程序。

第二次 ADB 查询后的自动恢复也已实测：USB 回到原组合、adbd stopped；常驻桥接 READY，主 GUI、预览 GUI、相机服务进程保持原实例。

## 原厂 GUI 加按钮：新增核对

用户进一步要求查看原厂界面加按钮的可行性。此项仍为读取和离线分析，没有安装新菜单项。

- 实机原厂主 GUI 命令行仍为原始 Wayland 全屏启动；`init.svc.camera-gui=running`，其环境没有 `LD_PRELOAD`。测试模式属性为零，独立测试 GUI 属性为空。原厂 GUI 文件哈希仍匹配基线。
- 用户截图描述的是另一轮停止主 GUI、预加载库后手动启动的行为。不能把截图中的回读直接当作本次相机现状。本次没有使用该启动方式。
- 静态重新核对 `GuiObjectImpl::setupOsdClock`（RVA `0xae32d8`）：读取配置偏移 `0x32`，为零时调用时钟设置分支。主 QML 的 OSDClock Loader 根据时钟状态启用。这支持截图有关未锁定分支显示时钟的局部解释，但没有复现截图所述事件因果。
- 原厂主页面仍为内嵌资源；`HblLoader.qml` 根据 active/source 设置或清空内部 Loader 来源，没有证明存在外部页面扩展入口。
- Wi-Fi 菜单由 C++ 菜单模型生成，不是单独的 Wi-Fi QML 文件。`_GLOBAL__sub_I_menux2d.cpp` 内 RVA `0x2a856c` 至 `0x2a85b0` 初始化 X2D 的 `wifiMenu`（RVA `0x21be540`）。复制步长 `0x130`，总源跨度 `0x980`，对应八个 MenuItem。
- 对当前主 GUI 的相应 QList 头进行只读回读，项数也是八。初始化结果与运行对象吻合；运行地址只限本次进程，不跨重启复用。
- `SubmenuDelegate.qml` 的点击走 `gotSelected()`。新增项必须确认类型、展示字段、无动作选择处理、对象生命周期及模型通知；不能只增大列表长度或复用一个会改设置的菜单项。

因此新增空按钮已有具体研究对象，但尚未完成候选构建、原厂页面刷新和实际点击验证。ADB root 并不自动解决这些问题。

开机方案同样仍未安装。进一步策略展开发现 `su` 对原厂 GUI 可执行类型没有直接文件许可，对主 GUI 进程也没有 ptrace 许可；原维护通道所在的 GUI 域反而具有同域内存访问许可。因此不能笼统把 root 调试描述为所有操作权限均更大。新启动服务还必须使用被允许的入口标签和运行域，不能直接把原 shell 加载器放进 init 就宣称成功。

## 继续核对：启动入口与加载器自身的缺口

本节为本地文件与官方镜像静态核对；没有新增相机操作。

- `/etc/init/camera-gui.rc` 的 `hbl.sutest_gui=1` 动作会停止 `camera-gui`，再启动 `camera-sutest-gui`。这只证明该专项测试入口的行为，**不等于用户照片中的 Debug Mode 菜单也通过这个入口打开**。照片中的菜单和开机服务需要分别追踪。
- 扫描 system、vendor 镜像 `/etc/init` 的直接配置文件，以及 system `/bin` 下的 shell 脚本，仍只在所筛选的持久脚本路径中找到前述 aging 钩子；本次扫描不是对全部二进制、递归目录和启动镜像的穷尽证明。
- 重新核对固定策略：init 可以执行 `hbl_camera_service_exec` 并转换到 GUI 域；GUI 域允许该类型作为入口。普通 `shell_exec`、`system_file` 对 GUI 域没有 entrypoint。因此仅给 shell 服务指定 GUI 域并不足够。未找到可直接用于新加载器的已允许安装路径与完整标签设置流程。
- 现有 `Install-ResidentPage.ps1` 在电脑上完成版本检查、预览进程启动、地址解析、写入及显示验证；它还读取旧 `/tmp/afmf-page-bridge/state.sh` 和图片，并要求旧桥接完成恢复。它不是相机独立开机安装器。
- 现有监听脚本从本次生成的 `state.sh` 取进程身份、按键节点和 mailbox 地址；输入设备暂固定为 `event6`。跨重启必须重新定位并校验，不能持久保存这些地址或假定设备编号固定。
- 开机版本还需要幂等启动、等待 GUI/显示服务及按键映射就绪、输入设备身份确认、版本不符即退出、禁用标记和卸载路径。恢复处理还应在终止预览前核验 PID 与启动时间，避免 PID 重用。

候选服务的职责仅是等待正常系统就绪、初始化独立预览及监听、管理退出恢复。现阶段既未形成可安装的服务入口，也未将电脑安装步骤完整迁入机内；没有安装或宣称开机自加载完成。

## 照片中的 Debug Mode：总开关与权限的区别

离线来源：同一官方 4.2.0 system.img。camera-gui 哈希沿用前述基线；camera-system SHA-256 为 `bf854a21881148565ff2cc00376426c37a2b82fed94c653abf024e23ed4ceda6`，camera-service 为 `fbcf828f73bca13f0c8b95e7dd0b95ac483ae36954ec06179098c8a1a65f9f82`。

- GUI 的 SystemProxyDbus 提供 `setDebug_mode` 和 `setDebug_options`；不是 USB ADB 配置的同名开关。
- camera-system 的 `SystemObject::setDebug_mode`（RVA `0x116f50`）检查一个相机状态后交给 `SystemSettings::setDebug_mode`（`0x110e98`），更新布尔字段并发出属性变更信号。本轮没有完整追完所有信号接收者，不能据此断言开关绝无其他副作用或持久性。
- `SystemObjectImpl::debug_options`（`0x7fc58`）给出了明确总开关语义：debug_mode 为 false 时返回 0，为 true 时返回已配置的 debug_options 位集合。打开总开关不等于自动全选所有项目。
- GUI Qt 元数据的 E_DebugOption 包含 EyeDetection=1、FaceDetection=2、Recalibrate=4、Touch=8、TouchPointerHandlers=16、Dcf=32、Browse=64。这是标志位，不是八级权限；Max 是枚举哨兵，不能当有效全开值。
- QML 的触摸调试读取该位集合；人脸调试影响指示图层及 ID 对应颜色。camera-service 的 `DCAMCaptureEngine::setDebugOptions`（`0x1e6548`）分别把人脸和眼部位传给检测调试设置，`MLControl::setDebugOptions`（`0x2236e8`）也设置内部标志和日志类别。
- 因此有依据将照片中的开关解释为诊断选项总开关；已检查链路没有 UID、SELinux 域或分区权限提升，不能作为“权限拉满”或解决开机加载权限的依据。各选项的完整作用还需分别核查；本轮没有开启任何相机调试选项。

## 运行启动配置的只读对照

继续获授权的窄范围 USB 读取，无配置写入、无 ADB 切换、无服务重启：

- `/init.rc` 的 post-fs 阶段已启动 camera-gui；early-boot 再启动 camera-system、存储及 start_dji_system。
- boot-sleep 有原厂一秒间隔，注释说明用于避免影响首次 liveview；boot 阶段启动 core，随后触发 boot-late 并启动 auxiliary。独立加载器如能解决安装与入口权限，宜使用后续辅助阶段，再自行检查必要对象是否就绪；class 启动不等于依赖已经 ready。
- 当前 `/init` 字符串包含 `/system/etc/init`、`/vendor/etc/init` 和 `/system/etc/mount/init.mount.rc`。这支持标准配置目录线索，但字符串本身不构成任意新配置可被加载、通过校验的实证。
- 原厂镜像 mount 配置有 system/system_2、vendor/vendor_2 和 normal/normal_2 双份分区映射。后续安装、更新兼容性与撤回必须考虑实际活动分区，不能笼统承诺一次写入永久生效；本轮没有修改任一分区。
- 最新读取为 camera-gui running、resident READY、adbd stopped。只说明本轮读取时相关状态正常。

下一关仍是独立服务的可用执行入口、文件标签与完整性条件。未找到可直接复用的、无需这些条件的持久自动加载接口，尚未安装。

## 获授权的只切换挂载测试

用户在明确询问“临时切为可写、随后立即只读，不写文件、不重启”后回复继续。本批仅扩大到此测试，未安装库或 init 配置。

- 先前两次请求均在前置状态检查失败退出，未执行 remount：ADB 域没有维护通道的 awk，调用 BusyBox 也被拒绝。只读检查确认 su 域访问 `/system/xbin/busybox` 得到 Permission denied；不能把维护通道工具可用性套用于 ADB。
- 改用 shell 内建读取 `/proc/mounts`，使用原厂 `/system/bin/mount` 和 `/system/bin/sleep`（均指向 toybox）。固定请求要求 uid 0、su 域、唯一预期活动 system_2 分区、ext4 且初始 ro。
- 命令内设 EXIT/HUP/INT/TERM 恢复，并启动机内五秒只读恢复看守。没有写测试文件，也没有重启服务。
- 实际返回：RW_COMMAND_RESULT=0；挂载从 `ro,seclabel,relatime,data=ordered` 变为 `rw,seclabel,relatime,data=ordered`，随后恢复原字符串，返回 RESTORED_EXACT。
- 此结果证明本次运行内核允许该分区重挂载，不证明修改内容后仍能通过下次启动校验，也不代表自启动模块已经加载。

后续真实库加载和 init 配置安装仍未执行；当前仍是独立诊断模块及配置候选。

## 最新状态：独立 init 开机诊断实机通过

后续用户分别授权诊断库加载和开机验证，并手动完整重启。详见本目录 `AUTOLOAD-PROBE-PLAN.md` 的实际结果，不再以以上历史段落的“未安装”作为当前状态。

已安装独立 `x2d-preview-probe` oneshot 服务，仅在 boot-late 使用原厂 camera-test 的版本参数加载专用诊断库，记录自身状态后退出。重启后、任何手动启动前，读取到 module_loaded=1、uid=root、secure=0、预期 hbl_camera_service 域；服务 stopped，主 GUI 和相机服务 running。系统挂载只读、原厂 GUI 哈希一致、ADB 关闭、USB 原组合。

这证明了本次活动分区的实际开机入口和模块装载；不代表完整按键/预览加载器完成，不代表其他固件或另一系统分区也通过。两份持久新增文件仍在，撤回脚本已准备。下一步需要将电脑端动态初始化移入机内，再验证 resident 预览及前键切换。

## 最新交付：完整开机预加载已验收

后续完整机内加载器已安装，独立诊断的两份系统文件已撤下。用户再次完整重启后，未手动启动任何程序即读取到加载器 running、READY、预览已创建、前键多次切换及实际隐藏状态；系统只读、原厂 GUI 哈希不变、ADB 关闭。用户明确确认开机和按键切换一切正常。

最终安装清单、版本绑定、初次启动显示限制、停用/卸载说明及各阶段证据见本目录 `BOOT-PREVIEW-RESULT.md` 和 `boot-preview-package.json`。本结论仅覆盖当前第一代 X2D 4.2.0 的活动分区；没有验证固件升级后自动兼容，也没有实现图片按钮触摸动作。
