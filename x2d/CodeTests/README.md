# X2D 4.2.0 离线回读模型

`region_reply_model.py` 保存此前已在纯内存中执行的地区回复模拟。输入全部为人工响应，不读取设备、固件、照片或外部数据；无网络、USB、串口、ADB、进程调用和文件输出功能。脚本只向 stdout 输出计数与验证范围。

在项目根目录运行：

```powershell
py -3.11 -B x2d/CodeTests/region_reply_model.py
```

对应固定官方 X2D 100C 4.2.0 的静态结构，证据见 [地区报告](../research/4.2.0/REGION_AND_READBACK.md)。已保存的本轮结果为 [offline-region-reply.json](../outputs/4.2.0/offline-region-reply.json)。

覆盖 14 个内层场景、8 个外层场景、160 组 CRC 交叉、已知向量、1888 个正文单比特损坏和 96 个头字段不匹配。外层采用该固定版本 260 字节完整帧模型；没有验证真实传输的分包、会话、超时、跨启动持久性或同头旧回复的新鲜度。这是离线研究验证，不是已实现的维护客户端。
