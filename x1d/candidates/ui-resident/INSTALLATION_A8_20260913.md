# 原厂 GUI 独立 UI 包实际安装记录

2026-09-13（北京时间），主任务完成原厂 GUI 专用 `a8` 包的暂存、前置检查、安装及状态检查。本 UI 任务只读取既有本地回执并登记，没有新增设备请求。

包 SHA-256：`a8a78411c639f4182d87e79279886273f499d8ab5ebca7cfbf02a394b50ae177`，41,432 字节。它只提供主菜单与通用设置容器常驻及再次进入刷新，不含 AF 配置页、回放或引闪。固定包、程序与既有验证报告均未修改。

## 实际阶段回执

以下目录名使用 UTC 时间。四份结果均为 `completed=true`、`allHandlesClosed=true`、`failed=false`，且包摘要一致。

| 阶段 | 设备请求数 | 结果与证据 |
| --- | ---: | --- |
| stage | 334 | `staged=true`；[result.json](build/session/sessions/stage-20260912T203350382117Z/result.json) |
| preflight | 6 | `0 / ui-resident-preflight-ready`；[result.json](build/session/sessions/preflight-20260912T203418468006Z/result.json) |
| ui | 12 | `0 / ui-resident-session-ready`；[result.json](build/session/sessions/ui-20260912T203432186508Z/result.json) |
| status | 2 | `ui-resident-session-ready`；[result.json](build/session/sessions/status-20260912T203450568892Z/result.json) |

合计 354 次，由主任务执行。四份结果的 `farmRequests=0`、`busRestarts=0`；主任务报告设备操作已结束，没有在途请求。原分段回执保留在上述各目录，本记录不复制其中设备数据。

| 回执 | SHA-256 |
| --- | --- |
| stage | `0fb00e43c37e248fb59b8f08a1f3b628c4045eedf918378329d7fd7fe3fdeb93` |
| preflight | `ceb7be3161ab4c303d386f36e48b7d63d8a165fa84ffe03ff887ee6ad600a213` |
| ui | `939aa822ffd826b5b26a7d5d0ed85072588162ec1783be30b4cf38560dcb021e` |
| status | `aba3592164a4ad13e587b42b9b7d73b7a0fdb822171d83aeae9c40fe45d8e1a3` |

## 已确认与待确认

原冻结脚本成功返回就绪，表明其目标检查链通过：原厂服务前置条件、正常根对象、四个实际资源摘要、四组件 Ready、当前 GUI PID 就绪标记、本库加载、稳定健康快照及 bus PID 未变。主任务另明确报告四资源、四组件和健康检查已通过。因此本次目标装载已成功，先前“尚未执行目标装载”的状态已由本记录更新。

实际菜单操作、反复进入后的体验、流畅度和性能仍待用户试用确认。安装就绪不等于完整功能与性能验收；本记录也不包含 AF 或回放功能通过的结论。

冻结包内 `targetValidated=false` 与旧离线报告保留构建时事实；本文件及实际回执记录后续安装结果，不回写旧证据。包与恢复入口见 [独立会话交接](SESSION_HANDOFF.md)。本次未使用 `83b` AF 共存包。

## 第二次同包安装与用户反馈

主任务按用户明确要求，在用户报告正常重启完成且未先操作菜单/回放后，再次安装相同原厂专用 `a8`，用于观察第一次进入的响应。四份本地回执再次核对通过：

- [stage](build/session/sessions/stage-20260912T204910812957Z/result.json)：334 次请求，暂存成功。
- [preflight](build/session/sessions/preflight-20260912T204940074264Z/result.json)：6 次请求，`0 / ui-resident-preflight-ready`。
- [ui](build/session/sessions/ui-20260912T204948363474Z/result.json)：12 次请求，`0 / ui-resident-session-ready`。
- [status](build/session/sessions/status-20260912T205005798768Z/result.json)：2 次请求，`ui-resident-session-ready`。

均为 `completed=true`、`allHandlesClosed=true`、`failed=false`，FARM 请求及 bus 重启为 0，合计 354 次。主任务报告没有预先进入菜单、回放或格式化页。这仍是原 `a8`，没有装入后续 `text2` 修复，不能把两次安装记成修复成功。

用户随后主观反馈整体明显变快，并感觉手动回放和拍照后自动回放也更快；未做计时或因果验证。本轮没有安装回放包，也不能据此宣称全部卡顿已解决。

用户另发现格式化按钮亮一下但确认页未出现，目前只明确报告这一处异常。已结合现场日志与离线原厂/旧包对照定位 `text2` 角色回归；[最小修复另版交付](FORMAT_FIX_HANDOFF.md)，尚未安装。其他页面未被用户报告异常不等于全面验收。后续重启或其他模块装载的当前状态由主任务掌握，本记录仅描述两次历史安装。
