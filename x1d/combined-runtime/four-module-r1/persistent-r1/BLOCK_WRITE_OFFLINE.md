# 整批写入离线候选

未安装，用户要求仅离线修改并统计。相机仍为主装载 64.8 秒的 resident-init 版本。

变更：接收器先验证整批地址，然后写完一批，最后本地逐字检查并一次返回；任何失败封闭当前会话，不自动重试。固定内存分配程序 976 字节改成 5 个批量包上传，仍在原厂任务上下文执行。写入范围仅在主机指定分配阶段开放，不跨越固定保留区。缓存与入口启用顺序保持。

完整模型 2474 次，相比 2912 次减少 438 次。接收器增加 72 字节，准备通信从 1551 增至 1587；分配及等待从 658 降至 184；其他阶段相同。接收器自身仍是逐字装入，微型引导候选未接通，不能声称全面消除逐字上传或达到 100 次。

验证：7141 项生命周期模型检查、241 项整批授权/写入失败/读回失败/不匹配及拒绝重试检查、24 项真实 ARM 消息链路用例通过。Linux ARM 动态库构建通过。没有新版实机耗时。

证据：build/block-write/lifecycle-validation.json、transport-arm-validation.json、staged-build.json、runtime-build.json、phase-profile.txt。源码在 native/boot_block_staged_adapter.c、build/block-write/block_loader.cpp、build/block-write/boot_batch_wire.h。后续安装还需完成正式安装期固件绑定与完整包验证；不得直接使用旧安装脚本。
