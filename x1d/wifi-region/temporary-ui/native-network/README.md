# 热点网络原生候选

本目录迁移 `temporary-ui/network.sh` 及实际生成的 `temporary-ui/build/dhcp.sh` 的固定操作。`temporary-ui/dhcp.sh` 并不存在；旧构建器从 `wifi-region/hotspot-dhcp.sh` 生成该材料并把目录替换成 `/run/hbl-hotspot-ui`。

当前是**离线候选，未装机，未运行 ARM 产物，未联网**。未修改原页面池、`entry.cpp`、旧构建器、其他 Agent 文件或原脚本。

## 固定接口

| 生产路径 | 允许 argv | 输入与输出 |
|---|---|---|
| `/run/hbl-hotspot-ui/network-native` | 严格一个参数：`start`、`dhcp`、`restore` | 无自由路径/接口/命令参数；退出码 0 表示该固定操作成功 |
| `/run/hbl-hotspot-ui/dhcp-native` | 严格一个参数：`bound`、`renew`、`deconfig`、`nak`、`leasefail` | 读取 udhcpc 的 `interface`、`ip`、`subnet`、`router`、`dns` 环境变量；接口必须是 `wlp1s0` |

`bound`、`renew` 执行地址配置；另外三个固定事件不改变网络。未知事件或多余 argv 返回 2，未知接口/不合法地址返回 63。所有生产入口要求有效 UID 0。

网络 DHCP 命令固定为 `/sbin/udhcpc -f -n -q -t 3 -T 2 -i wlp1s0 -s /run/hbl-hotspot-ui/dhcp-native`。没有持久 udhcpc PID 文件，父程序等待自己创建的前台子进程。回调输入必须在调用前由 udhcpc 正常提供；不是任意命令执行接口。

原 `entry.cpp` 和独立 `main.cpp` 均通过 `/bin/sh /run/hbl-hotspot-ui/network.sh <固定动作>` 调用辅助程序；`radio-mode.sh` 在持有 radio 锁时调用同一路径的 `restore`。父任务可以把已签名的旧 `.sh` 文件改成只含固定 `exec` 的桥，或者直接改 QProcess 的固定程序名。业务规则完全在 C 中；本候选不内嵌 shell，不调用 `system`、`popen`、`execvp` 或 `eval`。

旧 `.sh` 桥和两个 ELF 必须作为同一发行事务接线，继续接受原有签名/哈希门禁。父任务需要把 ELF 加入受授权文件集合、安装/运行副本一致性校验及恢复材料；本目录不替父任务修改这些门禁，也不把源码存在或离线编译当成已完成生产接线。

## 保留的正常行为

- `start` 仅接受原厂 driver 标记、停止的 network-manager/hostapd、`WIFI_power=false`、没有现有 IPv4 地址且没有本工具 started/PID 标记的状态。D-Bus 只发固定的 `Properties.Get`。
- 保存 band/infra/ap/up 四项后，先写 started，再按旧顺序执行 `wl down → ap 0 → infra 1 → band auto → scansuppress 0 → up`。
- WPA 仍使用 `/usr/sbin/wpa_supplicant -D nl80211 -i wlp1s0 -c /run/hbl-hotspot-ui/wpa.conf`，配置只含固定 ctrl 路径及 `update_config=0`，日志仍写 `wpa.log`。最多检查控制 socket 8 次、间隔 1 秒。
- `restore` 停止本工具的 WPA，按旧顺序清理接口地址、恢复原 band/infra/ap，仅在原 up 为 1 时重新 up。保留旧快照字段，清理原 conf/PID/started/bound/dns/client.sock，并清理新增 `wpa.start`。
- DHCP 仍使用 ifconfig 的 IPv4/netmask/up，再只使用 router 列表的第一个网关执行原 `route add default`。不改系统 resolver，只写原有 dns 与 ready 标记文件。
- 不改变原厂区域、频段策略、服务启停或任何相机业务。`scansuppress` 仍按旧脚本在 start 设为 0；旧脚本没有保存其原值，本迁移没有声称恢复了未保存的字段。

