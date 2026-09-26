.import com.hasselblad.settings 1.0 as Settings
.import com.hasselblad.storage 1.0 as Storage
.import com.hasselblad.config 1.0 as Config
Qt.include(guiconfig.menuItemSpecificationsName)

// 只在语言索引改变时重建本 JS 实例内的翻译数组。
function refreshResidentTranslations() {
    var result = Qt.include(guiconfig.menuItemSpecificationsName)
    if (result.status !== 0) throw new Error("UI settings translation reload failed")
}
