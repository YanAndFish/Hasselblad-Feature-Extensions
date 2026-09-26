# 内置系统存储容量：实机只读结果

2026-09-10 03:36:36+08。用户询问存放Linux系统与原厂固件源文件的内置“ROM/硬盘”容量。本次读取系统MMC主用户区的可寻址总容量，**结果为7,818,182,656字节，即7.818182656 GB或7.28125 GiB**，可理解为8GB级内置存储；未读取芯片型号或厂商标称容量。

| 固定读取字段 | 实际值 |
|---|---|
| 块设备 | `/dev/mmcblk3` |
| MMC设备类型 | `MMC` |
| removable标志 | `0` |
| 主用户区扇区总数 | `15269888` |
| 当前启动root参数 | `/dev/mmcblk3p2` |
| 每个容量计数扇区的单位 | 512字节 |
| 精确乘积 | `15269888 × 512 = 7818182656`字节 |

## 对象与单位依据

当前root参数指向所测盘的分区，实际设备类型为MMC；结合已核官方1.25 Wedge板型的USDHC4/eMMC与`mmcblk3pN`映射，可将它关联到内置系统存储，见[既有板级证据E1/E2](../recovery-review/20260910-usb-sd/EVIDENCE.md)。`removable=0`本身不足以证明焊接内置：Linux MMC驱动有意不设置该标志，不能把它单独当作物理连线证明。

Linux3.14同代ABI实现中，[`part_size_show`](https://raw.githubusercontent.com/torvalds/linux/v3.14/block/partition-generic.c)读取缓存扇区总数；[MMC容量初始化](https://raw.githubusercontent.com/torvalds/linux/v3.14/drivers/mmc/card/block.c)明确以512字节为`set_capacity`单位。容量以整数相乘保存，GB按10^9、GiB按2^30换算，未把逻辑块大小、压缩包大小或空闲空间混入计算。

这不是已用/剩余空间，也不等于所有控制器存储总和。FARM NOR、FX3 EEPROM、芯片BootROM以及eMMC独立启动/保留区域未在本次测量；没有枚举外露SD卡或读取分区、文件系统与原始块内容。

## 唯一请求及验证

```text
cd /sys/class/block/mmcblk3&&/bin/cat device/type removable size;/usr/bin/awk '{for(i=1;i<=NF;i++)if($i~/^root=/){n++;r=$i}}END{print n==1&&r~/^root=\/dev\/mmcblk3p[1-9][0-9]?$/?r:"UNKNOWN"}' /proc/cmdline
```

来源任务核对通过后，执行了此205 ASCII字节常量一次。早期容量候选均未执行。awk统计所有完整`root=`参数，只在恰好一个且指向允许的`mmcblk3p1–99`时返回该字段；相邻/非相邻重复、其他根设备、UUID、缺项或异常均输出UNKNOWN或被主机拒绝，不返回其他启动参数。

`/bin/cat`与`/usr/bin/awk`的原包alternatives均指向已核BusyBox1.23.2。新增访问仅为三个固定sysfs属性与缓存的启动参数，未读取CID、序列号、账户、照片或原始块。Linux[类型字段](https://raw.githubusercontent.com/torvalds/linux/v3.14/drivers/mmc/core/bus.c)、[removable字段](https://raw.githubusercontent.com/torvalds/linux/v3.14/block/genhd.c)及[`/proc/cmdline`](https://raw.githubusercontent.com/torvalds/linux/v3.14/fs/proc/cmdline.c)均从内核缓存对象输出，未添加节点探测或介质读写。这是同代上游ABI依据，不是实机内核逐字节匹配的声明。

[6项必要离线验证](../CodeTests/usb_diagnostic/test_sutest_capacity_once.py)通过，含固定命令/CRC、精确整数换算、错误类型、缺/多字段、截断、UNKNOWN、重复root、其他设备/UUID、分区边界与超时。实机一次OUT完整发送512字节，一次IN收到512字节；命令、关联、CRC、结果字及完整四行白名单通过，主机耗时79ms，无迟到FARM回复、无重试；枚举、WinUSB与设备句柄均关闭。

不可变[结果JSON](validation/hardware/x1d-sutest-capacity-20260910-authorized-once.json)已读回核对，不保存原始回包、其他stdout或stderr。单次OUT、最多两次IN与共享6秒主机期限沿用前次路径；机内没有硬截止。awk退出成功不单独证明cat成功，因此还必须具备全部四项完整合法输出，本次满足。

此次完成后累计六次硬件应用请求并已停止，没有第七次，也没有Retry、UpdateNodes、刷写、设置修改、重启或试拍。之前FARM even/odd与SPC三份源文件匹配官方1.25的结论见[完整性报告](SOURCE_FIRMWARE_INTEGRITY.md)，两次读取分别保留证据。
