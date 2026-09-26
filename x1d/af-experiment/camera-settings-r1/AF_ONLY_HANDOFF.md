# 仅 AF 的独立首次安装与回滚

用户最新范围是只装 AF，且已经重启。本交付使用独立入口，不安装 HFS1、引闪、回放或其他常驻页面。历史组合入口和报告保持原样；本次不得使用 `settings_loader.py first-install`。

## 固定入口

从项目根目录运行：

```powershell
python -X utf8 -B x1d/af-experiment/camera-settings-r1/af_only_loader.py report
python -X utf8 -B x1d/af-experiment/camera-settings-r1/af_only_loader.py first-install
python -X utf8 -B x1d/af-experiment/camera-settings-r1/af_only_loader.py rollback --journal <本轮完整安装日志>
```

只有 `report` 是离线入口。后两个命令由主任务在新开机的独占 AF 窗口中运行，本任务不执行。恢复日志独立存于 `af-only-recovery/af-only-<动作>-<UTC时间>.json`，不复用组合日志。回滚只接受本轮完整 `factory-af-only-first-install` 事件链，不能接受组合版、历史观察版、部分安装、未关闭句柄或未完成缓存操作。

## 合同与保护范围

- `af_only_install.py` 复用已冻结 AF 的 14 个入口、32 KiB 原厂申请、缓存可见、Thumb 执行回执和严格报文/阶段白名单。首次预检要求原厂 AF 入口与零 bootstrap。
- HFS1 的驻留校验被替换为 8 个引闪相关入口所在原厂代码行与 `[0x2b2880, 0x2b3400)` 零区域检查，共 800 个只读字。不会为了满足前置条件而安装 HFS1。相应地址不在写入白名单内，`packet` 另行拒绝对此范围的所有写入。
- 安装和回滚前后均核对原厂保护区；AF 空闲检查仍保留，并核对原厂引闪入口。没有 HFS1 动态状态或计数读取，也不伪造其记录。
- `af_only_rollback.py` 恢复全部 14 个原厂入口、零 bootstrap 和临时回调。保留 AF 堆块，不重新 malloc、不 free、不覆写 AF 代码。任何失败都停止，不自动重试、回退或重启；部分失败必须按日志阶段独立审阅。
- 实际事务使用新随机 nonce，合同绑定其精确写入白名单，因此运行日志中的合同 hash 随 nonce 变化。验证报告的 `firstInstallContractSha256` 是 `exampleNonce=1` 的离线示例，不能拿它替代本轮实际合同。

## 健康窗口与 Linux 组成

继续使用固定 `/tmp/hbl-x1d-combined/system-check --require-held-min-ms 180000`，checker SHA-256 为 `e373262db5b23f567b22060f1a61687c723cbbbae3c1e237e60728015d3ccca0`。固定输出、20 分钟截止、最低剩余 180000 ms、每段 120000 ms 均不放宽。路径名字不表示装载组合功能。

主任务仅加载 `libhbl-af-ui.so`、`libhbl-af-bus.so` 和 AF 页面；负责本轮 GUI 健康保持和原厂导航。没有 formal worker。目标 Qt/IPC 仍须现场验收，FARM 装载期间 AF 页面不查询。两个库、QML、FARM 载荷与参数语义均沿用最新冻结结果，见 `INSTALL_HANDOFF.md` 的 ARM stat ABI 修复后哈希。

## 离线证据与源绑定

`CodeTests/test_af_only.py` 的 7 项测试通过：完整首次安装/回滚，原厂入口与空白区不符时零写入拒绝，禁止引闪写入，分配异常拒绝，组合或不完整日志拒绝，以及安装/回滚多个阶段写入前后不确定失败。原厂 ARM 分配器真实执行，USB、缓存和调度为模型。首次模型为 23752 请求、5075 写入、67 次 hold；不是实机时间承诺。

`CodeTests/validate_af_only.py` 生成独立 `build/af-only-validation.json`，逐文件绑定原冻结交付、原厂模型来源、新入口/合同/回滚/测试代码与报告。`af_only_loader.py report` 检查全部绑定；文件变化会阻止建立 USB 事务。原组合验证报告不被覆盖。

三个速度默认跟随原厂，手动档为五/四/五档；远端优先、默认关闭的抗噪判向、原厂精扫流程不变。两个绝对提前量仍仅保存、回读与下轮锁定，实际提前减速/停止未接通，能力位为 0。机内执行、真实对焦效果与毫秒时序没有被标为已验证。
