# 迁移与共享项索引

2026-09-12；对象为第一代 X2D 100C，固件分析基线 4.2.0。本任务核对了根目录源码、工具、测试、文档和构建配置的引用；没有读取或改动 `x1d/`。其他任务中保存的绝对路径无法穷尽，故保留全部旧文档路径作为跳转入口。

## 已迁入

根目录 `RESEARCH_HANDOFF.md` 与 `research/` 下七份 Markdown 正文已迁至 [research/history](research/history/RESEARCH_HANDOFF.md)。这些文件明确记录 X2D 前序研究和本项目客户端批次，属于本任务的前序资料。只添加归档提示并调整 Markdown 相对链接，未改写旧技术结论、批次结果或授权描述。

旧位置现为短索引。逐文件新旧位置、迁移前哈希与归档后哈希见 [organization-manifest.json](research/organization-manifest.json)。当前地区和机内无线结论另存于 [4.2.0 目录](research/4.2.0/REGION_AND_READBACK.md)，避免把历史“尚未找到”结论当作最新进度。

## 保留原位的共享项

“共享”指与既有根目录客户端或工具工作流共用，不表示已证明 X1D 使用这些文件。

| 保留位置 | 已核实的使用者与原因 |
|---|---|
| [research/firmware-manifest.json](../research/firmware-manifest.json)、[parameter-catalog.json](../research/parameter-catalog.json) | `app/evidence.ts` 直接导入，编译及发布产物也包含这些数据 |
| [research/firmware-observer-events.json](../research/firmware-observer-events.json) | `app/firmware-log.ts` 直接导入，是既有日志解析目录 |
| [research/binary-manifest.json](../research/binary-manifest.json) 及其他根目录研究 JSON | `tools/extract_system.py`、`catalog_parameters.py`、`trace_*.py` 等使用或生成，旧测试与正文继续引用 |
| [research/x2d-4.2.0-Camx_StartExpo.asm.txt](../research/x2d-4.2.0-Camx_StartExpo.asm.txt) 等四份 `.asm.txt` | `trace_eshutter.py`、`trace_debug.py` 固定在原路径生成；历史正文链接已调整为指向原件 |
| [research/validation](../research/validation) | 历史实机脱敏 JSON、离线 UI 及打包验证输出；`read-camera.cjs`、`read-firmware-logs.cjs`、`ui-smoke.cjs` 固定写这里。本轮不运行、不移动、不改写 |
| [tools](../tools) | `package.json`、根目录 `CodeTests` 与分析工具互相引用；`inspect_phocus.py` 的 ROOT 定义依赖原位置。包含硬件与构建入口，不能整体搬迁 |
| `.research-cache/` | 根目录分析工具和运行环境共同使用的固件、依赖与缓存；不复制大镜像，不输出其中的密钥或私密材料 |
| [app](../app)、[native](../native)、[CodeTests](../CodeTests) 及根目录构建配置 | 既有客户端实现和验证。本次只整理研究资料，未改变代码及入口 |
| `dist/`、`release/` | 既有客户端构建与发布输出；`tools/package.cjs` 依赖当前布局。未重打包 |
| [README.md](../README.md)、[AGENTS.md](../AGENTS.md) | 项目公共入口与权限规则；旧文档链接经兼容索引仍可访问 |

后续 X2D 独立研究新增输出进入 `x2d/outputs/<固件版本>/`。若以后要迁移整个客户端及上述共享资产，应在独立的客户端迁移任务中统一调整导入、路径与构建并验证；本次不扩大到这项工程。
