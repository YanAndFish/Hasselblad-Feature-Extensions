import QtQuick
import com.hasselblad.keys
import "qrc:/app/qml/scripts/Keys.js" as MKeys

// 由 MainScreen 中新增的 Loader 创建，稍后挂到原厂 ControlDrawer。
Item {
    id: root
    objectName: "X2dNativeMenuExtension"
    anchors.fill: parent
    z: 20
    visible: route.flashShowing
    enabled: visible
    property var screen: null
    property var drawer: null
    property var menu: null
    property var grid: null
    property var originalModel: null
    property Component originalDelegate: null
    property var originalLoader: null
    property var originalSwipe: null
    property var drawerList: null
    property bool attached: false
    readonly property bool menuActive: attached && drawer.mainState === "main_menu"
                                      && drawer.mainViewState === "main_menu" && !drawer.drawerAtTop

    function findItem(item, name) {
        if (!item) return null
        if (item.objectName === name) return item
        for (var i = 0; i < item.children.length; ++i) {
            var result = findItem(item.children[i], name)
            if (result) return result
        }
        return null
    }
    function attach() {
        if (attached || !screen || !screen.mainMenu || !screen.viewModel) return
        menu = screen.mainMenu
        drawer = menu.parent
        if (!drawer || drawer.objectName !== "ControlDrawer_root") return
        grid = findItem(screen, "MainScreen_grid")
        originalLoader = findItem(menu, "menu_loader")
        originalSwipe = findItem(menu, "MainMenu_swipeArea")
        drawerList = findItem(drawer, "ControlDrawer_list")
        if (!grid || !originalLoader || !originalSwipe || !drawerList) return
        // ControlDrawer.onLoaded 原文把信号接到这个具名函数；不能仅旁听。
        try { screen.loadSubMenuItem.disconnect(menu.loadSubmenu) }
        catch (error) { console.warn("X2D_NATIVE_MENU_ROUTE_NOT_READY"); return }
        originalModel = screen.viewModel.favoriteModel
        adapter.sourceModel = originalModel
        originalDelegate = grid.delegate
        adapter.stockDelegate = originalDelegate
        screen.loadSubMenuItem.connect(dispatch)
        screen.viewModel.favoriteModel = adapter
        parent = drawer
        attached = true
        screen.viewModel.inMenu = Qt.binding(function() { return originalLoader.active || route.flashShowing })
        screen.viewModel.preventSwipe = Qt.binding(function() { return originalSwipe.preventSwipe || route.flashShowing })
        drawerList.interactive = Qt.binding(function() { return !drawerList.blockSwipe && !route.flashShowing })
        console.info("X2D_NATIVE_MENU_ATTACHED")
    }
    function dispatch(name, sub, open, shortcut) { route.dispatch(name, sub, open, shortcut) }
    function detach() {
        if (!attached) return
        route.dismiss()
        screen.loadSubMenuItem.disconnect(dispatch)
        screen.loadSubMenuItem.connect(menu.loadSubmenu)
        screen.viewModel.favoriteModel = originalModel
        grid.delegate = originalDelegate
        screen.viewModel.inMenu = Qt.binding(function() { return originalLoader.active })
        screen.viewModel.preventSwipe = Qt.binding(function() { return originalSwipe.preventSwipe })
        drawerList.interactive = Qt.binding(function() { return !drawerList.blockSwipe })
        attached = false
    }
    FlashMenuModel {
        id: adapter
        supportedLayout: root.screen !== null && !root.screen.viewModel.sparseFavoritesGrid
        flashIcon: "flashMenu"
    }
    // 消费页面空白处触摸；半按等未处理按键继续交给原厂。
    MouseArea { anchors.fill: parent; onPressed: (mouse) => { mouse.accepted = true } }
    FlashMenuRoute {
        id: route
        anchors.fill: parent
        menuActive: root.menuActive
        mediaProcessing: root.screen !== null && root.screen.viewModel.mediaProcessing
        stockSubmenuActive: root.menu !== null && root.menu.state === "menu"
        iconBase: "assets/"
        onStockRequested: (name, sub, open, shortcut) => root.menu.loadSubmenu(name, sub, open, shortcut)
        onMainMenuRequested: { if (root.menuActive) root.screen.forceActiveFocus() }
    }
    Connections {
        target: root.drawer
        function onMainMenuExited() { route.dismiss() }
    }
    Connections {
        target: root.screen ? root.screen.viewModel : null
        function onCloseMenu() { route.dismiss() }
    }
    Keys.onPressed: (event) => {
        if (route.flashShowing && MKeys.pressedFnListAcc([KeyFn.Escape, KeyFn.JstkEscape, KeyFn.Menu], event))
            route.back()
        else if (route.flashShowing && MKeys.pressedFnListAcc([KeyFn.NavKey, KeyFn.Square, KeyFn.Cross], event)) {}
        else event.accepted = false
    }
    Component.onCompleted: {
        screen = parent ? parent.parent : null
        Qt.callLater(attach)
    }
    Component.onDestruction: detach()
}
