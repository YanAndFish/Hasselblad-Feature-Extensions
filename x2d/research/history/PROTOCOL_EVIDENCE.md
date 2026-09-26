> 历史资料归档：第一代 X2D 100C，固件基线 4.2.0。2026-09-12 迁入专属目录；保留原研究结论及批次边界，仅调整链接。最新地区与机内无线研究见 [当前研究索引](../../README.md)。正文中的根目录相对命令仍从项目根目录执行，旧硬件授权不延伸到当前批次。

# 只读调试客户端：证据与实现边界

2026-09-09；第一代 X2D 100C；离线分析基线为官方 4.2.0。后续最小 USB 读取已确认机身报告版本号为 4.2.0，见 [实机验证](USB_READ_VALIDATION.md)。以下地址只适用于 [binary-manifest.json](../../../research/binary-manifest.json) 中已校验的 ELF；版本号相同不等于实机整包字节已比对。

**当前交付范围。** Electron 主进程使用 Node.js 实现解析、回环模拟、受限导入和报告输出；界面使用 TypeScript / HTML / CSS。独立 Python 工具校验及解析官方固件。C# WinUSB 辅助程序原有 ID27/28 已在更正端点选择后取得实机结果；当前新增 ID25/87/88/61 固定读取及逐项通信记录，已通过离线检查及第三轮六项实机验证。详见 [调试增强批次](DEBUG_READ_BATCH.md)，细节见 [USB_READ_PROTOCOL.md](USB_READ_PROTOCOL.md)。首轮错误保留于 [独立更正说明](USB_ENDPOINT_CORRECTION.md)。本页主要保留 HTTP 路径证据，不能把其身份缺口外推为 USB 必须读取无线白名单。界面仍没有任意请求入口，测试模式后端固定拒绝实机读取。

## 参数路由

对象：`/bin/phocus`，SHA-256 `56c9a777fb9c5ed228fc32b47013822b34bd9109822871089700d23dd40a1516`。

| 证据 | 地址或范围 | 本次结论 |
|---|---|---|
| `Httpd` 构造 | `0xbec70`；注册处 `0xbf564` | 路由 `/v1/parameters`，MethodGet。 |
| 路由处理器 | `0xdc6b8` | 先调用 `validateClientId`；失败分支返回 401。 |
| 参数构造与取值 | `0xdc8b4`、`0xdc8dc` | 使用 `ControlParameterValue` (`0x9d950`) 与 `ReadParameter::getValue` (`0x910a8`)。 |
| 返回结构 | 参数处理器内 | 外层键为十进制 ID；项目包含 `can_get`、`can_set` 布尔及 `range`、`value` 字符串。 |
| 可选名称 | `0xdcbe8..0xdccb4` | `name` 受固件日志开关影响，不保证存在；客户端名称来自本地静态目录。 |
| 服务端循环 | 同一处理器 | 读取 ID 1–139；没有已证实的按 ID 缩小读取范围机制。 |
| Qt 元数据 | `0x1a68a8`、`0x1a1010` | `eCamDevParam` 共 141 项：0、1–139、168；168 不在上述 HTTP 循环中。 |

响应不包含独立 `type` 或 `unit` 字段。实际值经固件 `ToString` 转换，尚未通过正常实机响应核查其全部编码。下面仅是用于说明已核实外形的人工例子：

```json
{"27":{"can_get":true,"can_set":false,"range":"","value":"4.2.0"}}
```

| 参数 | 读取分支 | 限制 |
|---|---|---|
| 15、27：固件标识 | `0x911b8` → `SystemProxyDbus::version_id` | 两个 ID 共用读取分支；不是独立读取传感器 MCU。 |
| 74、75、120：镜头版本、产品码、名称 | `0x925f0`、`0x9271c`、`0x916a8` | 版本和产品码不能替代镜头同步能力。 |
| 25：回电等待 | `0x9278c` → `flash_recharge_delay` | 秒单位由参数名推断；不等于 Xsync 延迟。 |
| 87：闪光曝光补偿 | `0x92908` → `flash_ev_adj / 12.0` | EV 补偿不等于 Fsync 时间修正。 |
| 88：电子快门状态 | `0x928e8` → `eshutter_current` | 状态快照不等于感光窗口或事件时间。 |
| 118：语言 | `0x92ae8` → `language_index` → `Cam2Phocus_Language` (`0x12afb0`) | 不等于销售地区。 |

`HasDoubleFSync`、`FsyncAdjust`、`XsyncDelay` 未以这些名称出现于提取的 141 项枚举中；不排除别名或其他正常接口。当前发现的 `/v1/` 路由只涉及参数或照片相关操作，没有已证实的完整 trigger trace / 内部同步日志读取路由。

## HTTP / 无线会话尚未闭环

`Httpd::validateClientId` (`0xc0260`) 从 `X-Phocus-Client-Id` 解析非零数字并与 active ID 比较。成功路径会调用 `httpRequestHeartbeat` (`0x57590`)，因此“GET 参数”不能独自证明没有状态副作用。

