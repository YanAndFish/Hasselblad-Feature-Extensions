# X2D 4.2.0：地区配置与回读

记录：2026-09-12。以下为固定官方固件的静态分析及离线模拟，来源哈希见 [sources.json](sources.json)。没有执行地区写入、维护握手或重启；既有普通 USB getter 的成功不能替代地区维护通路的实机验证。

## 持久来源及运行效果

`camera-system` 的 `ProdInfo::setWifiRegion`（ELF VA `0xeab30`）写入生产配置字段 `Identity/WifiRegion`。静态路径为 `/factory_data/settings.ini`，分区对应 `/dev/block/by-name/factory`。这些是固件中的路径字符串，本轮没有访问真实设备路径。

`setConfigParam` 涉及分区写状态切换、QSettings `setValue` / `sync` / `status`、恢复只读与 `readAll`。它具有写盘副作用。

| 枚举 | 值 | 固定 4.2.0 行为 |
|---|---:|---|
| `CN` | 6 | GUI 提供 5 GHz；WMS 映射为 `CN` |
| `JP` | 8 | GUI 仅 2.4 GHz；WMS 映射为 `JP` |
| `2gOnly` | 2 | GUI 仅 2.4 GHz；WMS 同样映射为 `JP`，但枚举并不等于 JP |

GUI 的直接判断位于 `DisplayConverter::setWiFiModeList`（`camera-gui` VA `0x1049678`）。`dji_network::is_2gonly_country`（VA `0x123c8`）也限制 JP 的 5 GHz 选路，因此不只是菜单隐藏。CN 不受这条 2gOnly 检查，不代表取消 CLM 或国家信道限制。

WMS 另将国家配置经临时文件、fsync 和 rename 保存到 `/data/misc/wifi/user_config.conf`。它与 factory 字段是两个持久层；正常初始化会从 factory 派生期望地区，所以只改 WMS 文件可能被覆盖。

正常启动链已核：`ProdInfo::readAll` → `ProdinfoObjectImpl::wifi_region`（`0x73b28`）→ `SystemObjectImpl` 初始化回调（`0x82428`）→ `WmsCtrl::setWifiRegion`（`0xc03e0`）缓存期望值 → 就绪后 `updateWifiRegion`（`0xbf270`）。WMS 自身地区变化信号与 linkUp 回调均可触发更新；GUI 初始化和地区信号也会重建列表。成立条件包括配置有效可读、对象正常新建、网络服务就绪且国家设置成功；异常挂载等路径未全部验证。

用户接受下一次正常完整启动后生效，不要求即时刷新。维护进程回读成功不证明独立的 GUI / camera-system 缓存已即时更新，也不等于获得现在重启的授权。

## 维护通路及回执限制

`camera-test` 注册 `ProdConfig` 命令号 `0x31`；属性索引 `13` 为 `wifiRegion`，长度为一个 u32。功能号 `1` 为 set、`2` 为 get。功能号 `3` 会初始化配置，不能作为读取；本研究没有构建或发送这些设备请求。

静态 USB 路径为 FunctionFS 控制消息 → `msg2dbus` → `UsbhostHandler` 测试消息 → `camera-test`。回复经过 TestdRelay 返回 USB/TCP 路由。`camera-test.rc` 使用 auxiliary 类，与单独的 test-mode 服务不同；全局 auxiliary 启动条件仍未完全还原，实机是否接受维护消息未验证。

`ProdConfig::set` 用 `QObject::setProperty` 返回值判断成功；Qt 元调用未把 `ProdInfo::setWifiRegion` 的 bool 明确传回该状态。因此“收到 set 成功回复”不能单独证明保存成功。

每次 get 构造新的 ProdInfo 并读取生产配置。成功 get 的 236 字节正文从三个 u32 开始：状态 0、属性索引 13、地区值。`0x553c0` 写索引，`0x5537c` 起写转换数据；`fromQVariantToU32Array` 的单字分支调用 `QVariant::toUInt`。

SUTest 内层回复为 252 字节：前三个 u32 回显请求头，第 4 个 u32 存正文 CRC16。第三个回显字段的业务名称尚未确认，不能直接叫序列号。CRC 仅覆盖 236 字节正文，算法交叉符合 `binascii.crc_hqx(data, 0)`，不覆盖前三个头字段。

固定固件 USB 回复外层静态结构为 signal 9、origin 5、destination 8，正文含长度 252、内层回复及三个填充字节；模型按 260 字节严格验收。真实 USB 分包、混合消息、超时及回复新鲜度尚未联调。完全相同头和值的旧回复不能靠 CRC 排除。

## 证明范围与进度

- 写后 get 读到 6：只能证明该时点维护进程从生产配置读到目标值。
- 获授权正常完整启动后再次 get 仍为 6：可补跨启动持久证据。
- 菜单包含 5 GHz、实际网络可用：另行验证运行效果。
- [离线模型](../../CodeTests/README.md) 验证了响应判定规则；未实现传输客户端、地区写入或设备联调。

用户要求地区修改后回读，该要求不扩展到普通闪光发送。用户提供过日版修改后启用 5 GHz 的案例线索；未取得其原始命令或前后字段记录。机内 WifiRegion 与官方销售、购买及保修记录不是同一证据对象，本研究未找到修改销售后台记录的接口。
