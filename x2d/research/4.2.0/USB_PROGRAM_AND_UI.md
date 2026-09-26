# X2D 4.2.0：经 USB 传程序与使用机内 UI

记录：2026-09-12。用户本轮明确“方向是走 USB”。以下以正常 USB 控制接口为主线，不以 TCP、无线或开启 ADB 作为实施前提。仅离线分析官方 4.2.0；没有连接相机、发送维护命令、写入机内文件、启动 GUI 或停止原厂进程。

## 当前能回答到哪一步

**USB 传入小程序或 UI 资源已有具体候选通路；原厂还提供可显示自定义文字并点击退出的页面，第一阶段 UI 验证可以先不上传程序。** 尚未证明实机接受这条 USB 维护通路，不能把静态代码闭合写成已经传入或已经运行。

| 目标 | 本轮结论 |
|---|---|
| USB 传入文字并显示按钮 | 原厂 HblShell 可运行已有 camera-gui；confirmtest 支持文字、按钮参数和点击退出，静态链成立，未实测 |
| USB 传入图片并显示 | HblShell 文本输入可作为编码分段传输的候选；原厂 imagetest 支持 PNG/JPG。文件接收与完整性核验尚未实现 |
| USB 传入独立可执行程序 | 同一文本承载可研究传输编码后的字节，但还需接收完成协议、长度/哈希核验、匹配 ABI 与可写可执行目录 |
| 直接传入 QML 增加任意页面 | 没有现成入口证据。固件正常 GUI 的 QML 嵌入二进制，检查的 system:/bin 下没有 qml/qmlscene 启动器 |
| 使用原厂测试 UI | 已核实真正的交互处理，不只是名称。它们可作为候选验证工具，普通拍摄状态下的窗口并行、输入和恢复仍待验证 |

## USB 到程序标准输入的静态链

历史普通 USB 读取使用 WinUSB 接口的第二对 bulk 控制端点，见 [USB 协议](../history/USB_READ_PROTOCOL.md)。该读取路径曾成功，但本轮维护信号属于另一类命令，不能沿用六项 getter 的实机通过结论。

```text
USB 控制消息
  → msg2dbus / UsbhostHandler 的测试信号分支
  → USB host 的 testrx 通知
  → camera-test / TestdObjectImpl::onTestRx
  → 长度检查、正文 CRC 检查、TestExecutor
  → HblShell 创建子进程；后续消息写入其标准输入
  → 输出通知、最终结果经原厂测试回复路由返回
```

本轮补齐的固定地址：

- `msg2dbus 0x10ae60..0x10aeb8`：信号 `0x0a` 进入测试消息分支，从外层 `+4` 读取长度、`+5` 取得数据，调用 `UsbhostObject::emitTestrx`。
- `camera-test 0x4fb38`：`onTestRx` 先调用 `isTestMessageOk`，再在 `0x4fca4` 调用 `TestExecutor::execute`。长度标记要求 252，正文 CRC 在 `0x4df2c..0x4df38` 检查。
- 执行器在已有活跃测试时，通过虚表 `+0x70` 调用 `receivedDuringExecution`（`0x4e130..0x4e144`）。HblShell 虚表 `0x1b6618 + 0x80` 指向 `0x967d0`，所以后续文本不是另开一条 TCP 传输。
- HblShell 读取完整命令 `+0x14` 起的 NUL 结尾 UTF-8 文本。初始文本为空时选择交互 shell `-i`；非空时选择 `-c`。运行期间功能字段 1 的普通文本进入 `ShellCmd::write`（`0x96b5c`），转换为 UTF-8 后在 `0x9585c` 调用子进程的 `QIODevice::write`。
- 输出可通过通知回传，`ShellCmd::processFinished` 按进程退出值区分成功/失败；这还不等于任意文件接收成功。`msg2dbus` 的测试回复使用信号 9，见 [回读路由说明](REGION_AND_READBACK.md)。

原厂 `DataTransfer` 操作 1 仍固定 TCP，因此不作为本次 USB 文件路线。HblShell 使用同一 USB 测试消息承载文本，是本轮新增候选。它不要求绕过私有 Wayland 接口检查或无线客户端身份检查。

### 传文件必须补的部分

这条输入是文本通道，含 `strlen`、QString UTF-8 转换和 NUL 结尾写入，不能直接塞入包含零字节的 ELF 或 PNG。固定 252 字节命令中，文本从偏移 20 开始，剩余 232 字节；保留结尾 NUL 后，单包文本最多 231 字节，编码与包序仍须由专用传输实现控制。

可研究将资源编码成 ASCII，经 USB 分段送入限长接收程序，再在机内恢复字节。system:/bin/base64 和 head 均指向随固件提供的 toybox，toybox 内存在对应处理函数；这只是构造接收方案的基础，尚未实现该方案。不能把终端接收调用返回等同于所有字节落盘：`ShellCmd::write` 没有把本次写入的字节数作为分片确认返回。

具体还缺：总长度和边界、分片确认或可确定的接收进度、短写/超时处理、传完后的长度与哈希核验、失败残留处理。执行器在运行期间把后续命令交给当前测试，说明该会话必须串行管理，不能同时混入其他维护操作。终端的中断/强制终止分支针对进程 PID，不足以证明所有后代进程都已退出。

`camera-test.rc` 是 auxiliary 类，与 phocus 同类；system/vendor 的已检查 init 配置中尚未找到完整的全局 auxiliary 启动条件。未进行端口探测或 USB 维护握手，也未确认上传目标目录的挂载/执行限制。研究不通过启动未知服务或绕过访问检查来填补这些空缺。

