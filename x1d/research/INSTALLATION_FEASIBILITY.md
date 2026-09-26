# 第一代 X1D 增强的安装可行性

对象仅为官方 X1D-50c **1.25.0**，不是 X1D II 或 X2D。以下为离线字节校验与静态代码结论，未读取 X1D 实机版本、启动状态或 fuse，未连接、刷写或执行包内程序。

**当前不能承诺增强固件能够部署。** 已定位正常 CIM 更新链及系统分区切换，也已复核原包校验；修改包被机身接收、成功运行和失败后恢复尚未验证。已检查的接收链使用 AES 解密与 MD5 内容校验，不能把“必须取得厂商签名”作为本型号已经证实的障碍；这同样不是自定义固件已获官方支持或必定可装的证明。

## 固定输入与校验

官方输入：[X1D_v1_25_0.cim](https://cdn.hasselblad.com/firmware/X1D-50c_Firmware/1.25.0/X1D_v1_25_0.cim)，63,410,176 字节，SHA-256 为 `1b224ebe1f53d04a4352897c1ac1f50bc858d08048957382e4cb51ab16a5adf2`。完整清单见 [baseline-manifest.json](baseline-manifest.json)，调用与脚本位置见 [installation-evidence.json](installation-evidence.json)。

`prepare_baseline.py` 已复核原包声明长度、format 3 私有头内容校验和四个载荷的内容校验，全部一致。参考解包器只用于解析固定版本常量，不执行其代码，不在成果中保存密钥材料；它不是官方打包工具。

| 层次 | 1.25.0 已定位的行为 | 结论边界 |
|---|---|---|
| 公开头 | `Cim::PublicHeader`，128 字节；含文件标识、part number、版本、生成时间、格式、加密标志、文件长度。`0x2b954` 读取，`0x2c63c` 分字段，`0x2c0c0 → 0x2d158` 检查字段长度 | 此 `isValid` 主要是结构/长度检查，不能当作严格机型授权或防降级校验 |
| 加密 | `EncryptedFileReader` 和 `AES_set_decrypt_key` / `AES_cbc_encrypt` | 对称加密封装，不等于公钥数字签名 |
| 容器完整性 | format 3：`0x30314 → 0x30a40 → 0x2d6ac`，MD5 摘要后比较；`0x352dc` 为内容摘要辅助函数 | 原包私有头校验已独立复现；不生成或接收修改包 |
| 载荷完整性 | `0x342c8` 解包，`0x34a08` 摘要，`0x34a44` 比较；失败会向升级入口返回失败 | 原包四项一致。解包成功不等于已经写入相机 |
| 数字签名 | 上述接收/解包路径未见公钥验签调用；导入表亦未见常见 RSA/DSA/ECDSA/EVP 验签接口 | 有界静态结论，不把符号搜索当作整机绝无认证的证明 |

摘要辅助函数传给 `QCryptographicHash` 的算法值是 1，对应 MD5；语义交叉依据为 [Qt 文档](https://doc.qt.io/archives/qt-5.15/qcryptographichash.html)。版本号、HW compatibility 等字段存在，但本轮未闭环所有外层筛选和当前机身对重新封装版本的接收条件；不据字段存在宣称有严格防降级，也不宣称任意版本均可安装。

## 正常更新实际写什么

已知用户入口是 SD 卡 CIM，经相机的 Service / Firmware Update 检查更新。包内 `upgrade_from_slot.sh` 也通过 `com.hasselblad.upgrade` 的 `Check` / `Upgrade` 调用这条链。`Upgrade::Engine` 在 `0x3a8a8` 读取包，`0x3adc8` 逐项解包，通过后准备升级，再由 `preUpgradeCompleted` 启动脚本。没有运行这些入口。

`hbl-upgrade` 根据 `current_bootpart` 选择另一组 boot/root 分区，创建文件系统，展开 rootfs，并从 rootfs 复制 Linux 内核和 DTB 到相应 boot 分区。随后运行 `program_nodes.sh`；这一步会依次涉及 FARM、SPC、FX3、触控控制器和 SUC，具体由板型分支决定。它不是仅替换一个 JPEG 程序的无关紧要操作。

包内包含 `uboot` 载荷，但本版脚本明确不更新 U-Boot，只修改其环境中的启动命令和升级标志。JPEG/回放增强目前定位在 Linux 用户态的 `jpeg-daemon`、`storage-daemon`、`victory-gui` 及有关配置；尚无因该方案必须修改 Linux 内核、引导程序或控制器固件的证据。不过，若沿原整包脚本安装，即使只改用户态代码，也不能忽略其他控制器更新的副作用。

## 回退与启动认证

包内 U-Boot 默认 `bootcmd` 有一次试启动机制：发现 `upgrade` 时选择另一组分区、清掉该标志并以 `status=1` 启动；成功进入后，`hbl-post-upgrade` 把 `current_bootpart` 切到新分区。若提交新分区前发生失败，旧分区仍有成为下次启动目标的代码依据。

这不是已验证的整机恢复保证：包内 U-Boot 本次并不会写入实机，实机环境未知；post-upgrade 提交也不能直接等同所有相机功能健康。FARM、SUC 等控制器不受这组 Linux 分区切换的完整保护。`program_nodes.sh` 的 SUC 失败分支会重试、必要时尝试擦除并返回致命错误；其重试仍传入同一个 `SUC_FW`，不能仅根据日志文字把它称为恢复旧固件。

包内 U-Boot 的 IVT `csf` 指针为零；按照 [NXP/Freescale AN4581，§3.1](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/imx-processors/112842/1/AN4581.pdf)，该字段用于指向 HAB 认证数据。这仅说明这个包内引导镜像未通过该指针附带 CSF；不能据此判断当前机身的 ROM/fuse、实际引导器或后续组件认证状态。

## 两类部署方向的当前判断

1. **经正常更新入口安装修改 CIM：仍待验证。** 已有格式、内容校验和写入链证据，尚无官方认可自定义包、实际接收条件和可靠恢复的完整证据。本轮不制作可刷包，也不请求立即刷写。
2. **临时加载单一用户态组件：尚无已确认的正常开发入口。** 镜像中的 SSH 配置和内部构建下载脚本是工程痕迹，不等于公开 SDK、用户可用登录权限或受支持的临时部署流程。未连接内部地址、尝试登录、猜测凭据或开启接口，不把这些痕迹列成可执行方案。

源码范围见 [SOURCE_AND_FLASH_SCOPE.md](SOURCE_AND_FLASH_SCOPE.md)：开源组件包与固件中的 QML/脚本，不等于相机专有组件的完整可编译源码，也不自动提供自定义固件的安装支持。后续仍可做可审查的离线组件修改；实机部署与性能收益应继续明确标为未验证。
