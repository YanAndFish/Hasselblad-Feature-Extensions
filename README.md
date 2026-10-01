# Hasselblad Feature Extensions

独立、非官方的相机功能扩展源码项目。当前工作版本为**阶段性源码成果**：保留对焦、引闪、回放、动画、声音、通信与持久化相关实现，并提供经过验证的组件构建入口。**目前不能仅凭本仓库生成完整可安装的相机更新包。**

本阶段说明见 [STAGE_DELIVERY.md](STAGE_DELIVERY.md)。本阶段扩展此前仅含离线组件的 35 文件首版，恢复功能研究源码及组件构建入口。

## 从这里开始

只运行不需要相机输入的核心测试，需要 Python 3.11+ 和 C++11 编译器；以下以已验证的 Zig 0.13.0 为例：

```powershell
python -B scripts/CodeTests/test_build_contract.py
python -B scripts/build_core.py --compiler zig --driver zig --build-dir ../hfe-build/core
```

默认构建 5 个真实核心测试程序；提供受支持的本地无线表后增加第 6 个适配层测试。上述入口不连接相机。目标库的交叉编译需要额外输入，见 [构建输入与缺口](BUILD_INPUTS.md)，不要把其他历史安装脚本当成默认构建步骤。

## 内容索引

| 内容 | 入口 | 当前边界 |
| --- | --- | --- |
| X1D 对焦、回放、引闪与组合实现 | [X1D](x1d/README.md) | 包含历史候选；当前已复验组件见阶段说明 |
| X2D 研究、菜单与功能实验 | [X2D](x2d/README.md) | 固件版本绑定的历史研究；尚未统一完成本次目标构建 |
| X2D II | [X2D II](x2d2/README.md) | 研究与工具，不代表已完成机型适配 |
| 动画与声音策略 | [动画](x1d/shutter-effects/README.md) | 不附带音频；声音策略已做替身测试 |
| 离线引闪界面 | [界面](x2d/flash-ui/README.md) | 自绘图标及系统字体；机内集成另行验证 |
| 诊断客户端 | [客户端测试](CodeTests/README.md) | 根目录 Node 工程；离线测试与 Windows 辅助程序编译通过 |

X1D II 尚待收到实现，没有用其他机型代码替代。目录中的历史“已安装”“已验证”仅对应其记录的原环境，不能视为本公开项目的重新验收。

## 构建与来源

- [阶段交付与验证结果](STAGE_DELIVERY.md)
- [构建方法](BUILDABILITY.md)与[完整输入清单](BUILD_INPUTS.md)
- [公开范围](PUBLICATION_SCOPE.md)与[当前状态](PUBLICATION_STATUS.md)
- [来源审核规则](SOURCE_REVIEW.md)、[目录规范](DIRECTORY_LAYOUT.md)及[贡献说明](CONTRIBUTING.md)

保留功能源码，对资源依赖采用原创替代、使用者本地生成或机内引用。本项目不附带厂商程序、固件、图标、字体、音频或目标运行库；不支持的输入会明确拒绝。缺少输入和历史路径依赖都不算构建通过。

原创代码、文档和自绘图标采用 [MIT 许可证](LICENSE)。外部依赖适用各自许可，MIT 不授予第三方素材或商标权利。本项目不代表厂商，也不意味着厂商认可；技术检查不能保证法律风险为零。

## 本次研究源码更新

见 [PUBLIC_UPDATES.md](PUBLIC_UPDATES.md)。新增范围为自写离线算法与通用组件；厂商固件内部材料不纳入本轮更新，十六份旧分析工作文件已改为撤下说明。本次提交和推送已获授权；测试结果不能代替整个仓库的来源审查。
