# 第一代 X1D：源码范围与普通闪光入口

范围：官方 X1D-50c 1.25.0 的离线材料。本记录没有相机访问、试闪、设置修改或固件运行。文件哈希见 [baseline-manifest.json](baseline-manifest.json)。

目前不能以“有完整源码”为由认定 X1D 电子快门引闪比 X2D 更容易。可直接读到部分界面源码；产生曝光和闪光的原生组件及下层控制固件没有取得对应的完整工程。

| 材料 | 实际取得的内容 | 能用于什么 |
|---|---|---|
| 官方 1.24.0 GPL 归档 | 前轮实际枚举 70 个组件，包括 Qt、systemd、GStreamer、imx-lib 等；不是同版本的完整 1.25.0 工程 | 核对通用组件实现；不能重建哈苏曝光/JPEG/存储程序 |
| 1.25.0 `usr/bin/victory-gui` | ARM32 ELF，内嵌资源可解析为 137 份 QML、JS、配置文本 | 审查界面和部分业务逻辑；不含完整原生 GUI 工程 |
| `camera-daemon`、`jpeg-daemon`、`storage-daemon`、`configstore` | ARM32 ELF，动态符号、Qt 元对象及部分函数边界；未取得对应 C++ 源码 | 对固定哈希做有限静态分析、实验补丁；反汇编不是原始源码 |
| `libappscommon.so.1.0.0` | 原生代理、元对象、接口封装 | 绑定字段和内部调用；不等于外部 PC 接口已经接通 |
| `lib/firmware/hbl/su-control/*.bin`、FARM 映像 | 控制固件二进制 | 是进一步追曝光信号的输入，尚未还原完整控制/物理时序 |

本机当前 PATH 未发现 ARM 交叉编译器、Qt 目标 SDK 或 qemu-arm；包内运行库不能代替专有源码与构建工程。已为本项目的 X1D 独立目录准备 Capstone 和 Unicorn，分别用于正确反汇编和有限 ARM 指令仿真。它们不能证明实际 VPU、传感器或热靴行为。

## 本轮已绑定的入口

- 机型绑定沿用同一 1.25.0 的 `Version::productInfo` (`0x4ad5e640`) 与 `Version::productName` (`0x4ad5e8dc`)：Wedge 板号分支的枚举 2 对应 `X1D-50c`，不是把共包的其他机型当成 X1D。
- QML `/settings/scripts/MenuItemSpecificationsWedge.js:84` 使用 `configstore.eshutter`；第 88 行有闪光同步模式。第 88 行本身没有电子快门条件，不能据此说原生控制允许电子快门引闪。
- `libappscommon` 的 `ConfigstoreProxy` 元对象中 `eshutter` 为 property 96，读取分支表 `0x4adb2b64` 指向 `0x4adb5094`，实际读取对象 `+0x14c`。`camera-daemon` 构造在 `0x24e98–0x24e9c` 将 ConfigstoreProxy 绑定到相机对象 `+0x10`。
- `WedgeStateMachine::checkFlashStatus` (`0x32c54`) 在 `0x32c68–0x32c70` 检查上述电子快门字段。电子快门分支还调用 `0x32844`：它读取 LensProxy 的 `lens_family`；值为 `NoLens=0` 时走 `preflashNotRequested`。这只闭环了一个与预闪相关的分支，不能把它当成最终热靴禁闪开关。
- 同函数还读取 `SucProxy.flash_status`。代理在相机对象 `+0x24`（构造 `0x24f10–0x24f14`）；状态字段为代理 `+0x32`，元对象 getter `0x4ada7038` 已绑定。枚举为无闪光灯 0、普通充电 1、普通就绪 2、iTTL 充电 3、iTTL 就绪 4、未知上界 255。这是固件内部已有的可观测状态，不是已经通过自制 PC 客户端读到的数据。
- `WedgeStateMachine::performExposure` (`0x344d4`) 在 `0x34628` 调用 `CamBodyProxy::expose(int)`；FARM 还提供 `performStartPreFlashSeq`、`onSensorExposureStart`、`onSensorExposureDone` 等接口。调用完成信号不是物理曝光/闪光时间戳。
- `msg2dbus-suc.service` 与 `msg2dbus-farm.service` 将内部消息分别桥接至 SUC、FARM 通道。它们印证控制跨越 Linux 应用边界；本任务没有打开这些接口。
- `phocus-daemon` 引用 `CameraProxy::expose`、`setFlashRechargeTime`。本轮未证明存在外部独立试闪命令，更未证明普通曝光接口可以绕过电子快门禁闪。回电参数不能代替引闪时序数据。

## 唯一尚未闭环的控制段

`CamBodyProxy / SucProxy / FARM` 之后，电子快门模式如何进入下层控制固件，以及真正热靴同步输出的门控与时序，仍未绑定。不能只修改上述 QML 或预闪判断就称作可用的电子快门闪光增强。

若后续继续闪光，应沿这条具体控制段建立消息和时序对应关系，首先复核保持原曝光路径所需的正常条件；暂不修改闪光分支。没有证据表明 X1D 的这部分源码比 X2D 更完整。工具、输入校验和分析方法可复用，地址、消息和补丁不能跨代复制。

官方手册说明电子快门的闪光限制与约 300 ms 读出；该读出说明不是本机实测，也不能直接当作“所有行同时感光窗口”的跨度。即使用合理慢门，仍需证实共同感光窗口及引闪发生的位置。目标是普通闪光，不是 HSS。

来源：[官方 1.25.0 固件](https://cdn.hasselblad.com/firmware/X1D-50c_Firmware/1.25.0/X1D_v1_25_0.cim)、[官方 1.24.0 GPL 归档](https://cdn.hasselblad.com/firmware/X1D-50c-Firmware/1.24.0/X1D_v1_24_0.tar.xz)、[X1D 手册](https://cdn.hasselblad.com/manuals/X1D_User_Manual/1.0.0/X1D_User_Guide_EN.pdf)。
