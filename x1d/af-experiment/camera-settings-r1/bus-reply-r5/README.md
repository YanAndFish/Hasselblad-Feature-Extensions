# AF 回包线程交付修复 r5

固定对象：X1D 1.25.0、现有 delivery-r5 与已经应用的 bus-transport-r4。新目录独立冻结，旧交付包与 r4 证据保持原样。

## 证据与变更

实机 r4 用户一次读取的匿名计数为：private=returned=ok=rx784size=rx784owner=rx784queued=1，而 farm=0、expired=1。说明回复已抵达 ReceiveMessage 入口并进入旧投递分支，丢失发生在 Bus::reply 之前。

固定 Qt 5.5.1 二进制中，singleShotImpl 构造路径先在调用线程 startTimer，后迁移到接收线程。原厂接收回调来自 pthread；缺少调用线程事件分派器可能使这条路径无法投递。此为静态原因推断，未把 timer 返回零记为实测事实。

修复采用 QCoreApplication::postEvent 将自有 ReplyEvent 直接发给已有 Bus 的 Qt 线程。受 pthread mutex 保护的注册指针避免从回调线程搜索 QObject 子对象；析构先注销，入队在锁内完成。最多四个待交付事件，超限只记匿名计数。接收者 event 调用既有 reply 校验，保持 259 字节、magic、版本、op、session、sequence、hash 与两秒超时约束。

未改变原厂 activate 参数和次数、原厂 transport 返回值与 errno、AF 算法、GUI、FARM RAM 补丁。新增 eventhandled/eventmissing/eventfull 计数，不记录报文、设备身份或照片。

## 离线验证与实机边界

真实 Bus 源码在宿主替身环境执行，包含普通 std::thread（无 Qt dispatcher）入队、接收者事件交付、错误 owner、队列上限、析构注销及原有校验。实际 ARM 库执行原厂转发/返回值与启动 ABI 测试。Qt 事件队列和 OS 为替身；离线通过不等于实机读取成功。

安装脚本绑定 delivery-r5 manifest 与 r4 manifest、r4 已应用标记、原 90+95 drop-in、GUI PID、库映射和状态。只增加 96-hbl-af-bus-r5.conf 并重启 msg2dbus-farm。失败或显式 restore 只删除 96，恢复 r4；不重启 GUI，不写 AF RAM，不发送 AF query/apply。原服务正常打开 UART 的启动副作用包含在当前 AF 修复安装授权内。

执行入口：main.py 默认 report 离线校验；stage、apply、restore 仅由当前获独占授权的 AF 任务执行。observe.py 只读匿名服务/状态计数。实际安装及用户手动读取结果另记 INSTALLATION_RECORD_20260913.md；冻结时 physicalRoundtripVerified=false。
