# X1D Full JPEG 配置候选

对象仅为第一代 X1D-50c 官方 1.25.0。已生成实际 `configstore` ARM 组件候选，并用 Unicorn 执行原版与候选的构造函数、整数 setter 和范围判断。没有启动相机服务、访问相机或制作 CIM 升级包；这还不是完整回放增强。

## 修改

- [生成脚本](../tools/patch_full_jpeg.py)
- [候选组件](../artifacts/full-jpeg-v1/configstore.elf)与[补丁清单](../artifacts/full-jpeg-v1/manifest.json)
- [ARM 测试](../CodeTests/full_jpeg/test_arm_config.py)与[测试结果](validation/full-jpeg-config-arm.json)

输入 `configstore` 为 201000 字节，SHA-256 为 `0d24d3d3787bab08ab2c0b4f4c0f3d72831d2216eddc770a60b6742174ce4be1`。脚本拒绝不同基线和重复应用。

原构造函数 `0x23570` 在 `0x23f14` 已调用 `Version::productID()`；产品号 2 对应 Wedge／X1D-50c，绑定见[源码与闪光范围](SOURCE_AND_FLASH_SCOPE.md)。补丁只重排其后 `0x23f18–0x23f48` 的 52 字节尾部：产品号 2 时，将 `jpg_size`、`jpg_size_minval`、`jpg_size_maxval` 一并置 2（Full）。其他产品仍走原值和原分支。原板型专属字段 `this+0x4c8` 保留原行为，ELF 大小、动态链接和异常表保持原样。

这让保存 JPEG 的新流程选择 Full，取代 Quarter；没有增加第二份 Quarter 成片，也没有改 RAW-only 的格式选择。JPEG 编码仍走原 `jpeg-daemon` 链：`Encoder::onAdded` 的 `0x19798` 从代理读取尺寸，`0x197f8` 存入本次转换请求，`0x178c4` 将该尺寸传入 `StorageProxy::image`。应配合[编码失败传播候选](JPEG_FAILURE_PATCH.md)，不能仅改尺寸后忽略错误。

## 旧设置与默认恢复

只改默认值不足以处理已有 Quarter 设置，因此候选同时收窄 X1D 的范围。原 `config` 元对象中 `jpg_size` 为属性 270，可写；紧随的两个范围属性为只读。原 setter `0x244e4` 经 `0x24298 → 0x22908` 校验，按 `%1_minval`、`%1_maxval` 读取范围，再由 `0x22b2c–0x22b4c` 比较。特殊值表只含 `SV` 项，不放行 `jpg_size`。

SQL 加载和设置恢复中已查到 `QObject::setProperty` 调用（`0x18f58`、`0x19c7c`、`0x1a910`、`0x1b014`），没有据此声称数据库已实机验证。离线实际执行相同 setter 后，X1D 的旧值 1 被拒绝，构造后的有效值维持 2；Full 值保持有效。原数据库文件没有改写，旧值可能继续留在数据库，实际启动时按原校验机制拒绝。默认恢复所用的新 `config` 对象也得到相同的 Wedge 范围。

## 验证与未完成项

5 个测试方法通过，结果中记录 24 个场景：6 种产品号的完整配置对象逐字节比较；X1D 的 6 个输入值；其他 3 种产品的 12 次属性写入。另有原版允许重新设 Quarter、候选拒绝的对照，以及固定哈希、只读范围属性、装载入口和 ELF 结构检查。寄存器和栈返回均核对。

测试执行实际 ARM 分支；Qt 字符串、属性访问、通知以及产品号读取使用有界替身。没有启动 SQL 数据库、D-Bus 服务或实际编码器。这证明候选配置逻辑，不证明相机已生成 8176×6128 成片，也不证明拍后或回放提速。

内嵌预览、写入完成登记、GUI／provider 的统一 JPEG 选源、实际编解码颜色及内存、正常安装和实机性能仍需完成。不要将本候选独立标为可安装固件或完整回放功能。