正常命令顺序在 mock 中与上述冻结源的明确序列逐项比较。快照数值的尾部换行被规范化，恢复后的取值保持一致；未声称所有文件字节、错误时点、超时行为完全等价。

## 所有权、锁与 PID

固定 runtime 目录必须是真实目录、root 所有且组/其他用户不可写；不要求把现有 0755 目录改成 0700。状态文件必须是 root 所有的普通单硬链接文件，不能组/其他用户可写；读取和写入使用 `O_NOFOLLOW`、目录 fd 和固定 basename。新状态原子替换，权限 0600，进程 umask 为 077。日志在验证现有 inode 后才截断。

锁顺序为：既有 radio 锁 → 本工具 operation 锁 → lease 锁。

| 操作 | 锁 |
|---|---|
| `start`、`dhcp` | 先取得原脚本的 `/run/hbl-four-module/radio-mode/lock`，再取得 `network-native.lock`；radio 目录沿用原要求 root:0700 |
| `restore` | 只取得 `network-native.lock`、`lease-native.lock`；调用者可能已经持有 radio 锁，不能重复获取 |
| udhcpc 等待期间 | 保持 radio 和 operation 锁，释放 lease 锁，让回调执行；之后重新取得 lease 锁检查/清理标记 |
| DHCP 回调 | 只取得 `lease-native.lock` |

两个新增锁位于固定 hotspot runtime 中，都是 0700 目录。释放前核对取得时的 inode/device；锁争用返回 62，不抢占未知/残留锁。强制杀死进程可能留下锁；该状态阻止继续猜测或并发恢复，当前没有自动清锁操作或自由路径 CLI。

WPA PID 文件仍是十进制 PID 加换行。新启动另外保存 `/proc/<pid>/stat` 的 starttime 到 `wpa.start`。恢复要求完整 NUL 分隔 argv 精确匹配上述 WPA 固定命令，并核对 starttime；PID 0、1、符号、溢出及非数字输入均被拒绝。

旧 shell 启动的 WPA 没有 `wpa.start`，仍可恢复：必须匹配完整旧 argv，并在发送 SIGTERM 前连续读取 starttime，拒绝两次读取之间的身份改变。daemon 是否已被 init 收养不影响判断，不以 PPID 作为所有权证明。进程已消失或已是 zombie 可继续恢复；活着但身份不明的进程不被终止。对这种继承的 daemon 只发 SIGTERM，最多等待 4.9 秒，不升级为 SIGKILL。

旧目标内核没有在本实现使用 pidfd；两次 `/proc` 检查不能提供 pidfd 的原子保证。候选保留这一明确边界，不称作彻底消除了检查与 kill 之间的 PID 复用窗口。

程序自己创建的短命命令具有独立进程组；DHCP 回调中的 ifconfig/route 留在 udhcpc 所属组。发生超时/取消时先 TERM、再 KILL 自己拥有的组，并等待直接子进程；使用 `waitid(...WNOWAIT)` 保留 zombie 的 PID，避免先回收 PID 再清理其组。udhcpc 即使先退出，也会在返回前清理它可能遗留的回调组。这个过程只面向本次创建的子进程，和继承 WPA 的保守恢复规则不同。

## 有意修复与输入拒绝

