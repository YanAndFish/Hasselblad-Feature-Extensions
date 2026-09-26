# 第一代 X2D 100C 研究索引

**公开候选说明：本页包含历史研究记录，不能视为本独立目录已经复现。原厂输入、工具链与部分界面资源未随源码提供；当前范围见 [构建核对](../BUILDABILITY.md)。**

更新：2026-09-12。X2D 专属资料统一放在本目录，分析基线为**官方 X2D 100C 4.2.0**。相机曾在 2026-09-09 报告版本号 4.2.0；这不等于实机二进制已逐字节比对。当前地区与机内无线研究仅离线进行。

## 当前资料

- [Ciallo 动画与声音：400 ms 历史基线、800 ms 本地候选及迁移核对](CodeTests/shutter-animation-preview/MIGRATION.md)

- [经 USB 传程序与使用机内 UI](research/4.2.0/USB_PROGRAM_AND_UI.md)
- [地区配置、维护通路与回读](research/4.2.0/REGION_AND_READBACK.md)
- [机内无线 Godox 普通引闪研究](research/4.2.0/ONBOARD_RADIO.md)
- [本轮二进制来源与哈希](research/4.2.0/sources.json)
- [离线回读模型及验证方法](CodeTests/README.md)
- 离线模拟输出未随本候选提供；历史路径为 `outputs/4.2.0/offline-region-reply.json`，不作为本次验证证据。
- [共享项及迁移范围](SHARED_ITEMS.md)
- [逐文件迁移记录与原文哈希](research/organization-manifest.json)

## 分类约定

| 路径 | 用途 |
|---|---|
| `research/<固件版本>/` | 研究结论、来源清单、版本绑定的地址与证据 |
| `research/history/` | 已迁入的前序文档；保留原批次、原结论和更正记录 |
| `tools/` | 后续 X2D 专属离线分析脚本及使用说明 |
| `CodeTests/` | 离线解析、白名单、模拟响应等代码验证 |
| `outputs/<固件版本>/` | 本目录研究产生的验证结果；每份标明离线或实机来源 |

今后若确需功能或项目场景测试，再按项目规则建立 `FunctionalTests/`、`ProjectScenarioTests/`，不预建空目录。既有客户端所需的根目录工具、数据与发布目录保留原路径，详见共享项说明；不复制一套易漂移的数据。

## 历史正文

以下八份正文已迁入本目录；旧路径保留短索引，供现有 README、客户端打包说明和其他任务继续访问。

- [研究交接](research/history/RESEARCH_HANDOFF.md)
- [HTTP 协议与实现边界](research/history/PROTOCOL_EVIDENCE.md)
- [USB 读取协议](research/history/USB_READ_PROTOCOL.md)
- [USB 端点更正](research/history/USB_ENDPOINT_CORRECTION.md)
- [USB 历史实机验证](research/history/USB_READ_VALIDATION.md)
- [六项调试读取批次](research/history/DEBUG_READ_BATCH.md)
- [电子快门同步分支](research/history/ESHUTTER_BRANCH_ANALYSIS.md)
- [内部详情通道](research/history/FIRMWARE_DEBUG_CHANNEL.md)

本轮目录整理没有设备访问、配置写入、射频装载或 Git 操作。地区修改仍需回读；正常完整重启后生效可以接受，但不代表已经授权现在重启或写入。无线播放与曝光同步尚未实现、联调或测量。
