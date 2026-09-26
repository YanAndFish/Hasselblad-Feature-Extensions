# X1D Wi-Fi / SSH 诊断入口

2026-09-10。静态输入为官方 **X1D-50c 1.25.0**，另有 **1.24.0 开源组件包的既有目录核查结果**；二者分开使用，均不代表未知版本实机的全部运行状态。本轮没有从当前电脑探测相机网络，没有建立 SSH 登录。

**当前可用证据是 SSH 服务有响应，认证未通过。** 用户在另一台已连相机热点的 Windows 笔记本上观察到 `192.168.16.1` 的 TCP 22 可达；最初出现主机密钥类型不匹配，服务端提供 `ssh-rsa`。用户按来源任务给出的仅本次连接选项完成算法协商，出现 RSA 主机指纹和密码提示，随后收到 `Permission denied`。用户自行输入的用户名没有验证有效，且明确不知道密码；这些结果不能区分用户名无效、密码无效或其他认证条件失败。没有成功登录，更没有读到机内日志。

## 官方 1.25.0 的正常启动和登录条件

`sshd.socket` 配置 `ListenStream=22`、`Accept=yes`，由 `verylate.target` 的依赖启动。`sshd@.service` 的有效启动行为是 `/usr/sbin/sshd -i`，并依赖 `sshdgenkeys.service`。后者可能在数据目录没有 SSH 主机密钥时生成密钥，因此连到服务也不是绝对无状态变化的被动观察。没有读取任何主机密钥。

| 配置内容 | 证据性质 |
|---|---|
| `Protocol 2`、`PermitRootLogin yes`、`PermitEmptyPasswords yes` | `sshd_config` 中显式生效的行。允许某认证方式不代表账户实际没有密码。 |
| `AuthorizedKeysFile .ssh/authorized_keys` | 指定公钥登录的文件位置，不证明当前已装有用户可合法使用的公钥。没有读取该文件。 |
| `#PasswordAuthentication yes`、`#PubkeyAuthentication yes`、`#UsePAM no` | 注释，不能直接称作显式配置；PAM 另有下述编译证据。 |
| `#MaxAuthTries 6` | 注释；默认数值另从实际二进制核对。 |
| `sshd_config_readonly` | 是另一个文件，不能替代上述实际启动所用配置；未发现本服务使用 `-f` 选择它。 |

此前在用户明确限定授权下，只对官方镜像中已知 `root` 账户的认证字段做过一次分类，结果为非空。没有显示、保存认证字段或推导口令；本轮也没有重读该字段。它只解决“原包是否有该已知账户、是否为空口令”的问题，不证明实机账户一致或提供可登录密码。

## 失败次数：断开连接与锁账户

[离线审计脚本](../tools/audit_ssh_login_policy.py)只读取六份非认证输入，校验 18 条指令，输出[机器证据](validation/ssh-login-policy-static.json)。`usr/sbin/sshd` 为 707044 字节，SHA-256 `2cee4f80cd24136366f943b25ec9305b27e0aa0a59fa37c594900cf71c338211`，版本标识为 `OpenSSH_7.1p2`。

| 问题 | 固定二进制与配置的结论 |
|---|---|
| 默认上限是多少 | 关键字 `maxauthtries` 在 `0xbabdc` 绑定 opcode `52`；分支 `0xd99c→0xe36c` 指向选项字段 `0x2d20`。默认函数 `0xcfe8…0xcff4` 在字段未设置时写入 `6`。有效配置中没有覆盖这一选项。 |
| 达到上限怎么办 | `0x15dbc…0x15dc8` 比较当前认证失败计数；达到上限经 `0x15fd8→0x14640`，记录错误并以 `Too many authentication failures` 进入断开路径 `0x4bd10`。这是单次连接上限的依据，不是跨连接累计封号证据。 |
| PAM 是否编入 | `usepam` 关键字在 `0xba8b8` 绑定 opcode `93`；`0xda40→0xe01c` 实际进入 `Unsupported option` 分支。动态依赖没有 `libpam`，符号没有 `pam_*`。这比仅看到 `#UsePAM no` 更强。 |
| 是否有常见跨连接封禁配置 | 固定 rootfs 文件名核查未发现 `etc/pam.d`、相关 security 模块目录、`pam_tally`、`faillock`、`fail2ban`、`denyhosts` 文件。它只限定于所查组件和名称，不能排除未知版本或其他定制机制。 |

这些结果也与 OpenSSH 7.1p2 上游的[配置实现](https://github.com/openssh/openssh-portable/blob/V_7_1_P2/servconf.c)、[默认上限定义](https://github.com/openssh/openssh-portable/blob/V_7_1_P2/servconf.h)及[认证失败处理](https://github.com/openssh/openssh-portable/blob/V_7_1_P2/auth2.c)相符。厂商二进制证据与通用上游默认分别记录，没有用最新 OpenSSH 行为替代该旧版本。

因此，**没有证据表明用户这次已经锁住相机或账户；也不能保证未知实机无限失败都不会锁定。** `Permission denied` 本身只表示未通过认证。上限统计认证尝试，不能直接换算成还允许输错几次密码。没有进行失败次数实测、修改策略、尝试其他账户或猜测密码。

## 开源包能否给出出厂凭据

此前已实读[官方 1.24.0 开源组件归档](https://cdn.hasselblad.com/firmware/X1D-50c-Firmware/1.24.0/X1D_v1_24_0.tar.xz)：415113824 字节，SHA-256 `79a5a0d4d34b85f8631874a665bbc25dfdeb2da80530b6f38b0c4ff83d02fcec`。外层 1165 条目、70 个组件；它不是完整相机专有工程。详见[源码范围](SOURCE_AND_FLASH_SCOPE.md)。

复核已保留的组件清单，没有独立 `openssh/openssh-sshd`、`shadow`、`base-passwd` 组件；有 `base-files`（21 个外层条目）、systemd、glibc 等。**组件未单独出现不等于所有归档内都没有账户相关文本。** 前次扫描针对成像控制，不能冒充本次账户初始化审查。

当前项目缓存中没有该原包或展开的 `base-files` 内容；按用户要求，本轮没有重复下载这份大包。因此，没有重新逐项复核这 21 个条目的内容，也不能排除它们包含通用初始化文件。尚缺与该机型/版本对应的镜像组装配方、账户设定/出厂初始化输入或明确的官方登录说明；未得到可用出厂口令。

通用 OpenSSH 源码解释如何验证登录、限制失败次数，并不会自动包含哈苏设置账户密码所用的产品构建输入。即使某份脚本含占位符、上游样例或散列，也需证明它对应该机型出厂流程；非空认证字段本身不能直接当作可登录口令。

公开官方页面与 GitHub 的有界检索也未提供经过核实的一代 X1D 默认 SSH 凭据。用户已有合法凭据、厂商明确提供的该设备诊断登录方法，才可能继续正常认证；本报告没有取得这些依据。官方[支持入口](https://www.hasselblad.com/zh-cn/support/)可用于核实服务诊断方法，但不能据此承诺厂商一定提供系统登录密码。

USB 已完成一次 FX3 本地状态成功回复及一次 FARM 单项读取超时，累计两次应用层请求，详见[RAM 诊断报告](FARM_RAM_DIAGNOSTIC.md)。后续离线诊断不依赖 SSH 登录；硬件当前停止，图像施工继续暂停。
