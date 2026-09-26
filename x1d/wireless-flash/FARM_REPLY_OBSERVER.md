# FARM 回复旁听候选

记录日期：2026-09-10，北京时间。用户仍在与本任务一起核对第一行／最后一行开始积分和传感器清空／复位相关候选；此组件解决的是后续观察数据怎样进入机内自有程序的问题，不能替代物理时序证据。

**2026-09-11 已在相机原厂 Qt 环境中通过独立合成报文自检，检查进程正常退出，临时目录已清理。尚未挂接真实消息服务，也没有取得实际 FARM 回复或验证感光边沿。** 原无线安装包和此前停用的四条软件通知未改动。

## 为什么这是一条新的入口

官方 X1D 1.25.0 wedge 的 `msg2dbus` SHA-256 为：

`988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1`

`MessageIO_Interface::ReceiveMessage(QByteArray)` 位于 `0x54f60`，在 `0x54f90` 调用外部导入的 `QMetaObject::activate(QObject*,const QMetaObject*,int,void**)`。其元对象地址为 `0x7e32c`，该信号的局部编号是 0，参数是 `QByteArray`。原调用把原字节数组对象指针放在 `arguments[1]`。

`MessageIO_Interface::staticMetaObject` 是动态符号表中的全局、默认可见对象；上述 `activate` 重载是未定义的外部动态导入。因此当前候选观察的是这个外部调用，而非试图覆盖原程序内部直接调用的 `ReceiveMessage` 本身。该区分已由 ELF 动态符号和 ARM 指令核对，动态加载效果仍须实际检查。

`AppsMessage` 的 `0x2194c` 检查至少四字节头，`0x219d0` 读取低端序命令字，`0x21a80`、`0x21a54` 分别读来源和目的字节，`0x2197c` 把数据起点移过四字节头。候选只识别完整九字节的成功寄存器读取回复：

```text
F5 00 01 05  vv vv vv vv  00
命令       FARM→iMX      四字节值     成功状态
```

USB 工具使用目的 8；本候选只接受目的 5，不采集发给 USB 的回复，也不启动另一套串口客户端。

## 候选的行为

- [native/farm_reply_observer.cpp](native/farm_reply_observer.cpp) 仅在元对象、信号编号、长度、命令、来源、目的及成功状态全部符合时提取四字节值。所有信号仍用原 sender、元对象及参数调用原 Qt 分发一次；自有输出放在原分发之后，并保留调用前及原分发返回后的 `errno` 语义。
- 默认没有观察输出。明确启用后，只连接自有 `/tmp/hbl-wireless-flash/farm-reply.sock`；父目录须为当前用户所有且权限 0700，接收 socket 须为同一用户所有且权限 0600。组件不创建目录、服务或接收 socket。
- 输出是固定 24 字节的自有报文，包含版本、进程序号、四字节值和 Linux `CLOCK_MONOTONIC` 读值。时间发生在原 Qt 分发之后，**不是 FARM 时间戳、传感器积分时刻或无线发射时刻**。原回复没有地址或事务号；未来读取端仍需独占、串行关联请求，不能把序号当作原协议事务标识。
- 非阻塞发送失败就停止输出，没有重试、重连、补发或相机控制。组件没有 FARM 请求、写寄存器、曝光、对焦、闪光或无线发射入口。
- 原 Qt 函数解析失败会拒绝该进程启动，不能静默吞掉所有 Qt 信号。为避免直接影响通信服务，必须先用下述独立检查程序验证相同的动态加载环境；目前尚未把库加入真实服务。

## 已做与未做的验证

[research/build_farm_reply_observer.py](research/build_farm_reply_observer.py) 只在 `build/farm-reply-observer` 输出独立产物，没有改写原 `build/manifest.json` 或安装脚本。使用 Qt 5.5.1 头文件、原厂 ARM32 库和 glibc 2.22 目标；编译时校验 Qt 版本及指针、`QByteArray` 大小。两个 ELF 均禁止未解析符号，并检查旧加载器所需的 REL/JMPREL 连续性。

[CodeTests/farm_reply_wire.test.c](CodeTests/farm_reply_wire.test.c) 已在电脑上实际运行：成功报文、十种错误长度、五处头／状态错误、空指针和固定报文编码／边界哨兵检查均通过。该检查不调用 Qt，不等于旁听器已在真实消息程序里工作。

[native/farm_reply_hook_check.cpp](native/farm_reply_hook_check.cpp) 已在机内独立运行通过。它只创建自有 Qt 对象和合成字节数组，不使用 DBus、串口、相机对象或网络。三条有效回复被识别、十五条无效报文被忽略，同时十八次原接收信号和一次状态信号继续送达原连接，字节数组保持不变。自检模式优先于输出开关，不打开输出 socket。**通过的是独立对象上的动态加载与 Qt 转发，未覆盖真实消息进程或 socket 输出。**

来源、产物哈希和电脑端检查见 [build/farm-reply-observer/validation.json](build/farm-reply-observer/validation.json)，机内本轮结果另存 [target-check-20260911.json](build/farm-reply-observer/target-check-20260911.json)。尚缺 socket 输出验证、严格关联请求的读取端、真实服务挂接与恢复验证，以及本次感光事件的物理对应；没有把候选标为可用的引闪通路。

## 独立自检包与本轮执行

[research/package_farm_reply_check.py](research/package_farm_reply_check.py) 已生成独立包 `build/farm-reply-observer/selfcheck-package.tar.gz`，不改原安装包。归档仅含两个自有 ELF 和 `run.sh`，三项均是无路径分隔符的普通文件，权限 0700，已重新打开归档逐字节核对。

运行脚本限定到由本次检查程序哈希命名的自有 `/tmp` 目录，要求目录属于当前用户且权限 0700；执行前固定核对两个自有文件和五个原厂运行库哈希。它只给自有检查进程设置预加载，并强制 `SELFTEST=1`、`OBSERVE=0`。检查程序在 `main` 开始设置自身的五秒 `SIGALRM`，没有修改相机或 FARM 计时器；该闹钟不覆盖进入 `main` 前的加载阶段。没有重启原服务、安装到原消息进程、请求寄存器、拍摄、对焦或发射。

本次实际执行的检查程序为 14096 字节、SHA-256 `d58ba355574f010b2ab1a0d166dea63cf0c4e1548be03e2ce7c51f7324912de1`；旁听库为 5920 字节、SHA-256 `3afe6b4012cb3acd1fbebb4860857c2623adb4bcec803d64c06a467a3cb94da4`。包清单与限制见 [build/farm-reply-observer/selfcheck-package.json](build/farm-reply-observer/selfcheck-package.json)，其中离线准备状态保留为构建时记录。

用户确认相机开机并连接电脑、对焦任务明确释放设备后，上传包哈希与本地相符，运行脚本的两个自有文件及五个原厂库校验全部通过。实际输出为 `valid=3 rejected=15 forwarded=18 status=1 hardware=0`，退出码 0。最后按固定文件名删除本轮六个临时文件，移除独立目录并核对不存在；没有挂到 `msg2dbus` 或重启原服务。

上传、校验、运行与清理累计 100 次 USB 命令请求、100 个匹配回包，全部句柄关闭。输出中的 `hardware=0` 指独立检查程序没有相机控制入口，**不能用它把本轮 USB 传输记成零**；本轮 FARM 内存／寄存器请求、拍摄、对焦及无线提交均为零。
