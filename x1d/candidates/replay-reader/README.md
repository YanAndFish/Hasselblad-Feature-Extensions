# JPEG 回放读取端候选

本目录是独立修订，原 `replay-stable/releases/stable-r1` 保持冻结。目标是保留原厂拍摄和写卡流程，仅在回放时优先读取对应 JPEG。状态为离线候选，未在相机装载或验证。

## 实现范围

- 仅为 victory-gui 加载 provider、会话守护库及 QML 资源。configstore、jpeg-daemon、storage-daemon 保持原厂程序；不增加生产钩子。
- 不强制改变拍摄格式或 JPEG 尺寸，不额外编码、嵌入预览、写照片或读写完成记录。原厂设置不生成 JPEG 时，本包不会替它生成。
- 新增 File 读取入口只接受 `.jpg`，按原 ContentModel 缓存解析同目录同名配对。有效 JPEG 使用 TurboJPEG DCT 缩放浏览；Full 保留该 JPEG 的原尺寸。
- 已确认缺少 JPEG 时允许一次原厂 RAW 回退；有效 JPEG、存储未知错误、空文件、配对歧义和不支持的 JPEG 不会触发额外 RAW 读取。原模型缓存不足时仍可能无法回退，需要实机核对 RAW-only 用例。
- 无 pending 依赖。可见且状态为 Error 的当前图，每秒最多重试一次，同源最多四次；Loading/Ready 不触发该重试。Full 资源重试沿用单独的有限机制。
- Full 保留一个 CPU/GPU 共同许可，上传失败露出下层预览，换源取消过期加载。上传瞬间仍可能同时保有约 200 MB CPU 和约 200 MB GPU 数据，不是整机内存上限。

缺陷诊断及原厂版本证据见 [DIAGNOSIS.md](DIAGNOSIS.md)。装载交接见 [RELEASE_HANDOFF.md](RELEASE_HANDOFF.md)。

## 离线构建和验证

从本项目工作区运行 `tools/build_replay_adapter.py`、`tools/build_session.py`。依赖沿用固定 1.25.0 库、Qt 5.5.1 公共头、Zig 0.13.0 和项目已有的离线输入，不能换成其他固件文件。

CodeTests 中 `arm_machine.py`、`run_provider.py` 是测试支撑模块；入口为 `run_stable_provider.py`、`run_stable_catalog.py`、`run_stable_gate.py`、`run_reader_contract.py`、`run_stable_qml.py`、`run_session_qml.py`、`run_install_contract.py`。ARM 测试使用带 Pillow 的运行时 Python，并从固定项目缓存加载 Unicorn；QML 测试使用项目已有宿主 PySide6。`tools/audit_session.py` 检查固定 ARM 依赖闭包和接入地址。

构建和上述证据齐备后，`tools/build_reader_package.py` 生成整包；`CodeTests/run_reader_transfer.py` 执行宿主 shell 的实际全包传输和解包验证。所有报告绑定源码及产物哈希。宿主服务、Storage、GL 为显式替身，宿主 QML 为 Qt6，不能当成相机 Qt5、GPU、性能或连续拍摄证据。