`V1Client::onV1MessageReceived` (`0xdf968`) 检查 ID 列表，并存在 `activeClientChanged`、`setConnected` (`0xe1648`)、ping 和定时器路径。`readDeviceIdFile` (`0xe2268`) 的固件路径线索是 `/data/misc/wifi/whitelist.conf`，这里只读到固件内的路径字面，没有读取实机文件、内容或凭据。

`PhocusD::addTetheredClient` (`0x6cdd0`) 在 `0x6cf10` 申请 wakelock，并更新客户端列表和 `updateTetheredCaptureClients` (`0x6d1f8`)。`removeTetheredClient` (`0x74cd8`) 清理订阅及更新模式，正常断开报文仍未完整还原。

`/bin/camera-system` 中 `SystemObjectImpl::doRequest_authorize_client` (`0x7fca0`) 在 `0x7fda4` 调用 `BtAuthRequestHandler::initiateBtAuthRequest`。这只是正常授权链的一部分证据，不足以构造合法客户端身份、USB/DUSS 首报文或断开协议；也不证明必须走蓝牙这一种路线。

用户允许正常会话、心跳与保持唤醒，并已恢复 USB 的最小状态/版本读取。USB 的固定路由节点与无线客户端身份分属不同入口；不会枚举、伪造或复用未知 ID。每轮真实读取先完成证据核查并协调当时唤醒状态，不能通过试包猜协议。

## 客户端约束及隐私

- 默认仅加载本地页面与静态证据，不扫描、自动连接或发送设备请求。
- `preload` 只暴露固定 IPC 方法；主进程检查调用窗口、主 frame、精确页面 URL 和方法参数。`sandbox`、`contextIsolation` 开启，Node 集成关闭。
- 渲染会话只允许三个明确的应用资源；禁止外部页面、导航、新窗口、下载和权限请求，CSP 的 `connect-src` 为 `none`。
- Node 网络函数为模拟器私有实现，客户端目的地址与显式源地址均为 `127.0.0.1`，端口只来自当次本进程服务器。独立 Agent 隔离全局代理；请求固定为一次 `GET /v1/parameters`。
- 不跟随重定向、不重试、不提交身份头；整个请求最长 2 秒，响应头上限 8 KiB、正文上限 256 KiB。错误时清除旧快照并关闭连接。
- 仅保留 18 项已审查的参数 ID。未知字段、远端名称、设备/镜头序列字段及非空 `range` 原文均不进入界面或报告；`value` 按明确格式和数值范围过滤，陌生编码隐藏。
- 本地白名单只限制本机解析与保留，**不能缩减未来服务端一次批量读取的范围**。当前还没有真实服务端请求。
- `can_set` 仅用于显示相机声称的能力，`clientCanSet` 始终为 false；没有写参数、拍摄、照片、地区修改、调试接口或固件功能。

各层文件为 `app/main.ts` / `preload.ts`、`protocol.ts` / `simulator.ts` / `service.ts`、`evidence.ts` / `renderer.ts`。显示来源区分 `offline-static`、`simulated`、`offline-import`；官方固件研究证据与当前参数快照分别标记。日志仅包含固定操作名、已审查结果、计数与耗时，不记录原始响应、导入文件名或设备身份。HTTP 耗时不能当作曝光或同步测量。

Electron 隔离机制参照 [Electron 官方文档](https://www.electronjs.org/docs/latest/tutorial/context-isolation)，网络实现参照 [Node.js HTTP 文档](https://nodejs.org/api/http.html)，Qt 方法常量参照 [QHttpServerRequest 文档](https://doc.qt.io/qt-6/qhttpserverrequest.html)。这些资料用于理解主机框架，固件行为结论来自上述固定 ELF。

## 地区线索

`camera-system` 的 `ProdInfo::setWifiRegion` (`0xeab30`) 使用 `Identity/WifiRegion` 键并调用 `setConfigParam` (`0xe8de8`)。后者可将制造分区切换为可写，经 `QSettings::setValue`、`sync`、状态检查后恢复分区并重新读取配置。因此，无线地区存在独立配置写入路径有静态依据；不能据此证明“销售区 JP 改 CN”就是同一字段，或普通客户端有可用的修改接口。

固件还出现 `/factory_data/settings.ini`、`/factory_data` 与 factory 分区路径，但本轮未完成 `settingsFile` 初始化与该具体文件的全部绑定，不能把候选路径升级为确定销售区存储位置。用户回忆可能只改配置，仍作为待验证线索。未调用任何 setter，也未读取实机制造、NVM 或校准存储。

## 实际设备接触及未完成项

本项目本次曾于 2026-09-09 17:26:23 +08:00 查看 Windows 现有网卡及设备元数据：RNDIS 状态 Up、主机侧 IPv4 为 192.168.42.1/24、接口索引 6，Hasselblad 图像设备状态 OK。这是当时主机快照，没有探测相机地址、打开 USB 控制或串口、发送 HTTP、启动 Phocus 或读取照片。旧相机地址不能直接复用。

本次真实相机报文为 0。前序交接中的那次 401 属于之前的检查，不能归为本轮客户端测试。尚未完成正常实机连接、参数联调、内部事件读取、电子快门闪光功能、实际时序测量或 JP/CN 转区结论。电子快门的最新独立结论见 [分支分析](ESHUTTER_BRANCH_ANALYSIS.md)。
