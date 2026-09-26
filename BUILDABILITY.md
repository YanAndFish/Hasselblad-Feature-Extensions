# 首批构建与离线验证

所有测试均不连接相机。工具链、Qt 和字体不随源码附带；使用者需遵守所安装依赖的许可。

## 声音路由策略

已用 Zig 0.13.0 在 Windows 编译运行九个替身场景。无需 Qt 或相机输入：

```powershell
New-Item -ItemType Directory -Force build/audio-route | Out-Null
zig c++ -std=c++11 -O0 x1d/shutter-effects/CodeTests/audio_route_test.cpp -o build/audio-route/audio-route-test.exe
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
& ./build/audio-route/audio-route-test.exe
if ($LASTEXITCODE -ne 0) { throw 'Test failed' }
```

测试覆盖获取、释放、失败恢复和原厂优先责任交还的状态逻辑，不证明真实扬声器出声。测试编译出现工具链导出声明警告，但编译和执行成功。

## 文本资源工具

Python 3.11 或以上，标准库即可：

```powershell
python -B x1d/offline-resources/CodeTests/test_resources.py
```

四项自造数据测试通过：往返、无效头、截断输入、循环目录拒绝。无需固件、Qt 或设备。

## 引闪界面

Python 3.11、PySide6 6.4.1。依赖由用户自行安装；不复用作者电脑路径：

```powershell
python -B x2d/flash-ui/CodeTests/smoke.py
```

五个页面状态与全部非空图标加载通过，Qt 使用 offscreen 和 software 后端。某些无界面平台不自动发现字体，可用 `--font` 指定本机已安装字体；该选项只读取本地字体，不复制或分发它。可选 `--screenshot build/flash-ui.png` 保存预览。

浏览器直接打开 `x1d/shutter-effects/index.html` 可以预览纯动画，未附带声音。

这些结果不代表真实设备集成、Qt 5.5 机内运行或完整更新包构建已通过。
