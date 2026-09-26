# USB_READ 离线诊断结论

现有资料不足以确定本次唯一根因。此前正常计数模型映射第 3234 次请求为 `0x0019da54`，紧接一次 Linux hold；该地址属于固定 FARM 原厂代码，预期字 `0xe3a03000`。轮询次数在实机可能变化，不能把模型映射直接当作已记录的实机最后地址。

旧成功安装的完整事件链已核验：26977 事件、20620 请求、4429 写、60 次 hold，预检期间 28 次 hold 均匹配，包含 `preflight_3072`。资料位于上级 `installed-baseline/audited-installation.json` 及其冻结来源。因此“以前完全没有切换 Linux/FARM 路由”不成立。

旧成功版与本次失败前的 `read_usb_link_once.py`、`native_loader.py`、`native_hold.py` 源码 SHA 相同；原本就是 FARM 回复 2 秒、Linux hold 回复 20 秒，未发现新版缩短了这个预算。两条路径使用同一 FX3 控制接口，但 FARM 请求走 SUC/FARM，Linux 健康命令还经过 iMX/Linux；Linux 查询成功不能证明下一笔 FARM 往返必然成功。

本次 `x1d/combined-runtime/build/sessions/af-only-install-20260912T161705518507Z/installation.json` 仅保留 `USB_READ`、3234 请求、0 写入和句柄关闭，没有记录 Win32、最后地址或请求耗时。这些字段无法事后补回。更早的纯 Linux 传包日志 `stage-20260912T151440213213Z/0066.json` 中，`chunk-4223` 也记录过 `USB_READ` / Win32 121；它不是本次 AF 错误原因的证明。

r3 的改进针对两项可离线证明的不足：预检缺少逐笔证据；健康查询后的首笔 FARM 回复只有 2 秒等待预算。离线模型已经验证 3 秒首笔回复仅接收一次、错误回复和超时立即停下，以及失败能记录实际请求地址。仍需要主任务在新的、独占的正常安装窗口中验收实际效果。

没有修改原字校验、AF 合同、相机机器码或原冻结来源。本任务没有建立设备会话。
