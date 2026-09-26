import QtQuick
import QtQml.Models

// 原厂网格的候选模型适配层；本文件不负责注入，不连接相机。
DelegateModel {
    id: root
    objectName: "FlashMenuModel"
    property var sourceModel: null
    property Component stockDelegate: null
    property bool supportedLayout: true
    property bool extensionEnabled: true
    property string flashLabel: "引闪"
    property string flashIcon: "flashMenu"
    readonly property string extensionName: "x2dCustomFlashUi"
    property bool reconciling: false
    property bool ready: false
    property bool extensionPresent: false
    property string rejectionReason: "not-ready"
    model: sourceModel
    delegate: stockDelegate

    // 原厂 CustomGridView 还调用这个方法，不能只提供同名角色。
    function itemEnabled(ix) {
        if (ix < 0 || ix >= items.count)
            return false
        var entry = items.get(ix)
        if (entry.isUnresolved)
            return extensionPresent && extensionEnabled && entry.model.menuName === extensionName
        return sourceModel !== null && sourceModel.itemEnabled(ix)
    }

    function requestReconcile() {
        if (ready && !reconciling)
            Qt.callLater(reconcile)
    }

    function reconcile() {
        if (!ready || reconciling)
            return
        reconciling = true
        var tail = -1
        var originals = 0
        var collision = false
        for (var i = 0; i < items.count; ++i) {
            var entry = items.get(i)
            if (entry.isUnresolved && entry.model.menuName === extensionName)
                tail = i
            else {
                originals++
                if (entry.model.menuName === extensionName)
                    collision = true
            }
        }
        var reason = sourceModel === null ? "no-source" :
                     !supportedLayout ? "unsupported-layout" :
                     collision ? "reserved-name-collision" :
                     originals !== 11 ? "source-count-not-eleven" : ""
        if (reason !== "") {
            if (tail >= 0)
                items.remove(tail, 1)
            extensionPresent = false
        } else {
            if (tail < 0) {
                items.insert(items.count, {
                    label: flashLabel, labelContext: "X2dMenuExtension",
                    iconSrc: flashIcon, itemEnabled: extensionEnabled,
                    menuName: extensionName
                })
            } else {
                if (tail !== items.count - 1)
                    items.move(tail, items.count - 1, 1)
                var data = items.get(items.count - 1).model
                data.label = flashLabel
                data.iconSrc = flashIcon
                data.itemEnabled = extensionEnabled
            }
            extensionPresent = true
        }
        rejectionReason = reason
        reconciling = false
    }

    items.onChanged: requestReconcile()
    property Connections sourceChanges: Connections {
        target: root.sourceModel
        ignoreUnknownSignals: true
        function onDataChanged() { root.requestReconcile() }
    }
    onSourceModelChanged: requestReconcile()
    onSupportedLayoutChanged: requestReconcile()
    onExtensionEnabledChanged: requestReconcile()
    onFlashLabelChanged: requestReconcile()
    onFlashIconChanged: requestReconcile()
    Component.onCompleted: { ready = true; requestReconcile() }
}