## 两种已经内置的简单 UI

### 确认页：自定义文字、按钮、点击退出

`--confirmtest` 对应 `ConfirmTestMain::run`（GUI VA `0xad76c8`）。本轮核实参数字面量 `textmsg`、`button`，它们设置 QML 的 `textMessage`、`buttonText`。内嵌 `confirmtest_main.qml` 创建屏幕大小的 GUI 类窗口，显示文字与按钮，按钮 MouseArea 的释放事件调用 `Qt.quit()`。

这是真实的可交互页面模板，可以用于验证“USB 请求启动 → 相机显示指定文字 → 用户点击退出”。它本身不能承载多组设置控件或引闪后端。

原厂 `/bin/test_usb_device_enumeration.sh` 已调用这个页面显示测试提示，并管理自己创建的 confirmtest 实例；该脚本还会检查 testing state、做 USB 外设测试，不能整段运行来代替页面验证。另一个 `/bin/test_lcd_module_link.sh` 使用 `--confirmtest -b none`，表明原厂也提供不使用应用 DBus 的页面用法。`-b none` 不代表整个进程零副作用：Qt/显示连接、初始化、日志及窗口焦点仍存在。

### 图片页：显示传入 PNG/JPG，按键返回

`--imagetest` 的 QML 对 PNG/JPG 使用直接图片路径；其他输入交给原厂测试图片 provider。`Keys.onPressed` 根据传入的成功/失败按键值调用 `Qt.exit(0)` 或 `Qt.exit(1)`。原厂 EVF 光学测试脚本明确用过机内 PNG 路径，作为外部图片使用方式的佐证。

因此，先传一张自行生成的页面样图，再调用原厂图片页显示，是比上传完整 Qt 应用更小的候选步骤。但图片中的按钮不会自动变成可触摸控件；图片页已有的交互是按键返回。

两种页面都可使用公共超时选项：`appMain` 在 `0x333198..0x3331d0` 把秒数乘 1000 并建立 QTimer，超时回调 `0x333fc0..0x333fdc` 进入退出值 1 的路径。此超时依赖事件循环，不是进程卡死时仍可靠的硬件看门狗。页面点击/退出的代码已确认，触摸驱动到应用以及退出后焦点恢复尚未实测。

## 自定义程序与真正的设置页

`camera-gui` 是 AArch64 ELF，动态解释器为 `/system/bin/linker64`，依赖 Bionic 的 libc/libc++。普通使用 glibc 动态解释器的 Linux 可执行文件不能照搬；未来应匹配机内 ABI。纯静态程序是另一候选，不能仅凭 AArch64 架构相同就宣布兼容。

Qt Quick 代码已经链接在原厂 GUI 内；检查的 system:/lib64 只有 Qt Core、DBus、Network 等部分动态库，没有独立 Qt Gui/Qml/Quick 动态库。自定义 QML 文件不能借这些库直接运行，完整 Qt 页需要提供相应运行环境或另找明确的扩展机制。

不过，轻量独立页面已有更小的显示基础：系统提供 `libwayland-client.so`，导出 `wl_display_connect`、dispatch、wl_shell、wl_shm、wl_seat 等接口。`eagle_renderer_attach` 在 `0x948a8..0x949ec` 接受标准 `wl_shm` 缓冲，处理格式值 0/1 并取得尺寸；无需仅凭私有 EGL 入口推断显示可行。这支持继续研究不依赖完整 Qt 的普通 Wayland 页面，但本轮没有完整追通其绘制、触摸和退出恢复，也没有编译可装载程序。

## 下一阶段的最小验证顺序

1. 先实现并离线验证 USB 维护帧的严格编码/解析、目标命令白名单和状态机；保持既有六项只读工具独立。
2. 在另行明确的实机批次中，验证受限、无文件写入的程序运行回执，再验证现有 confirmtest 的指定文字、点击退出及超时退出。该阶段尚未获授权执行。
3. 再验证小型自制图片的 USB 接收、长度/哈希和显示。图片不是用户照片，不读取或下载相机照片。
4. 上述通路可重复后，才有条件验证独立程序与真正的设置控件；引闪后端仍独立推进。

## 可重复证据

[只读复核脚本](../../tools/inspect_usb_ui_4_2_0.py) 与 [本轮结果](../../outputs/4.2.0/usb-ui-checks.json) 固定输入哈希并复核关键指令、QRC 页面行为、ABI 和原厂调用脚本。结果中的通过只代表静态检查通过，没有 USB 传输或 UI 运行成功记录。

输入为官方 X2D 4.2.0 固件；上述复核脚本固定核心二进制哈希。本轮补充：

| 官方 system 分区输入 | SHA-256 |
|---|---|
| /lib64/libwayland-client.so | `fc9bd40a0c0abd0af78241145eff27c3d228c4509c919adb92f454a8fd13c6e4` |
| /bin/toybox | `999a0669ef654efbda54bc585c0f3c00643d1af61c985bfb7968cfd2f9aed840` |
| /bin/test_lcd_module_link.sh | `b8c4f7d750c4d9a663e4e1a74d3268b5419e06cf1ace92b613f428e69eeefff8` |
| /bin/test_usb_device_enumeration.sh | `a38f7c74b4595e51464b15b8ae165e0452562cb4ecfc426661f19fca590a64e2` |
| /bin/test_evf_optics_function.sh | `00d4b48ed0bd0222d695392672ae11149b0ce70d947726ef56b6577e4cde53df` |
