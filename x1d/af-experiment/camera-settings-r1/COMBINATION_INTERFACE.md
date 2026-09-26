# 主任务组合接口（离线候选已就绪，现场待验收）

- `compose_resources.compose(files)` 返回复制后的资源字典，仅增加 `/af-settings/SettingsPage.qml`，不改其他资源。最终 RCC 由主任务唯一构建和注册。
- 页面 `pageActive` 控制查询生命周期，`backRequested()` 交给主导航处理；主任务将其接入最终导航。页面本身不调用 Camera、快门、闪光或对焦接口。
- GUI preload：`linux-build/libhbl-af-ui.so`，环境 `HBL_AF_SETTINGS_ENABLE=1`，通过 `RTLD_NEXT` 链接原来的 `QQmlApplicationEngine::load`。只提供 `hblAf` 上下文对象，不自行注册资源。
- `msg2dbus-farm` preload：`linux-build/libhbl-af-bus.so`，同一环境开关，链式转发原来的 `QMetaObject::activate`。只在已有 `MessageIO_Interface` 活动后于该对象线程创建配置端点，通过 `SendMessage(QByteArray)` 使用已有通道，不创建另一条串口连接。
- 所需目录 `/tmp/hbl-af-settings` 由最终安装器建立，当前 uid 所有、0700；本模块分别绑定 `ui.sock` 与 `backend.sock`（0600），拒绝覆盖已存在端点。正常退出删除自己绑定的端点；异常退出后的清理由主任务在确认旧进程已退出后执行。
- 本地端点校验发送者 uid、固定 pathname、精确长度与内容校验；配置有 session/sequence 回显、revision 冲突检查，apply 不自动重发，查询仅在页面显示期间运行。
- FARM 候选在既有12点外增加 `0x1e22b4` 配置分发、`0x1a0498` near端点入口，共14点；仅远端优先且无判向结论、far已到达、当前正向near运动时收束第二段。输出超过已装16 KiB区域，需要新的独立分配与完整升级事务。不能原地覆盖旧分配，不能重跑旧 `native_loader.py install`。
- 新健康窗口固定在 `/tmp/hbl-x1d-combined/install-state`，20 分钟一次性 deadline/pulse/release。Linux 健康程序为 `/tmp/hbl-x1d-combined/system-check`，阶段接口 `--require-ui-stage`、`--require-held-min-ms N`、`--require-active`。`settings_hold.py` 已绑定最终 checker 的哈希及精确输出；最低剩余 180000 ms，不复用旧 formal hold。详见 `INSTALL_HANDOFF.md`。
- AF 两库的目录/端点权限检查采用目标 ARM32 glibc 2.22 的 `__lxstat64(3, ...)`，104 字节对齐缓冲，mode/uid 偏移分别为 16/24；禁止用现代交叉编译头的 `struct stat` 解释目标结果。构建器检查最终导入符号并记录 ABI。目标 IPC 仍需主任务现场验收。

最新参数与页面以 `PARAMETER_CONTRACT.md` 为准：三个速度默认跟随原厂；两个独立绝对提前量按快扫/精扫分组；切档恢复目标档预设；抗噪判向默认关闭。当前 ABI 为 3，原 ABI 2 页面/库不可混用。

已完成：ARM 配置/阶段命令/持续滚动判向、远端优先及有限折返离线测试；两个 Qt 库交叉编译；18张实拍衍生输入及48组局部判向检查；桌面页面渲染和交互；首次安装/历史升级及完整回滚的模型路径。两个提前动作尚未接通，不能把保存成功或交叉编译等同机内验收。最终导航、目标 Qt/IPC 及更新后的完整安装报告仍待核对。
