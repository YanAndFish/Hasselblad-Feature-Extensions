# USB / SD 独立核查证据

2026-09-10。固定主输入：[官方 X1D 1.25.0 CIM](https://cdn.hasselblad.com/firmware/X1D-50c_Firmware/1.25.0/X1D_v1_25_0.cim)，SHA-256 `1b224ebe1f53d04a4352897c1ac1f50bc858d08048957382e4cb51ab16a5adf2`。实机固件、实际引导器和 fuse 均未知。以下“验证”均为离线字节、结构或指令核对；不是实机恢复测试。

## E1：i.MX Linux 设备树与启动存储

来源：`boot/devicetree-zImage-imx6q-hbl-wedge.dtb`，SHA-256 `bcd548efc1c01eb93bb8c8829beb371e2991f42dc7fcdf8bae29fa66d7bc7aca`。可复核输出：[board-evidence.json](board-evidence.json)。

- 根 `model` 为 `Freescale i.MX6 Quad Hasselblad Wedge Board`。
- `/soc/aips-bus@02100000/usdhc@02190000`、`@02194000`、`@02198000` 均 `disabled`；`@0219c000` 为 `okay`、`bus-width=8`、`non-removable`。这是固定 Linux 配置，不能直接读取 ROM 的启动脚或 fuse。
- `ecspi@02008000/m25p80@0` 的分区标签/范围为 `u-boot: 0+0x7c000`、`env: 0x7c000+0x2000`、`env-redundant: 0x7e000+0x2000`。`etc/fw_env.config` 的有效设备为 `/dev/mtd1` 与 `/dev/mtd2`。所以应说“U-Boot 从 eMMC 加载 Linux”，不能由 `emmcboot` 推成“所有引导程序都在 eMMC”。
- `ecspi@02010000` 另列 `fpga_mem1`、`fpga_mem2`；WEIM 下有 `vhfpga` 节点。
- `/soc/aips-bus@02100000/usb@02184000` 为 `okay`，没有 `dr_mode`；其 VBUS supply 名为 `usb_otg_vbus`。其他三个 USB 控制器节点为 `disabled`。没有 Type-C 数据线或外部 USB mux 的完整描述；缺字段不等于物理元件不存在。

## E2：包内 U-Boot

来源：`uboot.bin`，SHA-256 `bad3ab600873fa78adb7cc06190ff092052ff11b20f012da9c18cf22cddba8d3`；版本字符串为 `U-Boot 2015.07-rc1 (Jun 14 2017 - 00:55:53)`。原 1.25.0 更新脚本不写此程序，因此不能视为当前已安装版本。

- MMC 配置结构地址 `0x178387a4`，控制器基址 `0x0219c000`。板级初始化 `0x1780243c` 取该结构，`0x1780244c` 与 USDHC4 比较，`0x1780247c` 进入驱动初始化。与 Wedge DTB 的内置 eMMC 配置相符。
- `emmcboot` 指定 `root=/dev/mmcblk3p${rootpart}`，并从 U-Boot `mmc 0` 读内核/DTB。这两个编号属于不同软件命名，不能当作两台存储器。
- 默认环境的 `bootcmd/preboot/bootdelay/usbboot/usbupdate` 已逐项核对，完整值在 JSON 中。默认 `bootcmd` 不调用 USB；两个 USB 环境项分别读 `loader.hbl`、`hblupdate.img`。同名 `usbboot` 命令表项与环境项也不应混淆。
- 78 项固定命令表含 `bmode`、USB 主机和文件加载命令；未见 `fastboot/dfu/ums/sdp`。这是表项范围内结论，不否定 ROM 下载能力。
- `bmode` 处理器使用 BSS 的 `modes[2]`。本轮没有闭环其有效注册；上游 [cmd_bmode.c](https://raw.githubusercontent.com/u-boot/u-boot/v2015.07-rc1/arch/arm/imx-common/cmd_bmode.c) 明确需要注册模式表。不能仅凭命令名给出 `bmode usb` 步骤。
- 已有主研究核实零延时 `tstc/getc` 属于控制台输入，本轮未发现可复核的机身组合键分支。[已有入口报告](../../research/RECOVERY_ENTRYPOINTS.md) 保持原样。

## E3：FARM、两份 QSPI 镜像与 SD 启动分支

这部分是本轮新增独立证据，见 [payload-evidence.json](payload-evidence.json)。固定输入：

| 原包路径末段 | SHA-256 |
|---|---|
| `farm/bootimage_even-wedge-v1.25.0-13075-c9bb91d.bin` | `e0575442e0831f0ba6cd65a5beedfc64bff2c992182220b7832a27e49928cac0` |
| `farm/bootimage_odd-wedge-v1.25.0-13075-c9bb91d.bin` | `2c1ff341653f6548c04c0cfb10db7e864887135f259e278066de49ae1c7967be` |
| `usr/bin/program_farm.sh` | `2d3cf8bf120969961738d24af6c18aefeb3181d908146a78eb2d898b674ce4fb` |

两份镜像每份 3,954,444 字节。脚本先将 FPGA PS 置于 reset，切到 FARM 的 NOR，分别把 even/odd 写到 `/dev/mtd3`、`/dev/mtd4`。这些是已读代码的副作用说明，不是执行记录。

重组方法：将每对 even/odd 字节的 bit 0…7 分别放到 16 位字的偶/奇位，再按大端输出该 16 位字。不是普通字节交错。重组后 7,908,888 字节，SHA-256 为 `96449fce1e2bd5d9f181e92d84704154f97f3a758a5adeac11b466cc023f82f5`；已逐字节做完整反变换，恢复两份输入一致。没有保存重组镜像。

- 启动头 `0x20=0xaa995566`、`0x24=0x584c4e58`，`0x20…0x48` 的 11 个 32 位字加和为 `0xffffffff`。3 项分区头各自的加和也为 `0xffffffff`，分区内容边界全部在输入内。格式交叉依据为 Xilinx 官方 [FSBL 定义](https://raw.githubusercontent.com/Xilinx/embeddedsw/xilinx-v2017.2/lib/sw_apps/zynq_fsbl/src/fsbl.h)、[启动头](https://raw.githubusercontent.com/Xilinx/bootgen/master/zynq/include/bootheader-zynq.h) 和 [分区头](https://raw.githubusercontent.com/Xilinx/bootgen/master/zynq/include/partitionheadertable-zynq.h)。上游格式说明不当作哈苏专有源码。
- FSBL 数据从重组文件 `0x1700` 开始，长度 `0x1c014`，加载地址 `0`。其运行地址 `0x10898…0x108a8` 读取 `0xf800025c` 并取低 3 位；`0x108ac/0x108b4/0x108bc` 只比较 `1/2/0`，其他值在 `0x108c4` 开始报告 `ILLEGAL_BOOT_MODE`，`0x108dc` 使用错误值 `0xa000`。按照同系列官方定义 `SD_MODE=5`，这份 FSBL 的分派没有 SD 路径；这是指令验证，不只是缺少字符串。
- `FsblHookFallback` 位于 `0x5e4`，日志调用之后 `0x604: b 0x604`。该 hook 没有读取 SD 或调用 SD 初始化；不据此推断实机看门狗/供电之后的行为。
- 应用分区文件偏移 `0x5d1680`，加载地址 `0x100000`。含 `satadriver_read_sectors`、`satadriver_write_sectors`、`satadriver_enable_sd_clk`、SD0/SD1 状态和 USB 接口消息。结合 E4，支持卡访问经过 FARM 的正常运行路径；没有还原到外露槽的原理图引脚。
- 同一应用另有 `farm_microsd_busy_event` 以及“从 SD 恢复校准数据”的日志文本。本轮未闭环此恢复函数的入口、输入格式、介质映射或写入目标；不能把所有 `sdcard` 文本一概归为外露槽，也不能把校准恢复称为 Linux/整机重装入口。没有读取任何校准数据。

## E4：Linux 存储访问 FARM

`storage-daemon` SHA-256 为 `5dd2000254b926cacae97acca5dcf3b4b677633b8baddd2a3e6ef6785427396a`。已在原始 ARM 指令核实：

| 调用地址 | 目标 |
|---|---|
| `0x2d91c` | `FarmProxy::RequestFile`，PLT `0x1b234` |
| `0x2df3c` | `FarmProxy::OpenFile`，PLT `0x1a5f8` |
| `0x38724` | `FarmProxy::CloseFile`，PLT `0x1adfc` |

程序有 `FarmStorage` 的链接状态、卷信息、文件完成处理；原包 `msg2dbus-farm.service` 启动相应内部消息桥。此依赖与 E1/E3 共同成立，不是从一个类名直接推物理接线。SD CIM 正常更新与 Retry 的既有分流证据见 [入口报告](../../research/RECOVERY_ENTRYPOINTS.md)，失败日志写卡经 Storage 的已知依赖见 [日志说明](../../research/ERROR1000_LOG_EXPORT.md)。

## E5：FX3 自身与电脑枚举

`fx3/fx3_wedge-v0.0-14268-e0ef6ae.bin`：160,188 字节，SHA-256 `19236566d65ad6881fda0ee554944374188217fbcb514f0eb8c0cae1416b5a05`。已按 Cypress `CY` 镜像 5 段结构验证范围和累加校验；没有执行程序。

| 描述符 | 原文件偏移 | 加载地址 | VID:PID |
|---|---|---|---|
| USB 2.10 Device Descriptor | `0x17394` | `0x40017c60` | `2756:0002` |
| USB 3.00 Device Descriptor | `0x17514` | `0x40017de0` | `2756:0002` |

初始化中的 `0x40004a24…0x40004a34` 与 `0x40004a44…0x40004a54` 将这两个地址传给同一描述符处理函数；并非只找到未引用字节。序列号描述符内容未读取或记录。

已有 PnP 快照只证明当时存在此公开编号的设备，与固定 FX3 应用相符；没有运行态代码哈希，不能升级成当前 FX3 版本确认。FX3 应用同时带 USB 2/3 描述符，也不能排除板上另有 mux 或其他维修接线。

原包 `program_fx3.sh` 通过机内 I²C EEPROM `2-0050` 写入，并切换电源/EEPROM 总线 GPIO，说明这一控制器的程序存储与主 Linux 独立。Infineon 的 [FX3 自定义 USB Bootloader 说明](https://community.infineon.com/t5/Knowledge-Base-Articles/FX3-as-Custom-USB-Bootloader/ta-p/248733) 明确区分 ROM、PMODE 和第二阶段程序。其默认 USB ROM 编号不能用来反推 X1D 的 PMODE 布线或定制情况。

## E6：i.MX 下载能力、驱动与源码缺口

Wedge 原包的 `ci_hdrc.ko` 属于 Linux `3.14.28-1.0.0_ga+yocto+gf7d0ab5`；同时存在 `ci_hdrc_host_init`、`ci_hdrc_gadget_init`、`ci_otg_role`，并引用 `of_usb_get_dr_mode`。JSON 记录其哈希和符号范围。不能因为文件清单出现 `host` 子目录就称其不支持 device；同样不能从 dual role 驱动推断外露 Type-C 可直接连 i.MX。

[NXP 开发板资料](https://www.nxp.com/document/guide/getting-started-with-i-mx-6quadplus:GS-RD-IMX6QP-SABRE) 和 [mfgtools 示例](https://github.com/nxp-imx/mfgtools/wiki/Example) 支持芯片/制造工具的通用下载能力，并需要匹配 bootloader 和目标存储配置。尚缺 Wedge 的外口连接、启动条件、允许状态及恢复加载器。当前 Linux 错误 1000 发生在用户已见菜单之后，没有证据表明它会重新触发 ROM 的启动介质失败回退。

已完整读取并枚举 [官方 1.24.0 GPL 归档](https://cdn.hasselblad.com/firmware/X1D-50c-Firmware/1.24.0/X1D_v1_24_0.tar.xz)：415,113,824 字节，SHA-256 `79a5a0d4d34b85f8631874a665bbc25dfdeb2da80530b6f38b0c4ff83d02fcec`，1,165 个外层条目、70 个组件。外层没有 Linux/U-Boot 组件，也没有 Wedge/Umbrella 板级路径；含 `dtc-native` 不等于含 Wedge DTS。没有解开所有组件的嵌套归档，因此不作“整个归档每个字节都无板级代码”的绝对断言。[完整目录结果](gpl-inventory.json) 可复核。本轮没有在其他源仓库搜索或写入。

## 验证与交付

- [audit_board.py](audit_board.py)：已运行通过 5 个原包输入哈希、设备树分区与控制器条件、包内 U-Boot MMC 配置和 3 条 FARM 文件调用，生成 [board-evidence.json](board-evidence.json)。
- [inspect_payloads.py](inspect_payloads.py)：已运行通过 6 个固定原包输入、FX3 分段校验、两项描述符及引用、FARM 完整反变换、启动头/3项分区头和 FSBL 分支检查，生成 [payload-evidence.json](payload-evidence.json)。解密常量由固定公开解析器版本仅在内存取得，不记录材料，不执行第三方代码。
- [audit_gpl.py](audit_gpl.py)：已完整流式读取官方 GPL 归档并计算 SHA-256；仅保存目录与摘要，未执行其中程序。

上述脚本均检查真实 `cwd`，只把结果写入本独立目录；以 `py -3 -X utf8 -B` 运行避免生成外部字节码文件。无相机会话、端口请求、驱动改动、机内操作、Git 或发布动作。未修改原增强候选、原研究文档或其验证证据。
