# AF bus 启动发现修正 r2

## 结论与证据边界

主任务现场报告：旧 AF bus 已映射、环境开关正确、服务 active，但 10 秒后仍无 backend.sock；UI 与健康保持正常，AF/FARM 写入为 0。旧实现没有阶段结果，因此不能仅凭这些现象唯一确定是未捕获对象、排队未执行还是 bind 失败。

离线确认的缺口是：旧版仅在 `ReceiveMessage` 或 `InterfaceStatusChanged` 发信号后发现 owner，没有无流量启动保证。固定 X1D 1.25.0 `msg2dbus`（SHA-256 `988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1`）中，`0x1c218` 在状态未变化时不发状态信号。因此把缺少端点直接认定为构造器 dlsym 时机错误并不成立。

已逐项核对：

- `_ZN19MessageIO_Interface16staticMetaObjectE` 动态导出于 `0x7e32c`，符号拼写正确；UART meta 位于 `0x7e418`，继承前者。
- 两个 meta 都有 `SendMessage(QByteArray)` slot，参数类型编号 12 为 QByteArray，返回类型编号 1 为 bool；返回 bool 不属于签名字符串，不导致 `indexOfSlot` 失败。
- 原厂 UART 构造函数 `0x1cb74` 先在 `0x1cbb4` 设置 UART vtable，再于 `0x1cd58` 以 UART 为 receiver、`0x1cde8` 以 UART 为 sender 调用 `QObject::connectImpl` 的 PLT `0x18720`。发现对象不必等待消息或状态变化。

## 可审查改动

只有本目录的新 `settings_bus.cpp` 和独立库改变运行行为，旧源码、旧 bus、UI/QML/FARM、原 AF-only 报告均保留。

1. 链式转发已有 `QObject::connectImpl`，参数、Connection 返回和 errno 保持一致；从原连接的 receiver/sender 识别精确的 `MessageIO_UART` meta。没有遍历全局 QObject 树、创建另一个 MessageIO、初始化串口或发送消息。
2. 原连接成功且 QPointer 仍有效后，在真实 owner 的线程排队创建端点。保留原信号入口作后备；原子 owner 选择防止重复初始化，destroyed 连接释放选择，Qt 的 owner 上下文取消已销毁对象的排队回调。
3. meta 可在已有连接调用时重新解析；构造器过早返回 null 不会永久禁用发现。没有猜测静态地址或绕过类型检查。
4. 私有目录内增加 `backend-r2.status`，记录 `loaded/disabled`、`owner-found`、`queued`、`binding`、`ready`、`bind-failed`、`slot-missing`、`wrong-thread`、`owner-destroyed`，以及 errno、meta/uart 是否解析成功。只含阶段，不含设备标识或消息内容。失败后不自动重启、不自动覆盖已有 socket。

代价是多拦截一个固定 Qt 5.5.1 内部 ABI 的连接函数，并新增一条 destroyed 连接、一个 owner 上下文排队回调和少量阶段文件写入。此构建仍只支持已核对的 ARM32 Qt 5.5.1；不能推广至其他 Qt 版本。真实事件循环和 bind 还需现场验收。

## 构建和验证

`build_bus.py` 只构建新 bus；沿用固定 ARM stat64 ABI 和旧 loader 的连续重定位布局。新库：

`linux-build/libhbl-af-bus.so`，19968 字节，SHA-256 `35bd67c30ac7c95883db0392ec4ce0f2b0cbe6094a1698f01085dda8f7d26ca5`。

`../CodeTests/test_bus_startup_r2.py` 的 6 项检查通过，包括固定原厂 meta/slot/连接调用点、真实 ARM interposer 的隐藏返回参数及全部栈参数转发、errno、无信号发现、无关对象、原连接失败、转发中 owner 销毁和重复连接。Qt 与文件系统为替身；测试没有运行真实事件循环、创建真实端点或发送设备消息，不能当作现场成功。

## 主任务交接

主任务只替换 AF bus 文件，UI 继续使用 `../linux-build/libhbl-af-ui.so`（SHA-256 `89453190d2039f4e3440a875dc8f682f41d1bdd35ae4de3ed393cfa5e110f825`）。本任务不执行设备替换或服务重启。现场可读取 `/tmp/hbl-af-settings/backend-r2.status` 区分阶段；只有 `ready` 与真实 backend.sock 同时存在才表明端点创建完成，消息往返另行验收。

后续 AF 首次/回滚使用附加源绑定入口 `../af_only_bus_r2_loader.py`，动作仍为 `report`、`first-install`、`rollback --journal`。它复用原 AF-only 事务和独立恢复目录，绑定新 `../build/af-only-bus-r2-validation.json`：SHA-256 `5da79be7c090edabe8951c854f2c43ae54885fcec83962948305c57b85f1219b`。报告同时绑定旧 AF-only 报告 `c834f941…`、旧冻结来源、新源码/库/构建/测试证据，保留可追溯性。

配置、速度、远端优先、原厂精扫和两个提前量尚未接通的语义不变。全程 0 设备请求。
