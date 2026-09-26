# 蓝牙主机通路：固件板级复核

日期：2026-09-13。静态输入为官方 X1D 1.25.0 的缓存文件，不把发行包配置当作实机固件版本或实际走线。此次未访问相机、打开串口、改 GPIO 或加载驱动。

本文件主体记录此前离线研究。后续用户追加授权后的 UART5 单次试探已执行，结果为无回复，详见 [实验当前状态](README.md)及[实机证据](build/uart-probe-r1/session/result.json)。该结果尚未证实蓝牙连接假设。

再后续 H5 单包尝试在发送前静默检查停止，没有发出同步包；驱动累计接收计数较此前增加八个字节，但未读取内容，协议和来源未确认。详见 [H5 尝试证据](build/uart-h5-r1/session/result.json)。这不是 H5 握手成功证据。

H5 假设依据是原厂 [CYW4356 数据手册](https://www.infineon.com/dgdl/Infineon-CYW4356_CG8674_Single-Chip_5G_WiFi_IEEE_802.11ac_2x2_MAC_Baseband_Radio_with_Integrated_Bluetooth_5.0-DataSheet-v03_00-EN.pdf?fileId=8ac78c8c7d0d8da4017d0ee4c6ad6bfa)（002-20538 Rev. B，2018-07-27，第 7.5 节）：支持 H4、extended H4、H5，默认 115.2 Kbaud，H5 不需要 RTS/CTS。文档说明 BCM4356 更名为 CYW4356，但不能由此将文档的 Bluetooth 5.0 标记当作当前相机能力。同步包布局另与 [Linux v4.2 H5 实现](https://raw.githubusercontent.com/torvalds/linux/v4.2/drivers/bluetooth/hci_h5.c)交叉核对；本实验没有运行该驱动、完成配置握手或发送 HCI 命令。手册还说明蓝牙可独立保持复位，因此 Wi-Fi 正常不证明蓝牙已供电并运行。上述资料不能证明 UART5 对端和实际启动协议。

## 新确认的配置事实

`inspect_board.py` 已解析同一发行包的 Wedge、Victory、Idun 三份 DTB，并解析串口、USB、PCIe 的引脚引用及 GPIO 控制器引用。报告见 [board-topology.json](build/board-topology.json)，内含逐文件 SHA-256。Wedge 输入哈希固定为 `bcd548efc1c01eb93bb8c8829beb371e2991f42dc7fcdf8bae29fa66d7bc7aca`。

| 项目 | 固件中实际读到的配置 | 结论边界 |
|---|---|---|
| UART5，`serial@021f4000` | Wedge 为 `okay`；Victory、Idun 为 `disabled` | 是 Wedge 特有的启用配置，尚不知外接对象 |
| UART5 引脚 | `KEY_COL1` → TX，`KEY_ROW1` → RX | 仅确认 SoC 复用配置，不证明 PCB 对端 |
| UART5 流控 | 该组只有两条引脚记录；串口节点未声明 `fsl,uart-has-rtscts` | 没有在该配置中找到 RTS/CTS；不能推断物理引脚不存在 |
| UART4 | `disabled`，无板级 pinctrl 引用 | 不能因备用接口存在而直接启用 |
| USB OTG，`02184000` | `okay`，声明 VBUS regulator 和 pinctrl | 不能视为已经接出的内部蓝牙 USB 通路 |
| USB，`02184200` | `disabled` | 缺少启用和实际线路证据 |
| USB HSIC，`02184400`、`02184600` | 均 `disabled` | 不能通过修改状态直接证明蓝牙可用 |
| PCIe | 三份配置的供电、复位与 pinctrl 相同 | 这些属性属于 PCIe 节点，不是已识别的独立蓝牙供电/唤醒线 |

UART5 两条原始 pin tuple 为：

```text
0x200 0x5d0 0x000 0x4 0x0 0x1b0b1
0x204 0x5d4 0x940 0x4 0x1 0x1b0b1
```

前五项与 [Linux v4.2 的 i.MX6Q 引脚定义](https://raw.githubusercontent.com/torvalds/linux/v4.2/arch/arm/boot/dts/imx6q-pinfunc.h) 中 `MX6QDL_PAD_KEY_COL1__UART5_TX_DATA`、`MX6QDL_PAD_KEY_ROW1__UART5_RX_DATA` 一致。此引用只解释数值对应的 SoC 引脚功能，不引入上游板级配置。

## 启动与程序线索

- 缓存的 systemd 配置明确将 `ttymxc1` 分配给 SUC 消息服务，`ttymxc2` 分配给 FARM 消息服务；不能拿来试发 HCI。
- 对缓存 `usr/bin`、`usr/sbin`、`usr/lib`、`lib`、`etc` 相关文件进行定向字符串检查，`ttymxc4` 仅在 `etc/securetty` 命中。该文件是终端登录许可列表，不证明端口用途。
- `bluetooth.target` 只是 systemd 通用目标文件；未从此次检索找到实际蓝牙初始化服务。
- 缓存 `uboot.bin` 的定向可打印字符串检查没有找到 `UART5`、`ttymxc4`、蓝牙、BT 唤醒/使能或所查模块型号标记。字符串缺失不能排除无符号代码、动态构造路径或其他控制器里的实现。
- 此项检查针对已有缓存，不能声称遍历了所有可能的软件版本及全部固件组件。

## 当前判断

### 用户授权后的 Wi-Fi 蓝牙共存选项查询

实机 `/usr/bin/wl` 的 SHA-256 为 `ff644f19f29ae6b0f9576c063eecd1005431d3db81ff12c1bf1ae43c7bf6e999`，与官方 1.25.0 包内该文件一致；这不等于整机固件版本确认。选定实际存在的 `wlp1s0`，仅执行无设置值的查询：

| 查询 | 实际结果 |
|---|---|
| `btc_mode` | `5`，退出码 0 |
| `btc_wire` | 工具错误 -23，退出码 211 |
| `phy_btcoex_desense` | 工具错误 -23，附加 PHY DEBUG COMMAND 错误 -45，退出码 211 |

未传入设置值、未修改共存模式、未扫描或配对；所有查询 USB 句柄均关闭。公开 [Broadcom 2013 头文件](https://android.googlesource.com/kernel/msm/+/android-msm-hammerhead-3.4-m-preview/drivers/net/wireless/bcmdhd/include/wlioctl.h) 将 0 定义为关闭、5 定义为 HYBRID 共存；这是版本受限的语义参考，不能证明当前蓝牙处理器已经运行。原厂 [共存说明](https://community.infineon.com/t5/Knowledge-Base-Articles/Using-btc-mode-for-BT-coexistence/ta-p/680099) 同样讨论的是 Wi-Fi/BT 共存策略，不是 HCI 启动或发现开关。本轮确认共存查询可用，但没有取得蓝牙可发现的新证据。

### 完整 rootfs 续查与外部扫描条件

在后续用户要求继续外部扫描与初始化研究后，对固定官方 X1D 1.25.0 原包再次校验并在内存解析，覆盖 rootfs 全部 1982 个普通文件、158250622 字节。没有运行包内程序、访问相机或写回输入基线。报告见 [完整 rootfs 定向检索](build/full-rootfs-bt-audit.json)，逐命中文件记录 SHA-256；这次范围比此前缓存子集更广。

- 文件名仅命中两处通用 `bluetooth.target`，没有找到 `.hcd`、`hciattach`、`brcm_patchram`、`btusb` 或 `hci_uart` 名称的文件；对应内容标记检索亦未找到常见初始化程序线索。
- `ttymxc4` 内容标记仍仅见于 `etc/securetty`；没有找到 `BT_REG_ON`、`BT_WAKE`、`bt_power` 标记。无命中不能排除无符号、动态命名或其他控制器内的实现，也不等于证明硬件缺失。
- `usr/bin/wl` 中蓝牙相关帮助明确属于共存模式、参数、去敏及统计；`btc_mode` 不是已确认的蓝牙供电/发现开关。正常 Wi-Fi 固件里的 `host_wake_opt` 也不能直接当作蓝牙唤醒引脚。未运行这些选项。
- Windows 当前 PnP 设备查询没有识别到 Bluetooth 类设备；再按当前设备友好名称检索 Bluetooth/蓝牙也未命中，因此 Agent 未在本机执行外部射频扫描。用户随后明确补充：已自行完成外部扫描，未发现相机。此项记为用户观察；扫描设备、扫描类型（BLE 或经典蓝牙）、时长及当时相机状态未记录，不能据此证明无蓝牙硬件或完全没有射频活动。此前阶段报告中的“外部扫描尚未执行”应更正为“用户已扫描，未发现相机；Agent 本机未扫描”。

可将 UART5 保留为待查接口，但不能把它认定为蓝牙。现有证据没有形成“模块变体 → PCB 连线 → 供电/唤醒 → 主机接口”的完整链条。仅调整波特率、遍历串口或启用 USB 控制器，无法弥补该证据缺口。

要进入硬件通信验证，仍需板级连线资料、可辨识模块及走线的现成主板照片，或原厂针对该板的驱动/初始化源码。缺少资料时，下一阶段不执行未知接口试写；蓝牙发现目标仍未完成。此前内存程序自检的成功不改变这一判断。

## 公开资料续查

### 模块蓝牙 USB 通路的进一步核对

- AzureWave [AW-CM217NF User Guide v0.1，2015-02-16](https://manualzz.com/doc/62992368/azurewave-cm217nf-wireless-lan-and-bluetooth-combo-module...) 的第 17–19 页，在蓝牙控制、加载与连接章节明确选择 USB transport。它支持该型号的蓝牙 USB 通路结论，但不是 X1D 实机型号证明；文档后续还夹有 UART 速率测试步骤，不能据某个孤立步骤认定相机走串口。
- 制造商提交的 [RF150126E05K-2 报告](https://device.report/m/3387f9e0cde34ec973a5fd2ff6339b623c8cbc309983b038b7f55fa0c1aaa936) 第 8 页，将 AW-CM217NF 与 AW-CM240NF 都列为 BCM4356，并特别标注后者改为 PCIe+UART 接口。因此芯片型号不足以选定蓝牙主机接口。该报告为 2018 年资料，不直接证明 2016 年 X1D 用哪种变体。
- 实机再次只读核对：`/sys/bus/usb/devices` 列表为空；`/sys/class/usb_host` 不存在；`ci_hdrc` 平台驱动仅列出绑定 `ci_hdrc.0`，解析位置为 `2184000.usb/ci_hdrc.0`，`/sys/class/udc` 同时列出 `ci_hdrc.0`。当前可见的是设备端控制器，没有已枚举的内部 USB 蓝牙设备。查询没有切换 USB 角色、加载模块、绑定/解绑驱动或启用控制器。
- 初次直接列出不存在的 `usb_host` 类目录返回命令失败；后续带存在性检查确认该目录不存在。不能将命令失败本身当作硬件不存在的证据。

本轮把 USB 通路保留为需确认的备选路线，没有找到 X1D 特定模块引脚到主板的完整连接图，也没有找到可直接执行的蓝牙启用入口。模块指南的加载、测试、重置和地址写入步骤均未执行。

- [Alastair Philip Wiper 的哈苏工厂摄影原文](https://alastairphilipwiper.com/blog/hasselblad-factory-sweden)，2017-02-03 发布，正文讨论第一代 X1D。已实际查看其机身内部照片：可看清部分板件和连接器，但没有提供足以确认无线模块接口的标识与走线视角。图片仅作本地研究缓存，不据此判定 UART5 的对端。
- [2018 年同一 FCC ID 的变更说明](https://device.report/m/a9ef97ade39e72d286337c933b845cd4957da2efc26fa428ddd800f441edf453) 明确对应 H6D-400c MS。因此，该批内部照片不能直接作为第一代 X1D 的板级证据。
- 已定位 2016 年 X1D SAR 后续图页的公开附件条目 `3069882`，但原文件获取失败；没有读到图片，不能声称已核对附件走线。现有可读的报告前 27 页未覆盖该附件。
- 本轮公开检索未找到能对应上述固定 Wedge DTB 的原厂板级源码，也未找到能辨识蓝牙信号连接的第一代 X1D 主板原理图。此结论是本轮检索结果，不是“源码或原理图不存在”的断言。

需要向资料持有者核实的具体内容已整理为 [资料询问草稿](SOURCE_REQUEST.md)。尚未发送、联系任何人或要求用户拆机。
