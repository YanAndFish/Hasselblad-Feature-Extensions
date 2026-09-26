> 历史资料归档：第一代 X2D 100C，固件基线 4.2.0。2026-09-12 迁入专属目录；保留原研究结论及批次边界，仅调整链接。最新地区与机内无线研究见 [当前研究索引](../../README.md)。正文中的根目录相对命令仍从项目根目录执行，旧硬件授权不延伸到当前批次。

# 第一代 X2D 100C：最小 USB 读取协议

当前实现已扩展为固定六项（27、28、25、87、88、61），六项已在第三轮实机验证成功；编码、顺序停止条件和日志边界见 [DEBUG_READ_BATCH.md](DEBUG_READ_BATCH.md)。本页记录公共 USB 封装与前两项编码，六项实得结果另见 [实机验证报告](USB_READ_VALIDATION.md)。

已实现并通过实机验证：打开正常 USB 控制接口，读取机身固件版本与系统运行标志，随后关闭本次主机句柄。2026-09-09 的第二轮结果为 **4.2.0 / 运行标志 1**，见 [实机验证报告](USB_READ_VALIDATION.md)。首轮误选数据端点并发送超时的 [独立更正说明](USB_ENDPOINT_CORRECTION.md) 和 [首轮报告](../../../research/validation/hardware/usb-2026-09-09T11-05-32-256Z.json) 均保留，不覆盖历史结果。

正常连接、会话登记、心跳和保持唤醒此前已获用户授权；最新任务恢复了状态与版本读取。首次请求前仍须通知来源任务，等收到用户当时已唤醒相机的反馈。本实现不调用拍摄客户端登记，因此没有持续心跳或联机拍摄模式切换。拍摄、闪光、对焦、设置写入、照片和固件操作均未开放。

## 官方输入与适用范围

| 对象 | 版本 | SHA-256 |
|---|---|---|
| 相机 `/bin/phocus` | X2D 100C 4.2.0 | `56c9a777fb9c5ed228fc32b47013822b34bd9109822871089700d23dd40a1516` |
| 相机 `/bin/msg2dbus` | X2D 100C 4.2.0 | `c02c2cd83ec9e5d7862659f05328927b7faa3e57789dd4aa0fd9bc427ad13a43` |
| 相机 `/bin/usb_bulk_raw_hbl` | X2D 100C 4.2.0 | `918d1c96a7e269a16b7759f93fb79bc5f47a2b6d973fc96e637e516a95afa90f` |
| 电脑 `PhocusApi64.dll` | Phocus PC 4.1.1 | `70b697d839378c58de086cb82b81ecefd2b1d723ea7361bcdaef0c8a04a6211a` |

