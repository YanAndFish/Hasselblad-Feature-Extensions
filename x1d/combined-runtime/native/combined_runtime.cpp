#include "install_window.h"
#define HBL_FORMAL_RUNTIME_STATUS_PATH "/tmp/hbl-x1d-combined/ui.status"
#define HBL_FORMAL_RUNTIME_RCC_PATH "/tmp/hbl-x1d-combined/combined-ui.rcc"
#define HBL_FORMAL_EXTRA_QML_COMPONENTS \
    "qrc:/mainmenu/MainScreen.qml", "qrc:/mainmenu/Menu.qml", \
    "qrc:/settings/SettingsGeneric.qml", "qrc:/mainmenu/ResidentLoader.qml", \
    "qrc:/af-settings/SettingsPage.qml", "qrc:/af-settings/AfSettingsHost.qml"
// 复用已实机验证的引闪适配器，保持与现存 worker 的 socket 协议。
// 只替换本次资源和安装状态路径，不重新装载 FARM 引闪代码。
#include "../../wireless-flash/native/formal_runtime.cpp"
