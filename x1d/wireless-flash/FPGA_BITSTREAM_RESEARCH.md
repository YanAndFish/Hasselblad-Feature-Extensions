# 官方 FPGA 配置分区的离线解析

记录日期：2026-09-10，北京时间。目的是继续追查电子快门的真实积分同步信号。本轮只解析官方文件，未加载、修改或回读相机 FPGA，未访问配置口、JTAG、PCAP 或硬件寄存器。

**已完成配置报文、两处 CRC 与器件配置帧映射，并把 SENSORIF 的启动、模式及周期配置追到两路 I/O 输出；局部模型已复现行/帧周期，尚未识别物理积分边沿。** 最新细节见 [SENSORIF 局部逻辑](FPGA_SENSORIF_LOGIC.md)。

## 输入与结果

输入为官方 X1D 1.25.0 中 wedge 对应的 even/odd bootimage，沿已核对的位交织关系合成 7908888 字节，SHA-256：

`96449fce1e2bd5d9f181e92d84704154f97f3a758a5adeac11b466cc023f82f5`

按 AMD 的 [Zynq-7000 Boot Header](https://docs.amd.com/r/2022.2-English/ug1283-bootgen-user-guide/Zynq-7000-SoC-Boot-Header) 和 [Partition Header](https://docs.amd.com/r/2024.2-English/ug1283-bootgen-user-guide/Zynq-7000-SoC-Partition-Header) 定义读取分区表。表在 `0xc80`，三个分区分别为启动代码、PL 配置、FARM 应用，另有结束记录；四个分区头的反码加和检查通过。

| 项目 | 已解析结果 |
|---|---|
| PL 分区在合成镜像中的起点 | `0x1d740` |
| PL 分区长度 | 5979936 字节 |
| PL 分区 SHA-256 | `8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30` |
| 配置同步字位置 | 分区内 `0x30`，按 little-endian 字存储 |
| Type 1 / Type 2 报文总数 | 551，包含 NOP |
| IDCODE 写入值 | `0x0372c093`；这是官方文件中的配置目标值，不是机身实读芯片信息 |
| FDRI 数据 | 一个 Type 2 大数据块，1494396 个 32 bit 字，数据从分区内 `0xec` 开始 |
| CTL0 写入值 | 两次均为 `0x501`，没有设置 DEC 位 |
| 结束 | 已解析到 DESYNC 及尾部 NOP；长度精确覆盖整个分区 |

配置报文、寄存器编号和 DEC 的含义按 AMD [7 Series FPGAs Configuration User Guide，UG470](https://docs.amd.com/api/khub/documents/FOs3lXmlcWxBhTIFxVKyGA/content) 复核。该文件的分区属性、配置控制和报文结构支持继续分析明文配置数据；不据此推断相机硬件安全设置、运行状态或回读权限。

已重新计算两处配置流 CRC，均与原值吻合：分区偏移 `0x5b36dc` 为 `0x6febe65f`，`0x5b38b4` 为 `0xe3ad7ea5`。使用每个写入数据字及 5 bit 寄存器地址更新 CRC，按 RCRC 和 CRC 检查点复位；算法依据 [Project X-Ray 原始实现](https://github.com/f4pga/prjxray/blob/master/tools/bits2rbt/crc.h)。这支持解交织、字节序和报文覆盖的正确性，不代表电路功能或曝光时机已验证。

## 配置帧与局部资源

公开 [openXC7 器件数据库](https://github.com/openXC7/prjxray-db/tree/e8b8e8e46a91334f6232df84d36954323e15a1d1/zynq7/xc7z030) 提供 XC7Z030 的帧与布线描述。本轮固定数据库版本 `e8b8e8e46a91334f6232df84d36954323e15a1d1`，其 IDCODE 与官方 PL 中的值一致。使用 `xc7z030fbg676-1/part.json` 的同一硅片帧地址；不能据此断定相机实际封装或速度等级。

| 帧映射检查 | 实际结果 |
|---|---|
| 每帧长度 | 101 个 32 bit 字 |
| 真实配置帧 | 14780 帧 |
| 八个配置总线/半区/行组合的填充 | 每行两帧，共 16 帧，全部为零 |
| FDRI 覆盖 | 14796 × 101 字，精确覆盖数据块 |
| 资源网格 | 42636 个 tile；所有已有 bits 段的基地址都能对应配置帧 |

帧 ECC 使用 [Project X-Ray 的 7 series 算法](https://github.com/f4pga/prjxray/blob/master/lib/xilinx/xc7series/ecc.cc) 独立计算。直接对文件中的原始帧计算，有 33 帧不同。七帧位于 CLBLM 的 LUT 内容区域：按配置位识别 RAM/SRL 用途并屏蔽其 INIT 内容后，七处差异全部消失；受该屏蔽影响的 444 帧全部吻合。数据库识别出的动态 LUT 共 2300 个。

动态存储配置需屏蔽的理由见 AMD [Configuration Memory Masking](https://docs.amd.com/r/en-US/pg036_sem/Configuration-Memory-Masking)。这里是离线按数据库的对应验证，没有读取或改变机身的 GLUTMASK。剩余 26 帧包括 20 个 BLOCK_RAM 帧、两个 XADC 所在配置帧和四个网格未命名覆盖的帧；本轮没有完整重建这些资源的屏蔽规则，**不把它们标成已通过 ECC，也不把差异称作固件损坏或机身故障**。

同时取得固定版本的 `tileconn.json`、`node_wires.json`、CLB/INT segbits 和 PS7/相关接口 ppips，全部只作为数据解析，没有执行数据库仓库中的外部程序。正在使用配置实际选中的 INT 连接和标记为 `always` 的固定连接恢复局部信号路径；`hint` 不当作电气短接。

## 局部布线恢复进展

[research/fpga_routing.py](research/fpga_routing.py) 已保存并实际执行。它按 tilegrid 坐标、tileconn 固定连线、INT 的实际配置选择恢复局部连通关系，并用 tile_type 的 site_pins 绑定 CLB 引脚与 SLICEL/SLICEM 槽位。不能从线名中的 `L`、`M`、`LL` 猜测槽位。INT 中标记为 `default` 的常量路径只在该目的端没有已选连接时加入；`hint` 不加入导通图。

以 PS7 `MAXIGP0AWADDR25` 为起点，已追到输入暂存、原始/暂存地址的选择、读写地址汇合及后续分发。这里的“暂存”由实际 FF 输入选择和连线支持，不是由相邻位置推测。进一步找到八个 LUT 组成的十六路选择表：按内部四个已暂存输入穷举，十六种输入各有对应选择输出。该局部表的逻辑值已验证，完整地址事务的有效条件和时序尚未仿真。

其中传感器接口主寄存器分支已追到地址位 14、15 的分区选择、请求状态翻转、后续采样以及 XOR 形成的局部请求脉冲，并逐项绑定写数据位和多个低地址译码。偏移 `0x10` 的数据位 0、`0x18` 的模式位及 `0x0c` 的行周期已对应到局部电路，详见 [SENSORIF 局部逻辑](FPGA_SENSORIF_LOGIC.md)。不能把接口请求脉冲称作物理曝光起点。

基础布线分析器还原 INT 可变连接和已取得的固定连接；[research/fpga_clock_io.py](research/fpga_clock_io.py) 已扩展实际配置的部分时钟和右侧 I/O 路径。新增 [research/fpga_logic.py](research/fpga_logic.py) 支持普通 LUT、触发器数据选择、CARRY4 与 F7/F8；行周期后的十七位减 54 运算已穷举十六位输入核对。两路输出涉及的 135 个触发器已核对共同的时钟分发路径，并按显式边界和合成配置复现行/帧周期。完整时钟原语电气行为、RAM/SRL、原厂网表、时序约束、板级传感器接线和物理积分边沿仍未恢复。追踪在未覆盖资源处结束时，不能据此声称实际电路不连通。

## 可重复复核

[research/fpga_bitstream.py](research/fpga_bitstream.py) 接受已解交织的固定官方 bootimage 字节，先检查全镜像和 PL 分区哈希，再解析分区与配置报文。它只返回元数据，不输出改写后的固件或可装载包。

保存后的程序已实际重跑得到上述结果。截断 bootimage 被固定输入校验拒绝；直接对截断的 PL 配置数据解析时，报文长度检查也拒绝接受。没有安装新的分析依赖。

新增 [research/fpga_frames.py](research/fpga_frames.py) 对固定版本的 PL、part、tilegrid 和两份 CLBLM segbits 逐一验证 SHA-256，再运行帧映射、CRC、原始 ECC 与 LUTRAM/SRL 屏蔽复核。保存后已实际重跑，得到上述 14780/16 帧、两处 CRC 通过及 33→26 处 ECC 差异结果。输入数据保留在离线分析进程内，模块本身不联网、不自动读取任何设备或输出可刷配置。

公开数据库各项 URL、字节数、SHA-256 与本轮结果保存在 [research/fpga-database-manifest.json](research/fpga-database-manifest.json)。另外在内存副本翻转一个 FDRI 数据位，原配置流 CRC 检查正确判为不匹配；原始输入没有改变。

## 后续缺口

配置报文只说明“这些位如何配置进 FPGA”，不能自行说明哪一组 LUT、触发器与布线实现了 SENSORIF 的开始控制、同步发生器或传感器连接。

帧已对应到相符器件的物理资源；仍需沿已知总线地址、接口寄存器和传感器输入输出追到实际控制逻辑。局部连线恢复不是完整网表或硬件时序验证。不能把配置中的 START 命令误解为拍照时的曝光开始——它属于 FPGA 上电配置流程。

与本次目标直接相关的固件配置和积分时机缺口见 [SENSOR_EXPOSURE_TIMING.md](SENSOR_EXPOSURE_TIMING.md)。当前没有新的 FPGA 同步补丁可安装。
