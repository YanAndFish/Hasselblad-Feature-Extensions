# JPEG 写入完成的原生回执

以下是第一代 X1D-50c 官方 1.25.0 的静态调用链。尚未给 JPEG 回放新增可用状态登记，也未执行实机写卡。

## 已确认的接口

`libappscommon.so.1.0.0` 的 `StorageProxy::writeFile(QByteArray, offset, path)` 位于 `0x4ad9713c`。它在 `0x4ad97220` 调用 `DBusProxy::callWithFinished`，在 `0x4ad97230` 返回该结果。`callWithFinished`（`0x4ad6b4b8`）执行 `QDBusConnection::asyncCall` 并构造 `QDBusPendingCallWatcher`，所以该接口有可复用的异步完成对象。

`jpeg-daemon` 的 `ConvertCall` 在 `0x1e2dc` 调用写入，却忽略返回对象。代理默认 `onFinished`（`0x4ad6ae20`）只删除 watcher、检查并记录 D-Bus 错误；没有替增强登记 JPEG 已可用。编码阶段的 `encodeFinished` 也不表示文件写入完成。

## 服务端成功含义

`storage-daemon` 的元对象将 QByteArray 重载映射至 `0x1c464`，经 `FarmStorage` 虚表 `+0x50` 到 `0x328cc`，创建 `WriteFileCall`。后续：

1. `onFileOpened` 保存 FARM 返回的实际文件路径到 `WriteFileCall+0x30`（`0x38648`）。这能处理接收端决定的实际路径，不能只沿用请求时的同名推断。
2. QByteArray 数据经 `0x38920 → 0x30234` 传输，原路径会按 512 字节边界填充。`0x3041c` 调用 `QIODevice::write`，`0x30420` 比较所需与实际写入长度；成功再执行原传输提交助手。填充字节不是新增预览。
3. 之后 `0x38724` 调用 `FarmProxy::CloseFile`，并连接 `FarmStorage::onFileClosed`。
4. `onFileClosed`（`0x353f8`）先核对 watcher 是否是当前调用，再在 `0x35560` 检查 `isError`。只有成功分支取得 `WriteFileCall`，把其实际路径加入 reply（`0x355c0–0x355f8`），在 `0x35608` 经 `Bus::send` 回复原写入者。出错走错误回复和队列清理，不走这一成功回复。

因此未来的可用登记应绑定**本次写入的 watcher、无错误完成回复、返回的实际路径**，并与发起写入时保存的拍摄关联一起使用。目录 `Added` 是另一条 FARM 事件链，不能因为已出现条目便替代这份完成回执。这里确认的是软件层的传输与关闭成功，不是断电后的存储介质持久性保证。

## 集成尚未完成

需要在 JPEG 写入方持有本次调用上下文，接收完成回执、验证返回路径并发布可用状态；失败、取消、介质变化时撤销待完成状态。GUI／provider 也必须使用这一状态及同次拍摄关联，才能避免读取未完成文件。当前两个组件候选分别解决[编码失败传播](JPEG_FAILURE_PATCH.md)和[Full 配置](FULL_JPEG_CONFIG_PATCH.md)，不包含上述登记或回放集成。
