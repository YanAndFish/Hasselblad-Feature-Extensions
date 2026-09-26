# AF r3 首次实机装载通过

2026-09-13（北京时间），主任务使用原样冻结的 r3 入口完成一次真实相机装载。AF 模块任务随后只读复核主机记录、RAM 事务事件链、逐笔传输链和来源 SHA；复核没有发送设备请求。

本次结论为：**AF r3 首次实机装载通过，hold 已释放。** 对焦效果尚待用户实测；旧 USB 故障根因仍未确定。当前运行状态是主任务完成时的报告，不是本文件持续监测的状态。

## 用例和依赖

目标是从原厂 Linux/AF 基线串行安装冻结 AF-only Linux 包及 AF RAM 候选，完成原字、版本、回调、缓存、分配和安装后逐字校验，再释放本次 hold。组件为实际相机、冻结 WinUSB 主机入口、机内 AF UI/bus-r2、固定健康检查器和动态重定位的 AF 候选。固件来源、工具依赖和前置条件沿用交付根目录 [README](../../README.md)；本次实际输入的 SHA 见 [result.json](result.json)。

执行者为主任务 `01a08561-a63d-7203-86af-1433a00787d6`。执行顺序为 `stage` → `install-staged`，内部完成 Linux preflight、UI/hold、bus、完整 FARM 预检、持久日志、缓存探针、原厂分配、候选构建与安装、日志复核、hold 释放。首笔 FARM 回复最多 20 秒、普通请求 2 秒及原段预算保持冻结配置；本记录不把预算当作物理计时精度。

## 已核对结果

| 项目 | 实际记录 |
|---|---:|
| 完整 FARM 预检 | 7905 请求、0 RAM 写入 |
| AF 事务合计 | 23753 请求、5075 RAM 写入 |
| hold 查询 | 67 次，全部匹配并关闭句柄 |
| Linux 传包 / 安装阶段 | 620 / 27 请求 |
| RAM 持久事件链 | 31799 事件，完整，无未完成操作或缓存动作 |
| 逐笔传输链 | 47507 事件，完整；23753 个结果全部成功且句柄关闭 |
| 最终状态 | `completed=true`、`afInstalled=true`、`holdReleased=true` |
| AF 阶段 | `installed_settings_until_restart` |
| 自动拍摄 / 对焦 / 试闪 | 0 / 0 / 0 |

本次没有安装 resident UI、回放或闪光模块。AF 专用机内 UI 和 bus 是本次 AF 包的组成部分。

候选在实际分配地址 `0x003577c0` 重定位，17344 字节，SHA-256 为 `23d3bc18b47d873e70de13242b4c69e81aa3f65d9aa66c25b97fcda3b2ca7556`。它与离线测试地址不同，重定位后的哈希也不同。

Linux 包仍为 `f325db70de366f52ae3b58b98f8e9fd3e496f353dbab64c6ca4712a49064cc6a`；冻结验证文件仍为 `cf2eb05b6b1927e8c95e2efa49cd54dcd9038355475211f1aed13b0ecc001cfd`。本次只读检查确认完整冻结来源链仍有效。

## 证据与保留状态

- [传包记录](../../build/sessions/af-only-stage-20260912T165611644147Z/stage.json)
- [安装完成记录](../../build/sessions/af-only-install-20260912T165707900998Z/installation.json)
- [RAM 日志入口](../../recovery/af-only-first-install-20260912T165909435658Z.json)，事件链末 SHA 为 `21b8d5360599f75e6234140b9e8503a65069d854f9aeacbfca9ce25aa76f496d`
- [逐笔传输链](../../build/sessions/af-only-install-20260912T165707900998Z/af-trace.jsonl)，链末 SHA 为 `e9a59b32fb4728d7212ac8426c2d9ce9fe9119dc752b705a453ea1b955ed3252`
- [结构化结果与逐文件 SHA](result.json)

按本次目标保留 AF 安装，未执行回滚、释放堆块、删除临时目录或重启；设备继续由主任务独占操作。实机回滚、设置交互和对焦效果不在本次通过范围内，新预测动作与两个提前补偿的执行连接状态也没有因此改变。

此文档是独立的实机结果补充。冻结 `validation.json` 和默认 `report` 中的 `physicalR3Verified=false` 保留发布时的离线状态，不能据此覆盖本次通过记录；后续状态说明应同时引用本结果，不能改写冻结执行源或包。
