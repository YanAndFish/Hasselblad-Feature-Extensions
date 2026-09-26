# 普通页常驻离线原型：初始化回写与特殊页边界

本轮完成一个可运行的离线原型，范围仍为本目录。没有修改冻结 a8、格式化修复包或其他模块，没有生成装载包，没有访问相机。原 [20 次内存评估](REPORT.md) 的全部输入摘要已再次核对，结果保持不变；新增原型的内存尚未重新测量。

## 两个滑块的原型结果

原厂 `SettingSlider.value` 同时承担后台显示值和用户输入值，父页面的 `onValueChanged` 会在构造或后台更新时触发属性赋值。仅在 Component.onCompleted 后打开开关，还不能区分后台刷新与用户编辑。

原型在评估副本加入 `userEdited(editedValue)` 信号：键盘与拖动结束通过专门函数发送用户输入；父页只响应这个信号写入代理。`value: proxy[name]` 保留为显示绑定。隐藏、禁用以及值未改变时，输入提交函数不发送信号。现有键盘步进和拖动取值计算保持原样。

真实的 23 个普通页与 99 个功能行全部创建、行 Loader 全 Ready 后，两处滑块的初始化赋值从各 1 次变为 0。Qt 5.15.2 Windows 宿主测试分别覆盖 `BACKLIGHT_brightness`、`crop_mode_opacity`：

| 验证行为 | 结果 |
|---|---|
| 隐藏页接收后台属性更新 | 显示绑定更新，无回写 |
| 真实键盘左右键 | 进入原键盘处理分支，单次代理赋值 |
| 真实鼠标按下、移动、释放 | 进入原拖动路径，结束时单次代理赋值 |
| 键盘/拖动之后再收到后台更新 | 显示绑定仍有效 |
| 隐藏、禁用或相同值调用提交函数 | 无代理赋值 |
| 完整普通页预建 | 99 行 Ready，两滑块回写 0，QML 警告 0 |

代理为本地内存替身，数值类型与取值范围是测试条件，不是实机参数类型测量。此原型只验证交互路径和绑定，不证明目标固件数值语义、Qt 5.5 兼容性或触摸设备行为；鼠标拖动通过也不等于实机触摸验收。

可审阅 [两个 QML 的差分](build/guard-prototype/changes.patch)、[运行脚本](guard_prototype.py) 和 [执行证据](build/guard-prototype/report.json)。复现：

```powershell
python x1d/candidates/ui-resident/evaluation/full-pages/guard_prototype.py
```

脚本使用上一轮已准备的评估输入，在 `build/guard-prototype` 下复制并修改自己的副本，执行完核对原测量输入未改变。

## 三个特殊页不能直接套用普通页常驻

以下均为固定 X1D 1.25.0 GUI 的静态调用证据，没有调用真实原生服务，也没有实例化特殊页来估算其内存。

| 页面 | 已核对的初始化/隐藏行为 | 对预建策略的影响 |
|---|---|---|
| 日期时间 | `DateTime.qml` 的 Component.onCompleted 调用 populateModel，后者首先调用 `SystemTimeControl.loadSystemDateTime()`，再建月/小时/分钟模型并申请焦点 | 不可把构造视为纯分配；长期保留还需要在用户进入时刷新时间 |
| 水平仪 | `SpiritLevelView` 完成构造调用 setSpiritLevel；子组件在 visible 变化、running 变化、系统状态变化时调用 `SpiritLevel.enabled(visible)`；另有 Binding 写入 `usingUserLevel` | 隐藏构造仍可能向共享水平仪服务发送 false 或改绑定，不能以不可见证明无副作用 |
| 白平衡工具 | 完成构造设置 `SortedContentModel.showOnlyImages(true)`，在条件满足时切到活动图片目录；销毁时设置筛选 false | 保留实例会改变原本依赖销毁恢复的生命周期，涉及与回放共享的图片模型；不得直接预建 |

证据文件：[DateTime](build/qml/factory/settings/DateTime.qml)、[SpiritLevelView](build/qml/factory/settings/SpiritLevelView.qml)、[SpiritLevel](build/qml/factory/liveview/SpiritLevel.qml)、[GreyBalanceTool](build/qml/factory/components/GreyBalanceTool.qml)。其来源和摘要见原 [输入汇总](build/summary.json)。

据此，下一版普通菜单常驻方案应先将这三个工具继续留在按需创建路径。若以后扩展特殊页，需要把纯界面构造、实际进入时服务激活、退出时共享状态恢复分开验证，并尊重其他页面的服务使用权；不能统一在隐藏时强行关闭共享服务。

本轮没有填入特殊页内存数字：用空图片列表或删掉服务后的壳测量，无法代表真实白平衡工作集；当前 16.60 MiB 差分仍只覆盖原报告的普通菜单范围。

## 当前可交付程度

初始化回写已有离线可审阅修正原型，键盘/鼠标与绑定回归通过；特殊页有明确的生命周期分界。完整多页导航路由、能力变化后的行增删、进入 About 时刷新、目标 Qt 5.5、实机峰值及长期稳定性仍未验收。本原型不是可直接装机的候选包。