1. 原热点脚本没有自身锁。候选新增 operation/lease 锁并与既有 radio 锁协作，阻止恢复、DHCP 回调与驱动切换穿插。
2. 原 DHCP 没有 IPv4 验证。候选在任何网络修改前检查十进制四段 IPv4、0–255、禁止歧义前导零，掩码必须连续；全部 router/DNS token 均须是 IPv4。每个列表最多 16 项、512 字节，IP 单项最多 15 字节。缺失环境字段、未知接口、选项/域名/命令文本均拒绝；空 router/DNS 列表保持允许。
3. 原脚本的 UID/目录检查不足以覆盖状态 symlink、硬链接或可写权限。候选加强文件所有权、不跟随链接、原子状态写入和 ELF 回调文件检查。
4. 原恢复仅用命令行字符串包含 wpa.conf 判断 PID 所有权。候选改成完整 argv、PID 范围和 starttime 校验。
5. 原 `start` 中途失败会保留改变后的接口等待用户恢复。候选主动尝试恢复四项原状态；恢复失败返回 71 并保留 started/快照，不虚报已恢复。
6. 原 `! systemctl is-active` 会把各种查询失败都看成不活跃。候选只接受明确的 inactive 返回值 3；读取 ip/wl/D-Bus 失败、未知值或超长输出都阻止开始。
7. 原 DHCP 可能使用先前的 bound 标记。候选每次申请先清除旧 bound/dns；回调失败及前台 client 失败后，在可取得 lease 锁的情况下清理标记，避免把部分操作误认成新的成功。
8. 原工具调用没有统一截止时间。候选固定 5 秒一般命令上限、25 秒 udhcpc 上限，并清理本轮的短命子进程组；不无限等待失控命令。
9. 原恢复可能在读取坏快照之前就清理接口。候选先校验完整快照；清理成功后最后移除 started，恢复/清理失败仍保留可核对的标记。

不额外修复旧 `route add default` 的重复路由行为。若 `renew` 遇到已有路由而 route 返回失败，候选也返回失败并撤销成功标记；不会用 `replace default` 擅自覆盖其他路由。地址配置成功后若路由/文件写入失败，可能留下部分地址状态；明确的 `restore` 仍是最终恢复路径。锁残留时不会绕过锁删除正在运行的回调可能使用的文件。

## Radio-mode 的范围

`radio-mode.sh` 包含固件摘要、firmware search sysfs 的备份/恢复、rmmod/modprobe、driver=unknown 的失败事务、systemd 服务与 AP 就绪等待，超出本批网络客户端迁移。它的业务仍留在原脚本，没有被本目录伪装成已原生化。

本候选保持该脚本已有的锁协议及持锁调用 restore 的边界，未操作驱动、服务或 sysfs。后续迁移需要独立保留其 boot/0/1/2 状态事务及失败恢复；不能只把原 shell 文本藏进 C。

## 离线验证与产物

仓库根目录执行：

```powershell
py -3.14 -B x1d/wifi-region/temporary-ui/native-network/build.py
```

只启动本项目已有 Zig 编译器和 Windows mock 测试程序。生产 ARM 文件不会被执行。编译产物为静态 ELF32 ARM / Cortex-A9，已检查没有 PT_INTERP。未安装依赖或运行 systemctl、wl、udhcpc、ifconfig、route、D-Bus 命令。

当前 [mock-result.json](build/mock-result.json)：38 个用例、1,281 条断言、69 个逐 I/O 故障注入点通过。覆盖正常命令顺序与参数、旧 PID 无 starttime、完整 argv、PID 改换/消失/zombie/终止超时、start 回滚成功/失败、非法恢复快照、旧 bound、DHCP 回调失败、client 结束失败的标记清理、遗留 lease 锁拒绝恢复、radio 持锁调用 restore、输入拒绝与固定 CLI。

[build.json](build/build.json) 绑定 native 源码、mock、构建脚本、旧脚本、交接时 entry.cpp 与 X1D 1.25.0 rootfs inventory，以及两个 ELF 的 SHA-256。固定系统工具路径由该离线 inventory 支持；父任务另报告只读核实了目标上的 systemctl/dbus-send/wpa_supplicant/udhcpc 可执行路径，本子任务没有进行设备访问。

mock 运行的是实际 C 状态机和 WPA 所有权/终止策略，所有效应均为内存替身。POSIX 层的 fork/exec、进程组回收、文件系统竞争和目标 BusyBox/驱动行为仅已编译并审阅，尚未在运行环境执行；不能把 fault injection 说成已证明内核进程组或真实网络恢复。整机连接、吞吐、断线/恢复、最终签名包装和 GUI 性能尚待父任务后续获授权验证。