固件输入见 [固件清单](../../../research/firmware-manifest.json)。电脑安装包来自 [Hasselblad 官方 CDN](https://cdn.hasselblad.com/software/Phocus_for_PC/4.1.1/Phocus-4.1.1-x64.exe)，下载清单见 [PC 输入记录](../../../research/phocus-pc-input.json)。已核对安装包 Authenticode 签名为有效 HASSELBLAD；只拆解容器及读取 DLL/INF，未执行安装包、官方 DLL 或驱动安装。电脑库地址以下均为其首选虚拟地址；相机地址属于上述固定 ELF。

第二轮已从 ID27 读取并接受机身版本号 4.2.0。USB VID/PID 和用户对所接机身的描述用于限定目标，不能单靠通用设备名推断型号或版本，也没有比对实机整包字节。

## 正常 USB 入口与身份

官方 `hbusb.inf` 覆盖 `VID_2756&PID_0009&MI_03`，使用 WinUSB 和接口类 GUID `{CC135687-5267-4313-B0C7-C344609D6EF0}`。这都是公开协议及驱动标识，不是设备唯一身份。

电脑库在 `0x1805cbe06` 检查产品号，在 `0x1805cbe17` 为这一产品号范围选择直接 AppsMessage 方式（对象字段 `+0x4b0 = 2`）。`0x1805c8050` 对应此分支；`0x1805cc676` 建立请求信号 4、回复信号 3，`0x1805cc681` 建立固定 origin=8、dest=5。固定节点号适用于正常 USB 路由，不是任意选取的客户端凭据。

**控制端点是第二个 OUT 与第二个 IN。** Phocus 发送回调 `0x1805c8fb0` 调用虚表 `+0x68`。官方 USB 虚表基址 `0x180ebccb8` 的此项是 `0x1805bab50`，在 `0x1805bab67` 使用对象 `+0xc9`，即第二个 OUT。控制接收 mode0 在 `0x1805ba600` 使用 `+0xc8`，即第二个 IN。此前把另一个数据发送入口 `0x1805ba8c0` 混同为这条虚调用链，是本实现的分析错误，现已更正。

相机 `/etc/init/msg2dbus.rc` 以 core 服务启动 `msg2dbus -s /dev/usb-ffs/bulk`。`MessageIO_USB` 构造在 `0x48498` 调用 init，检查 ep0、ep2、ep4 存在，打开 ep0，然后启动 `USBCtrlOutEp2`、`USBCtrlInEp4` 线程。控制 OUT 线程在 `0x47348` 打开 ep2，在 `0x47570` 执行读取。它不等待先收到某种拍摄命令才开始普通读取。

`usb_bulk_raw_hbl` 的 FS/HS/SS 描述符（`0x1960`、`0x198d`、`0x19ba`）顺序均为 OUT1、OUT2、IN1、IN2，所以 FunctionFS ep2/ep4 正好是第二对控制端点。端点地址会由 USB 组合设备映射，不能把相机本地逻辑地址直接硬编码为 Windows 地址。客户端现在严格核对四个 bulk 端点的方向顺序，选择第二 OUT/IN，布局不同即停止。

`USBCtrlOut::process` 将控制内容交给 AppsMessage；`UsbhostHandler::onMessageReceived` 的信号 4 分支在 `0x10aed8` 读取第 4 字节的长度、第 5 字节起的 PhocusMessage。通过 DBus 到达 phocus `0x83298` 回调时，目的类型为 USB（0），继续通过现有 enabled/connected 检查。

这条 USB 读取入口不调用 HTTP 的 `validateClientId` 或无线白名单读取。没有修改这些检查，没有取得、猜测或生成无线身份。PC 的完整高层初始化还会调用 WriteParameter；本程序没有载入该客户端代码，也没有复刻那些写入步骤，只实现相机已有的 ReadParameter 分支。

## 请求与回包

固定两项请求使用 `uint16LE sequence + byte type + payload`，type 固定 2，payload 固定为一个 `uint16LE parameterId`。相机 `ReadParameter` 在 `0x90cd0` 读取该 ID；处理器返回 ToString 文本。`PhocusMessage::MakeAnswer` 返回类型 `0x82`，`0x8c738–0x8c73c` 保留原请求序号。

第一项的人工示例（序号 1，读取 ID 27）为：

```text
04 00 08 05 05 01 00 02 1b 00
│     │  │  │  │     │  └─ ID 27，uint16LE
│     │  │  │  │     └──── ReadParameter = 2
│     │  │  │  └─────────── 序号，uint16LE
│     │  │  └────────────── PhocusMessage 长度 5
│     │  └───────────────── dest = 5
│     └──────────────────── origin = 8
└────────────────────────── signal = 4，uint16LE
```

相机发送的内部信号 14 在 `msg2dbus 0x3fec8–0x3fee8` 映射为 signal=3、origin=5、dest=8。Phocus `sendToHost` 每段最多 255 字节；非末段 length=0，末段 length=本段实际长度（`0x6c9c8–0x6c9d0`）。`USBCtrlIn::process 0x47ae0` 将每次 USB 控制输出补至 1024 字节。辅助程序只提取有效段，丢弃所有补齐内容；合并的 PhocusMessage 上限 603 字节，并严格核对序号和类型。

未设置参数订阅，因此不把任意其他回包当成允许继续的通知。遇到不同路由、类型或序号即停止，不扫描命令、不重试、不调整参数来使读取成功。

## 两项数据的解码

| ID | 4.2.0 已核实分支 | 允许的编码与显示 |
|---|---|---|
| 27 | `0x911b8` → `SystemProxyDbus::version_id`；type 4 字符数组 | `S<字节数>,<版本文本>`，长度必须吻合；去掉已核实的 `v` 前缀后仅显示点分数字版本 |
| 28 | `0x91168` → `system_state`，在 `0x91184` 比较 1，输出 type 2 | `i0` 或 `i1`；表示比较后的运行标志，不是完整状态枚举 |

`sCameraParameter::ToString 0x954e0` 的字符串格式位置 `0x1824bf`、数组计数格式 `0x1824c7` 和整数格式 `0x1824d0` 已核对。未知文本只标记隐藏，不原样输出；没有补写 `can_set=false`，而是明确“写入能力未查询”。若实机版本不同，后续对状态含义与闪光代码的解释要重新绑定该版本。

4.2.0 `camera-system` 的 `SystemObjectImpl::version_id 0x7ddd8` 通过 `Version::productVersion` 取得版本，并在 `0x7de48–0x7de80` 使用格式 `v%1`（`0x39aeaf`）。例如人工编码 `S6,v4.2.0` 规范化显示为 `4.2.0`；该例仍不是实机读取结果。

## 本机实现与关闭

[WinUsbReadOnly.cs](../../../native/WinUsbReadOnly.cs) 只允许固定的六项 ID，命令类型不能由外部指定。只枚举精确 GUID 与硬件 ID，拒绝多个匹配；打开后核对 interface=3、alt=0、class=255、subclass/protocol=0，并核对四个 bulk 端点，选择第二 OUT/IN 控制端点。更正版本不对第一对数据端点提交 I/O。

WinUSB 使用 Windows 已有驱动。打开所需的 `CreateFile`、`WinUsb_Initialize`、查询端点与读取方式依据 [Microsoft WinUSB 说明](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/using-winusb-api-to-communicate-with-a-usb-device)。每个控制端点设置本次主机 I/O 超时 2000 ms；[WinUsb_ReadPipe](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_readpipe) 使用同步模式及有效的返回长度指针。没有调用 SetConfiguration、SetCurrentAlternateSetting、ControlTransfer、ResetPipe、驱动安装或任何串口 API。

[WinUsb_WritePipe](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_writepipe) 支持 Overlapped=null 的同步写；未启用 RAW_IO 时不要求应用请求长度为最大包长的倍数。PC `0x1805bae73–0x1805bae7a` 使用请求剩余长度与分块上限的较小者，本请求实际长度仍是 10 字节。不能把相机回包补齐至 1024 字节推成主机请求也必须补齐；本次没有改成猜测的补齐或盲目加长超时。

当前每次最多六个读取请求，每项一次写入和一次回包，无自动重试。参数文本上限 100 字节，不接受本批不需要的分段。无论成功或出错均在 finally 中调用 WinUsb_Free、关闭本次文件句柄；不发送额外相机断开命令。Node 另设 30 秒辅助进程上限，异常失联时将请求数/清理状态记为未知，不能记成零或成功关闭。

## 复核与执行入口

```powershell
npm run build
npm run build:native
.\dist\native\HasselbladUsbReadOnly.exe selftest
npm test
$env:PYTHONIOENCODING='utf-8'
py -3.11 tools/trace_usb.py
node tools/read-camera.cjs
```

最后一条默认只看 Windows 接口元数据，不打开相机。人工报文检查与 TypeScript 替身检查没有真实 USB I/O。静态检查输出见 [usb-protocol-checks.json](../../../research/usb-protocol-checks.json)。

真实读取入口是 `node tools/read-camera.cjs --read`，或 Electron 中的“读取六项调试快照”。首次执行须先完成前述唤醒协调。CLI 只保存解析后的中文字段与有限传输元数据；不记录设备唯一路径、序列号、原始回包或凭据。
