# 构建输入与当前闭环

目标是保留完整功能，让使用者从公开源码自行构建。原厂输入不随仓库分发，资源能在机内引用时使用宿主资源；需要参与离线编译的输入由使用者合法自行准备。下列成功项和阻断项分开列出，不用“核心测试通过”替代整包构建。

| 入口 | 显式输入 | 产物与已验证范围 |
| --- | --- | --- |
| `scripts/build_core.py` | C++11 编译器或 Zig；可选本地无线表目录 | 默认 5 个真实核心主机测试程序，提供无线表后为 6 个；无硬件访问 |
| `scripts/generate_radio_tables.py` | 固定版本的 prepared 无线输入 | 1345 项校验表及采样表，仅在使用者输出目录生成 |
| `scripts/build_x1d_worker.py` | Zig 0.13.0、Qt 5.5.1 源码头、X1D 1.25.0 目标运行库、本地无线表 | ARM32 无线 worker 共享库；已编译链接，尚未接入完整启动与界面组合 |
| `x1d/tools/generate_display_tables.py` | 支持的矩阵 RGB ICC、输出路径 | 三组显示表；自造输入测试通过，本地实际输入生成数组与旧实现一致 |
| 根目录 `npm test` 与 `npm run build:native` | 锁文件中的 Node 依赖；Windows x64 .NET 编译器 | 诊断客户端 TypeScript、29 项替身测试及 WinUSB 辅助程序编译；未运行设备接口 |

## 主机核心

```powershell
python -B scripts/build_core.py --compiler zig --driver zig --build-dir ../hfe-build/core
```

该命令覆盖实际持久化版本的引闪策略、半按更新、持久设置编码、设置恢复及声音路由。半按功能直接存在于源码中，不依赖旧构建目录里的字符串变换结果。

## 无线表及适配层

```powershell
python -B scripts/generate_radio_tables.py --prepared-image <本机输入文件> --output ../hfe-build/radio-tables
python -B scripts/build_core.py --compiler zig --driver zig --build-dir ../hfe-build/core --radio-tables ../hfe-build/radio-tables
python -B scripts/build_x1d_worker.py --zig <zig可执行文件> --qtbase <Qt5.5.1源码目录> --target-root <X1D1.25.0运行库根目录> --radio-tables ../hfe-build/radio-tables --build-dir ../hfe-build/worker
```

prepared 输入不是未经处理的原厂固件。历史流程由 `x1d/wireless-flash/firmware/prepared_flash.py` 引用三段 `probe10` 中间块后生成它。目前没有在已恢复源码中找到这三段块的完整生成源码，因此**从纯原厂输入重建无线固件这一段尚未闭环**。不能要求使用者任意寻找同名文件，也不能用修改哈希绕过此缺口。

表生成器只接受已绑定的输入摘要，消费入口同时检查输入身份、生成表的固定版本摘要和本次完成状态。复用输出目录失败时，报告会先标记为未通过；即使目录还有旧产物，也不能当成本次构建成功。生成表、目标运行库和输出二进制不属于可直接再分发的公开资源，不能据此自动加入仓库。worker 导出 API 还要由观察器及启动模块调用，本构建入口不会连接相机或创建安装包。

## 回放显示

```powershell
python -B x1d/tools/generate_display_tables.py --icc <本机合法ICC文件> --output ../hfe-build/display/display_tables.h
```

编译 `display_pixels.c` 时把 `../hfe-build/display` 加入头文件搜索路径。生成器保留原有三组数组接口，只接受已经验证的矩阵及统一 gamma 形式；其他 ICC 明确拒绝。不会从机内提取配置，也不改变照片文件。

## 尚未闭环的完整更新

1. 重建或找回无线早期中间块的生成源码，并验证与运行实现的契约。
2. 把启动装载和组合界面的旧 `build/*.json` 编译参数依赖改为显式配置。
3. 梳理 AF 配置模型和机内图标引用，保留功能，同时分离不应分发的资源。
4. 在全新源码副本中执行目标构建、资源组合、打包和离线恢复检查，记录所有输入身份。

当前没有通过以上整包验收，也没有修改设备或上传这批恢复内容。历史装机记录不等于公开构建验收。

## 构建入口自身的故障检查

```powershell
python -B scripts/CodeTests/test_build_contract.py
```

五项检查使用临时目录和自造输入，不需要相机文件或编译器。检查旧成功报告失效、错误输入身份以及文件和自报摘要同时修改时的拒绝行为。
