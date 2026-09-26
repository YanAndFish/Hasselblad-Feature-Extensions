# 验证说明

所有自动化测试使用人工响应、本机回环地址或固定离线固件文件，不访问相机。验证结果覆盖软件边界与静态证据，不能单独证明实机连接或闪光同步可用。

| 命令 | 覆盖 |
|---|---|
| `npm test` | 29 项 Node 测试：保留原 17 项参数/USB 验证，新增 12 项固件消息与本机 ADB 替身验证，覆盖真实模板解码、脱敏、分包/粘包、版本哈希门控、唯一目标、拒绝/错误/超时/坏包、空缓冲区、服务不可用和并发。所有 ADB 测试使用随机回环端口，不连接设备或实际 ADB server。 |
| `npm run build:native` 后 `.\dist\native\HasselbladUsbReadOnly.exe selftest` | 64 项人工 USB 检查：控制端点选择/错误布局拒绝、固定请求、禁止 ID/零序号、正确回包、错误字段拒绝、分段拼接及完成后拒绝重复处理。另以人工读取委托确认未知版本、未运行及陌生字段立即停止后续项。不枚举、不打开设备。 |
| `npm run test:ui` | 9 组真实 Electron 交互检查：保留原 8 组，增加固件消息详情、人工来源、未验证实机标记及 ADB 适配器隔离。原生文件选择在测试中被固定人工文件替代。 |
| `npm run package:local` 后 `npm run test:package` | 在实际打包目录启动 `Hasselblad-Debug.exe`，执行同一组 9 项交互验证，核查所载应用目录确实属于该构建。 |
| `py -3.11 -m unittest discover -s CodeTests -p 'test_*.py'` | 2 项离线边界测试：transfer range 及参考源码字面量解析，拒绝执行表达式。 |
| `py -3.11 tools/trace_eshutter.py` | 对固定 ELF 执行哈希、14 条指令、6 个字符串及模式跳表验证并生成反汇编证据；不执行固件。 |
| `py -3.11 tools/trace_debug.py` | 41 处固定 getter、虚表、类型、double 位模式、缓存读取/初始化检查、写分支及拍摄权限检查；生成有限反汇编与能力范围记录。 |
| `py -3.11 tools/trace_usb.py` | 对官方固定 ELF/PC DLL 执行哈希与 39 处 USB 路由/虚表/端点/长度/版本格式复核；不执行第三方程序。 |
| `py -3.11 -B tools/trace_firmware_observer.py` | 10 个真实日志点的 60 项核对、12 个通路调用和 4 个配置文件哈希；保留命令分发、机内回传与动态串口路由的版本绑定。 |

界面截图与结构化结果位于 `research/validation`；打包版结果位于其 `packaged` 子目录。自动测试截图展示人工值或静态研究内容，没有设备采集数据。Electron 自动化窗口使用 `--smoke` 隔离临时状态，后端不给它实机适配器，结束后关闭。经协调后执行的实际读取另存 `research/validation/hardware/`，不与模拟测试混记。

首次输入准备另外核验官方 CIM 的 SHA-256、8 个外层条目内容校验、OTA 哈希和提取 ELF 哈希。相关结果见 `research/firmware-manifest.json`、`binary-manifest.json`、`eshutter-evidence-checks.json`。测试通过次数不应被写成实际硬件能力完成度。
