"""仅制作内存 UI 候选，保留 R40 引闪行为及原厂图标。"""
from pathlib import Path
import sys
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parents[1]/'patch-distribution'))
from build_viewfinder_modes import read_rcc,rcc
v=read_rcc((P.parents[1]/'patch-distribution/build/candidate-r40/stage/files/af-ui.rcc').read_bytes())
s=v['/controlscreen/FlashPage.qml']
a=s.index('        Item {\n            objectName: "FlashSettingsPage"')
b=s.index('        FlashText {\n            objectName: "FlashError"',a)
s=s[:a]+'''        Flickable {
            objectName: "FlashSettingsPage"
            x: flashStyle.pageInset+(page.screen==="settings"?0:640); y: flashStyle.contentTop
            Behavior on x { NumberAnimation {duration:200;easing.type:Easing.InOutQuad} }
            z:2
            width: flashStyle.contentWidth; height: 380
            visible: page.screen==="settings" || x<640; clip:true
            enabled:page.screen==="settings"
            Rectangle {width:608;height:460;color:"black"}
            contentHeight:460; contentWidth:width
            flickableDirection:Flickable.VerticalFlick
            boundsBehavior:Flickable.StopAtBounds
            MouseArea {width:608;height:460;property real startX:0;property real startY:0
                onPressed:{startX=mouse.x;startY=mouse.y}
                onPositionChanged:if(pressed && mouse.x-startX>80 && mouse.x-startX>Math.abs(mouse.y-startY)*1.5)page.requestBack()
            }
            Repeater {
                model:["发送功率更新","发送引闪同步","调节步长","同步","快门","延迟标定"]
                delegate: Item {
                    x:8; y:[0,82,187,265,323,411][index]; width:592; height:index<2?80:58
                    FlashText { x:0;y:0;height:36;text:modelData;font.pixelSize:28;font.family:page.fontName }
                    FlashText { x:280;y:0;width:300;height:36;horizontalAlignment:Text.AlignRight;font.pixelSize:26;font.family:page.fontName
                        opacity:index===3||index===4?0.62:1
                        text:[page.sendPowerUpdates?"开":"关",page.sendFlashSync?"开":"关",page.adjustmentStepText,page.syncText,page.shutterText,""][index] }
                    FlashText {x:0;y:40;height:27;visible:index<2;font.pixelSize:18;opacity:0.6;font.family:page.fontName
                        text:index===0?"调整功率时同步到闪光灯":"拍摄时发送引闪信号"}
                    MouseArea {anchors.fill:parent;property real startX:0;property real startY:0;property bool swiped:false
                        onPressed:{startX=mouse.x;startY=mouse.y;swiped=false}
                        onPositionChanged:if(pressed && mouse.x-startX>80 && mouse.x-startX>Math.abs(mouse.y-startY)*1.5){swiped=true;page.requestBack()}
                        onClicked: {if(swiped)return;if(index===5)page.calibrationOpen=true;else if(index===1||index===2){settingChoice.kind=index;settingChoice.visible=true}}
                    }
                }
            }
            Repeater {model:[168,244,385];Rectangle {x:8;y:modelData;width:592;height:1;color:"#444444"}}
        }
        Rectangle {
            id:settingChoice;objectName:"FlashSettingChoice";anchors.fill:parent;z:99;color:"#b0000000";visible:false
            property int kind:0
            MouseArea {anchors.fill:parent;onClicked:settingChoice.visible=false}
            Rectangle {x:113;y:82;width:414;height:316;color:"#181818";border.color:"#666666"
                Text {x:20;y:20;color:"white";font.pixelSize:28;text:["发送功率更新","发送引闪同步","调节步长"][settingChoice.kind]}
                ListView {x:20;y:86;width:374;height:210;clip:true;model:settingChoice.kind===2?["0.3 EV","0.1 EV"]:["关","开"]
                    delegate:Rectangle {width:374;height:86;color:"transparent"
                        Text {anchors.centerIn:parent;text:modelData;color:"white";font.pixelSize:30}
                        MouseArea {anchors.fill:parent;onClicked:{
                            if(settingChoice.kind===0)page.setDeliveryOptions(index===1,page.sendFlashSync)
                            else if(settingChoice.kind===1)page.setDeliveryOptions(page.sendPowerUpdates,index===1)
                            else page.setAdjustmentStep(index===0,true)
                            settingChoice.visible=false
                        }}
                    }
                }
            }
        }
'''+s[b:]
footer=s.index('objectName: "FlashChooseGroups"')
s=s[:footer]+s[footer:].replace('visible: page.screen!=="wireless"', 'visible: page.screen!=="wireless" && page.screen!=="settings"')
# Reuse factory selector visuals and interaction; change only choices and callback.
selector=v['/settings/components/ListSelectorSettings.qml']
selector=selector.replace('property var viewfinderChoices: ["正常", "电子取景器", "屏幕取景"]','property var viewfinderChoices: ["0.3 EV", "0.1 EV"]\n    signal stepSelected(bool thirds)')
a=selector.index('    function saveViewfinder(text) {');b=selector.index('    property var theProxy',a)
selector=selector[:a]+'    function saveViewfinder(text) {var i=viewfinderChoices.indexOf(text);if(i>=0)stepSelected(i===0)}\n'+selector[b:]
v['/settings/components/FlashStepSelector.qml']=selector
s=s.replace('import QtQuick 2.5','import QtQuick 2.5\nimport "../settings/components"',1)
a=s.index('        Rectangle {\n            id:settingChoice;');b=s.index('        FlashText {\n            objectName: "FlashError"',a)
s=s[:a]+'''        FlashStepSelector {
            id:settingChoice;objectName:"FlashSettingChoice";anchors.fill:parent
            popupAnchor {leftMargin:350;rightMargin:16;topMargin:86;bottomMargin:30}
            onStepSelected:page.setAdjustmentStep(thirds,true)
        }
'''+s[b:]
s=s.replace('else if(index===1||index===2){settingChoice.kind=index;settingChoice.visible=true}', 'else if(index===0)page.setDeliveryOptions(!page.sendPowerUpdates,page.sendFlashSync);else if(index===1)page.setDeliveryOptions(page.sendPowerUpdates,!page.sendFlashSync);else if(index===2)settingChoice.openViewfinder(page,page.thirdStopSteps?0:1)')
s=s.replace('opacity:index===3||index===4?0.62:1','visible:index>=2;opacity:index===3||index===4?0.62:1')
s=s.replace('MouseArea {anchors.fill:parent;property real startX:','''FlashToggleRow {x:508;y:3;width:84;height:36;visible:index<2;label:"";checked:index===0?page.sendPowerUpdates:page.sendFlashSync
                        onToggled:if(index===0)page.setDeliveryOptions(!page.sendPowerUpdates,page.sendFlashSync);else page.setDeliveryOptions(page.sendPowerUpdates,!page.sendFlashSync)}
                    MouseArea {anchors.fill:parent;property real startX:''')
# Follow the factory drag/release policy, never navigate during movement.
s=s.replace('        Flickable {\n            objectName: "FlashSettingsPage"','''        MouseArea {
            id:settingsSwipe;anchors.fill:parent;anchors.topMargin:76;z:2
            Connections {target:page;onScreenChanged:settingsList.x=flashStyle.pageInset+(page.screen==="settings"?0:640)}
            enabled:page.screen==="settings" && !settingChoice.visible && !page.calibrationOpen
            drag {target:settingsList;axis:Drag.XAxis;minimumX:flashStyle.pageInset;maximumX:flashStyle.pageInset+640;threshold:constants.dragThreshold;filterChildren:true}
            drag.onActiveChanged:if(!drag.active){
                if(settingsList.x>flashStyle.pageInset+640/constants.swipeLengthDividor){page.requestBack();settingsList.x=flashStyle.pageInset+640}
                else settingsList.x=flashStyle.pageInset
            }
        Flickable {
            id:settingsList;objectName: "FlashSettingsPage"''')
s=s.replace('Behavior on x { NumberAnimation {duration:200;', 'Behavior on x {enabled:!settingsSwipe.drag.active; NumberAnimation {duration:constants.menuSwipeDuration;')
a=s.index('            MouseArea {width:608;height:460;');b=s.index('            Repeater {',a);s=s[:a]+s[b:]
a=s.index('                    MouseArea {anchors.fill:parent;property real startX:');b=s.index('                        onClicked:',a)
s=s[:a]+'                    MouseArea {anchors.fill:parent;\n'+s[b:]
s=s.replace('if(swiped)return;','')
s=s.replace('        FlashStepSelector {','        }\n        FlashStepSelector {',1)
# Match the compact header labels rather than enlarge CH while shrinking exposure.
s=s.replace('x: 326; y: 10; spacing: 8; height: 52','x: 344; y: 10; spacing: 8; height: 52').replace('width: 72; height: parent.height','width: 64; height: parent.height').replace('width: 84; height: parent.height','width: 72; height: parent.height')
s=s.replace('x: 70; y: 10; width: 246; height: 52','x: 60; y: 10; width: 280; height: 52').replace('font.pixelSize: 21; font.weight','font.pixelSize: 24; font.weight').replace('page.apertureText+"  "+page.shutterSpeedText+"  "+page.isoText','page.apertureText+" "+page.shutterSpeedText+" "+page.isoText')
s=s.replace('font.pixelSize: Math.max(17,Math.min(21,Math.floor(21*width/Math.max(1,exposureMetrics.advanceWidth))))','font.pixelSize: Math.max(20,Math.min(24,Math.floor(24*width/Math.max(1,exposureMetrics.advanceWidth))))')
a=s.index('        Item {\n            objectName: "FlashGroupSelection"');b=s.index('        Item {\n            objectName: "FlashPowerEditor"',a)
part=s[a:b].replace('objectName: "FlashGroupSelection"; x: flashStyle.pageInset;', 'id:selectionPane;objectName: "FlashGroupSelection"; x: flashStyle.pageInset+(page.screen==="selection"?0:640);').replace('height: flashStyle.contentHeight','height:380').replace('visible: page.screen==="selection"','visible: page.screen==="selection" || x<640\n            Behavior on x {enabled:!selectionSwipe.drag.active;NumberAnimation {duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad}}\n            Rectangle {anchors.fill:parent;color:"black"}')
wrapper='''        MouseArea {
            id:selectionSwipe;anchors.fill:parent;anchors.topMargin:76;z:2;enabled:page.screen==="selection"
            Connections {target:page;onScreenChanged:selectionPane.x=flashStyle.pageInset+(page.screen==="selection"?0:640)}
            drag {target:selectionPane;axis:Drag.XAxis;minimumX:flashStyle.pageInset;maximumX:flashStyle.pageInset+640;threshold:constants.dragThreshold;filterChildren:true}
            drag.onActiveChanged:if(!drag.active){if(selectionPane.x>flashStyle.pageInset+640/constants.swipeLengthDividor){page.requestBack();selectionPane.x=flashStyle.pageInset+640}else selectionPane.x=flashStyle.pageInset}
'''
s=s[:a]+wrapper+part+'        }\n'+s[b:]
footer=s.index('objectName: "FlashChooseGroups"')
s=s[:footer]+s[footer:].replace('&& page.screen!=="settings"','&& page.screen!=="settings" && page.screen!=="selection"')
s=s.replace('visible: page.screen!=="settings" }','visible: page.screen!=="settings" && page.screen!=="selection" }')
s=s.replace('x: flashStyle.pageInset+(page.screen==="settings"?0:640); y: flashStyle.contentTop','x: flashStyle.pageInset+(page.screen==="settings"?0:640); y: flashStyle.contentTop-76')
s=s.replace('x: flashStyle.pageInset+(page.screen==="selection"?0:640); y: flashStyle.contentTop','x: flashStyle.pageInset+(page.screen==="selection"?0:640); y: flashStyle.contentTop-76')
# Detail pages use the whole content area; footer actions belong to the overview.
s=s.replace('&& page.screen!=="selection"', '&& page.screen!=="selection" && page.screen!=="power"')
# Expand the five overview rows into the former standalone status strip.
s=s.replace('width: 608; height: 58', 'width: 608; height: 61')
s=s.replace('height: flashStyle.contentHeight', 'height: page.screen==="groups" ? 305 : flashStyle.contentHeight')
s=s.replace('y: 376; width: flashStyle.contentWidth; height: 16', 'y: page.screen==="groups" ? 375 : 450; width: flashStyle.contentWidth; height: 20')
# The group letter is part of the large power value, not a duplicate header label.
s=s.replace('groups.get(page.selectedGroup).letter+"  组"', '""')
needle='FlashValueText { width: implicitWidth; height: parent.height; text: page.powerText(groups.get(page.selectedGroup).tenthStops);'
assert needle in s
# Group identity stays under the M/OFF control regardless of power text width.
detail_start=s.index('objectName: "FlashPowerEditor"')
label_pos=s.index('            Item {\n                x: 20; y: 76; width: 568; height: 112',detail_start)
s=s[:label_pos]+'''            FlashValueText {x:20;y:76;width:110;height:112;text:groups.get(page.selectedGroup).letter;horizontalAlignment:Text.AlignHCenter;font.pixelSize:80;font.family:page.fontName}
'''+s[label_pos:]
s=s.replace('x: 20; y: 76; width: 568; height: 112','x: 150; y: 76; width: 438; height: 112',1)
base_start=s.index('                Row {',s.index('x: 150; y: 76; width: 438; height: 112'))
base_end=s.index('            Row {\n                x: 20; y: 211;',base_start)
s=s[:base_start]+'''                FlashValueText {
                    id:detailPowerBase;objectName:"DetailPowerBase";anchors.horizontalCenter:parent.horizontalCenter
                    width:implicitWidth;height:parent.height;text:page.powerText(groups.get(page.selectedGroup).tenthStops)
                    font.pixelSize:80;font.family:page.fontName
                }
                FlashValueText {
                    objectName:"DetailPowerFraction";anchors.left:detailPowerBase.right;anchors.leftMargin:10
                    width:implicitWidth;height:parent.height;text:page.fractionText(groups.get(page.selectedGroup).tenthStops)
                    visible:text.length>0;font.pixelSize:32;font.family:page.fontName
                }
            }
'''+s[base_end:]
s=s.replace('x: 150; y: 76; width: 438; height: 112','x: 20; y: 76; width: 568; height: 112',1)
s=s.replace('Math.round(contentY/58)*58', 'Math.round(contentY/61)*61')
s=s.replace('id: groupContent; width: parent.width;', 'id: groupContent; y:3; width: parent.width;')
# Consume gestures in the power strip so they cannot become page navigation.
a=s.index('            Row {\n                x: 20; y: 211; spacing: 8')
b=s.index('\n        Item {\n            objectName: "FlashWirelessEditor"',a)
s=s[:a]+'''            Row {
                x:20;y:230;spacing:12
                Item {width:70;height:72
                    FlashText {anchors.centerIn:parent;text:"−";font.pixelSize:52;font.family:page.fontName}
                    MouseArea {anchors.fill:parent;preventStealing:true;onClicked:page.adjustPower(-1)}
                }
                Rectangle {width:404;height:72;color:"#151515";border.color:"#555555";radius:4
                    FlashText {anchors.centerIn:parent;text:"左右滑动调节功率";font.pixelSize:22;font.family:page.fontName;opacity:0.65}
                    MouseArea {
                        objectName:"FlashDetailPowerStrip";anchors.fill:parent;preventStealing:true
                        property real pressX:0;property int startValue:0
                        onPressed:{pressX=mouse.x;startValue=page.currentPower;page.powerGestureActive=true}
                        onPositionChanged:if(pressed && Math.abs(mouse.x-pressX)>=8 && page.currentGroupEnabled){
                            var raw=(mouse.x-pressX)/width*page.swipeSpanEv*(page.thirdStopSteps?3:10)
                            page.swipePower(page.selectedGroup,startValue,raw<0?Math.ceil(raw):Math.floor(raw))
                        }
                        onReleased:page.powerGestureActive=false
                        onCanceled:page.powerGestureActive=false
                        Component.onDestruction:page.powerGestureActive=false
                    }
                }
                Item {width:70;height:72
                    FlashText {anchors.centerIn:parent;text:"+";font.pixelSize:52;font.family:page.fontName}
                    MouseArea {anchors.fill:parent;preventStealing:true;onClicked:page.adjustPower(1)}
                }
            }
        }
''' +s[b:]
# Full-height selection hit surface, including the blank space below the grid.
s=s.replace('id:selectionPane;objectName:', 'id:selectionPane;objectName:')
s=s.replace('width: flashStyle.contentWidth; height:380', 'width: flashStyle.contentWidth; height:parent.height-y')
# Detail navigation owns only gestures outside the dedicated power strip.
a=s.index('        Item {\n            objectName: "FlashPowerEditor"')
b=s.index('        Item {\n            objectName: "FlashWirelessEditor"',a)
detail=s[a:b].replace('objectName: "FlashPowerEditor";', 'id:detailPane;objectName: "FlashPowerEditor";').replace('y: flashStyle.contentTop;', 'y: 10;').replace('height: page.screen==="groups" ? 305 : flashStyle.contentHeight','height:parent.height')
detail=detail.replace('            visible: page.screen==="power"', '''            visible: page.screen==="power"
            Rectangle {anchors.fill:parent;color:"black";z:-1}
            Behavior on x {enabled:!detailSwipe.pressed;NumberAnimation {duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad}}
            Behavior on y {enabled:!detailSwipe.pressed && !detailSwipe.settling;NumberAnimation {duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad}}''')
wrapper='''        MouseArea {
            id:detailSwipe;anchors.fill:parent;anchors.topMargin:76;z:2;clip:true
            enabled:page.screen==="power" && !page.calibrationOpen && !settling
            property real startX:0;property real startY:0;property int direction:0
            property bool settling:false;property int pendingGroup:-1
            onPressed:{startX=mouse.x;startY=mouse.y;direction=0}
            onPositionChanged:if(pressed){
                var dx=mouse.x-startX,dy=mouse.y-startY
                if(direction===0 && Math.max(Math.abs(dx),Math.abs(dy))>=constants.dragThreshold)
                    direction=Math.abs(dx)>Math.abs(dy)?1:2
                if(direction===1)detailPane.x=flashStyle.pageInset+dx
                if(direction===2)detailPane.y=10+dy
            }
            onReleased:{
                var dx=mouse.x-startX,dy=mouse.y-startY
                if(direction===1 && Math.abs(dx)>640/constants.swipeLengthDividor)page.requestBack()
                if(direction===2 && Math.abs(dy)>height/constants.swipeLengthDividor){
                    var i=page.visibleGroups.indexOf(page.selectedGroup)+(dy<0?1:-1)
                    if(i>=0 && i<page.visibleGroups.length){
                        pendingGroup=i;settling=true;groupSettle.to=10+(dy<0?-height:height);groupSettle.restart();return
                    }
                }
                if(direction===2){pendingGroup=-1;settling=true;groupSettle.to=10;groupSettle.restart();return}
                detailPane.x=flashStyle.pageInset;detailPane.y=10;direction=0
            }
            onCanceled:{detailPane.x=flashStyle.pageInset;detailPane.y=10;direction=0}
            NumberAnimation {id:groupSettle;target:detailPane;property:"y";duration:constants.menuSwipeDuration;easing.type:Easing.OutCubic
                onStopped:{
                    if(detailSwipe.pendingGroup>=0)page.selectedGroup=page.visibleGroups[detailSwipe.pendingGroup]
                    detailPane.y=10;detailSwipe.direction=0;detailSwipe.pendingGroup=-1;detailSwipe.settling=false
                }
            }
'''
neighbor=detail.replace('id:detailPane;', '''id:neighborPane;
            enabled:false
            property int neighborIndex:page.visibleGroups.indexOf(page.selectedGroup)+modelData
            property int previewGroup:neighborIndex>=0 && neighborIndex<page.visibleGroups.length?page.visibleGroups[neighborIndex]:page.selectedGroup
            ''',1)
neighbor=neighbor.replace('x: flashStyle.pageInset; y: 10;', 'x:flashStyle.pageInset;y:detailPane.y+modelData*detailSwipe.height;')
neighbor=neighbor.replace('visible: page.screen==="power"', 'visible: page.screen==="power" && detailSwipe.direction===2 && neighborIndex>=0 && neighborIndex<page.visibleGroups.length',1)
neighbor=neighbor.replace('groups.get(page.selectedGroup)', 'groups.get(neighborPane.previewGroup)')
neighbor=neighbor.replace('Behavior on x {enabled:!detailSwipe.pressed;NumberAnimation {duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad}}','')
neighbor=neighbor.replace('Behavior on y {enabled:!detailSwipe.pressed && !detailSwipe.settling;NumberAnimation {duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad}}','')
s=s[:a]+wrapper+detail+'        Repeater {model:[-1,1]\n'+neighbor+'        }\n        }\n'+s[b:]
# Keep the overview painted underneath child pages during interactive return.
s=s.replace('visible: page.screen==="groups"; clip: true', 'visible: true; clip: true\n            enabled:page.screen==="groups"',1)
s=s.replace('objectName: "FlashExposureSummary"; x: 60; y: 10; width: 280; height: 52; visible: page.screen==="groups"', 'objectName: "FlashExposureSummary"; x: 60; y: 10; width: 280; height: 52; visible: page.screen==="groups" || page.screen==="power"')
s=s.replace('Image { x: 70; y: 24; width: 22; height: 25; visible: page.screen!=="groups";', 'Image { x: 70; y: 24; width: 22; height: 25; visible: page.screen!=="groups" && page.screen!=="power";')
a=s.index('        FlashIconButton {\n            objectName: "FlashBack"')
b=s.index('        Image {',a)
s=s[:a]+'''        Item {
            objectName:"FlashBack";x:4;y:8;width:60;height:56
            Canvas {anchors.centerIn:parent;width:24;height:40
                onPaint:{var c=getContext("2d");c.clearRect(0,0,width,height);c.strokeStyle="white";c.lineWidth=4;c.lineCap="round";c.lineJoin="round";c.beginPath();c.moveTo(21,3);c.lineTo(4,20);c.lineTo(21,37);c.stroke()}
            }
            MouseArea {anchors.fill:parent;onClicked:page.requestBack()}
        }
'''+s[b:]
# Shared separators across the overview and its settings/selection/detail pages.
s=s.replace('outlined: true','outlined: false')
s=s.replace('color: "white"; opacity: flashStyle.frameOpacity','color: "#555"; opacity: 1')
# Selection brackets encode selected groups, unlike decorative status-cell
# borders. Preserve the native pair and their selected-state visibility.
s=s.replace('source: page.iconBase+"left_bracket.png"; visible: parent.selected','objectName:"SelectedGroupLeftBracket"; source: page.iconBase+"left_bracket.png"; visible: parent.selected')
s=s.replace('source: page.iconBase+"right_bracket.png"; visible: parent.selected','objectName:"SelectedGroupRightBracket"; source: page.iconBase+"right_bracket.png"; visible: parent.selected')
needle='        Row {\n            x: 344;'
assert needle in s
s=s.replace(needle,'''        Repeater {
            model:[340,412,492,568]
            Rectangle {x:modelData;y:0;width:1;height:76;color:"#555";visible:page.screen!=="wireless"}
        }
        Repeater {
            model:[324,416,526]
            Rectangle {x:modelData;y:flashStyle.footerTop;width:1;height:flashStyle.footerHeight;color:"#555";visible:page.screen==="groups"}
        }
'''+needle,1)
v['/controlscreen/FlashPage.qml']=s
v['/controlscreen/FlashText.qml']=v['/controlscreen/FlashText.qml'].replace('font.weight: Font.Light','font.weight: Font.Normal')
v['/controlscreen/FlashPage.qml']=s=s.replace('font.pixelSize: 14; font.family: page.fontName; horizontalAlignment: Text.AlignHCenter','font.pixelSize: 24; font.family: page.fontName; horizontalAlignment: Text.AlignHCenter')
v['/mainmenu/DirectMainMenu.qml']=(P/'DirectMainMenu.qml').read_text(encoding='utf-8')
v['/mainmenu/PagePool.qml']=(P/'PagePool.qml').read_text(encoding='utf-8')
# Refresh specification arrays that translated their labels at script load.
# Read the actual firmware resource, not host-test copies of the importer.
sys.path.insert(0,str(P.parents[1]/'tools'))
from binary import ArmElf,qml_files
importer=qml_files(ArmElf.load('usr/bin/victory-gui'))['/settings/scripts/MenuItemImporter.js']
assert 'Qt.include(guiconfig.menuItemSpecificationsName)' in importer
v['/settings/scripts/MenuItemImporter.js']=importer+'\nfunction refreshResidentTranslations(){Qt.include(guiconfig.menuItemSpecificationsName)}\n'
for name in ['SettingsPage.qml','SettingsToggle.qml','NativeSettingsPage.qml','NativeSettingsActions.qml','CaptureFormatPolicy.qml']:
    v['/settings/'+name]=(P/name).read_text(encoding='utf-8-sig')
# Replace the navigation root rather than covering a live factory menu.
v['/mainmenu/OwnMainScreen.qml']=(P/'OwnMainScreen.qml').read_text(encoding='utf-8')
touch=v['/common/TouchWindow.qml']
assert touch.count('source: guiconfig.mainMenuName')==1
v['/common/TouchWindow.qml']=touch.replace('source: guiconfig.mainMenuName','source: "qrc:///mainmenu/OwnMainScreen.qml"',1)
# These original page overrides are now unreachable from the new root.
# Removing them from the overlay restores the factory resources without
# altering firmware files or retained special-tool implementations.
v.pop('/mainmenu/MainScreen.qml',None)
v.pop('/mainmenu/Menu.qml',None)
generic=v['/settings/SettingsGeneric.qml']
needle='var settingsList = MenuItems.getSettingsList(newItemValues);'
assert needle in generic
generic=generic.replace(needle,needle+'''
        if(newItemValues === "cameraSettingsAutofocus") {
            settingsList = [{editType:MenuItems.SettingType.SUBHEADER,text1:"自动对焦"}].concat(settingsList,
                [{editType:MenuItems.SettingType.SUBHEADER,text1:"手动对焦"}],
                MenuItems.getSettingsList("cameraSettingsManualFocus"))
        }
''',1)
sys.path.insert(0,str(P))
from settings_layout import apply_layout
generic=apply_layout(generic)
generic=generic.replace('objectName: "SettingsGeneric_list"','objectName: "SettingsGeneric_list"\n        flickableDirection: Flickable.VerticalFlick',1)
v['/settings/SettingsGeneric.qml']=generic
# Parameter screen: scale only the drawn symbols, preserving native hit boxes.
control=v['/controlscreen/ControlScreen.qml']
for control_id in ('whitebalance_control','af_control','exposureControl','meterControl','driveControl'):
    marker='id: '+control_id+'\n'
    assert marker in control
    control=control.replace(marker,marker+'                    symbolScale: 0.86\n',1)
control=control.replace('valueSize: constants.cameraSettingSmallTextSize',
                        'valueSize: constants.cameraSettingSmallTextSize - 2',1)
control=control.replace('color: constants.cameraViewLineColor','color: "#555"')
control=control.replace('id: af_control\n','id: af_control\n                    symbolText: Camera.FocusMode === Config.Focus_AFS ? "AF" : ""\n',1)
from control_layout import apply_control_layout
control=apply_control_layout(control)
v['/controlscreen/ControlScreen.qml']=control
button_path=P.parents[1]/'candidates/replay-page-resident/build/original-page/components/buttons/BracketedCameraControl.qml'
button=button_path.read_text(encoding='utf-8')
prefix=(P.parents[1]/'candidates/replay-page-resident/build/original-page').resolve().as_uri()+'/'
assert prefix in button
button=button.replace(prefix,'qrc:/')
button=button.replace('property alias symbol: symbol.source',
                      'property alias symbol: symbol.source\n    property string symbolText: ""\n    property real symbolScale: 1.0')
button=button.replace('id: symbol\n','id: symbol\n        scale: root.symbolScale\n',1)
button=button.replace('id: symbol\n','id: symbol\n        visible: root.symbolText === ""\n',1)
button=button.replace('    SequentialAnimation {','''    Rectangle {
        objectName: "FocusModeBadge"
        anchors.centerIn: parent
        width: 77; height: 51; radius: 5
        scale: root.symbolScale
        visible: root.symbolText!==""
        color: root.showBracket ? "white" : "#808080"
        opacity: root.symbolOpacity
        Text {anchors.centerIn:parent;text:root.symbolText;color:"black";font.pixelSize:44;font.bold:true}
    }

    SequentialAnimation {''',1)
button=button.replace('visible: showBracket','visible: showBracket && root.symbolScale===1.0')
button=button.replace('    SequentialAnimation {','    Rectangle {anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;width:1;height:parent.height;color:"#555";visible:root.symbolScale!==1.0}\n\n    SequentialAnimation {',1)
assert 'file:///' not in button
v['/components/buttons/BracketedCameraControl.qml']=button
# Four full group rows; the footer keeps icon labels and all original actions.
s=s.replace('page.screen==="groups" ? 305','page.screen==="groups" ? 304')
s=s.replace('Math.round(contentY/61)*61','Math.round(contentY/76)*76')
s=s.replace('width: 608; height: 61','width: 608; height: 76')
a=s.index('id: groupList;')
b=s.index('id:selectionSwipe',a)
rows=s[a:b]
for value in ['flashStyle.groupSize','flashStyle.powerSize']:
    rows=rows.replace('font.pixelSize: '+value+';', 'font.pixelSize: 32;')
s=s[:a]+rows+s[b:]
a=s.index('id:settingsList;')
b=s.index('objectName: "FlashError"',a)
settings=s[a:b].replace('font.pixelSize:28','font.pixelSize:32').replace('font.pixelSize:26','font.pixelSize:32')
settings=settings.replace('height:36','height:42').replace('color:"#444444"','color:"#555"')
settings=settings.replace('height:460','height:604').replace('contentHeight:460','contentHeight:604')
settings=settings.replace('x:8; y:[0,82,187,265,323,411][index]; width:592; height:index<2?80:58',
    'objectName:"FlashSettingRow"+index; x:8; y:[0,106,236,340,420,524][index]; width:592; height:index<2?106:80')
settings=settings.replace('FlashText { x:0;y:0;height:42','FlashText { x:0;y:0;height:80')
settings=settings.replace('x:280;y:0;width:300;height:42','x:280;y:0;width:300;height:80')
settings=settings.replace('FlashText {x:0;y:40;height:27','FlashText {x:0;y:66;height:27')
settings=settings.replace('FlashToggleRow {x:508;y:3;', 'FlashToggleRow {x:508;y:19;')
settings=settings.replace('FlashToggleRow {x:508;y:19;width:84;height:42;visible:index<2;label:"";', 'SettingsToggle {x:506;y:22;visible:index<2;')
settings=settings.replace('onToggled:if(index===0)', 'MouseArea {anchors.fill:parent;onClicked:if(index===0)')
settings=settings.replace('page.setDeliveryOptions(page.sendPowerUpdates,!page.sendFlashSync)}', 'page.setDeliveryOptions(page.sendPowerUpdates,!page.sendFlashSync)}}')
settings=settings.replace('model:[168,244,385]','model:[224,328,512]')
s=s[:a]+settings+s[b:]
v['/controlscreen/FlashPage.qml']=s
v['/controlscreen/SettingsToggle.qml']=(P/'SettingsToggle.qml').read_text(encoding='utf-8')
# The firmware 1.25 native pressed cell is 82 pixels tall (left_bracket.png).
# Keep four full 76-pixel group rows between equal-height status/footer bars.
style=v['/controlscreen/FlashStyle.qml']
style=style.replace('footerTop: 399','footerTop: 398').replace('footerHeight: 70','footerHeight: 82')
v['/controlscreen/FlashStyle.qml']=style
s=s.replace('y:0;width:1;height:76;color:', 'y:0;width:1;height:82;color:')
s=s.replace('y: 76; width: flashStyle.contentWidth','y: 82; width: flashStyle.contentWidth')
s=s.replace('y: 392; width: flashStyle.contentWidth','y: 397; width: flashStyle.contentWidth')
s=s.replace('x: 344; y: 10; spacing: 8; height: 52','x: 344; y: 0; spacing: 8; height: 82')
s=s.replace('x: 60; y: 10; width: 280; height: 52','x: 60; y: 0; width: 280; height: 82')
s=s.replace('x: 574; y: 20; width: 50; height: 32','x: 574; y: 25; width: 50; height: 32')
s=s.replace('text: "CH "+page.channel;', 'horizontalAlignment:Text.AlignHCenter;text: "CH "+page.channel;')
s=s.replace('text: "ID "+(page.wirelessId===0 ? "OFF" : page.wirelessId);', 'horizontalAlignment:Text.AlignHCenter;text: "ID "+(page.wirelessId===0 ? "OFF" : page.wirelessId);')
# User's latest correction: footer is icons only; status label stays intact.
s=s.replace('label: page.screen==="selection" ? "完成" : "选择分组"', 'label: ""')
s=s.replace('label: "试闪"', 'label: ""').replace('label: "设置"', 'label: ""')
s=s.replace('"FlashTest"; x: 334; y: flashStyle.footerTop; width: 72;', '"FlashTest"; x: 324; y: flashStyle.footerTop; width: 92;')
s=s.replace('"FlashChooseGroups"; x: 425; y: flashStyle.footerTop; width: 88;', '"FlashChooseGroups"; x: 416; y: flashStyle.footerTop; width: 110;')
s=s.replace('"FlashSettings"; x: 536; y: flashStyle.footerTop; width: 88;', '"FlashSettings"; x: 526; y: flashStyle.footerTop; width: 114;')
s=s.replace('x: flashStyle.pageInset; y: 82; width: flashStyle.contentWidth', 'x: 0; y: 82; width: 640')
s=s.replace('x: flashStyle.pageInset; y: 397; width: flashStyle.contentWidth', 'x: 0; y: 397; width: 640')
s=s.replace('x: 0; y: 82; width: 640; height: 1; color: "#555"; opacity: 1; visible: page.screen!=="settings" && page.screen!=="selection" && page.screen!=="power"', 'x: 0; y: 82; width: 640; height: 1; color: "#555"; opacity: 1; visible: page.screen!=="wireless"')
# Use the parameter screen's 100-pixel minimum cell and 13-pixel outer inset.
s=s.replace('model:[324,416,526]', 'model:[327,427,527]')
s=s.replace('"FlashTest"; x: 324; y: flashStyle.footerTop; width: 92;', '"FlashTest"; x: 327; y: flashStyle.footerTop; width: 100;')
s=s.replace('"FlashChooseGroups"; x: 416; y: flashStyle.footerTop; width: 110;', '"FlashChooseGroups"; x: 427; y: flashStyle.footerTop; width: 100;')
s=s.replace('"FlashSettings"; x: 526; y: flashStyle.footerTop; width: 114;', '"FlashSettings"; x: 527; y: flashStyle.footerTop; width: 100;')
a=s.index('id: groupList;');b=s.index('id:selectionSwipe',a)
part=s[a:b].replace('x: flashStyle.pageInset; y: flashStyle.contentTop; width: flashStyle.contentWidth;', 'x: 0; y: flashStyle.contentTop; width: 640;')
part=part.replace('width: 608; height: 76','width: 640; height: 76')
part=part.replace('id: groupContent; y:3; width: parent.width;', 'id: groupContent; x:16; y:3; width: 608;')
part=part.replace('y: groupRow.height-1; width: flashStyle.contentWidth; height: 1; color: "white"; opacity: flashStyle.dividerOpacity', 'y: groupRow.height-1; width: groupRow.width; height: 1; color: "#555"; opacity: 1')
s=s[:a]+part+s[b:]
a=s.index('x: flashStyle.pageInset; y: flashStyle.footerTop; width: 300;')
b=s.index('        FlashIconButton {',a)
part=s[a:b].replace('x: flashStyle.pageInset;', 'x: 13;').replace('width: 300;', 'width: 314;').replace('height: 64;', 'height: flashStyle.footerHeight;').replace('height: 70;', 'height: flashStyle.footerHeight;')
s=s[:a]+part+s[b:]
button=v['/controlscreen/FlashIconButton.qml']
button=button.replace('y: 8; width: 34; height: 30; visible: button.groupSelector', 'y: button.label.length ? 8 : (button.height-height)/2; width: 34; height: 30; visible: button.groupSelector')
button=button.replace('width: 34; height: 30; visible: button.groupSelector', 'width: 34; height: 30; scale: button.label.length ? 1 : 1.4; visible: button.groupSelector')
v['/controlscreen/FlashIconButton.qml']=button
s=s.replace('source: page.iconBase+"FlashStatus.png"; label: "";', 'source: page.iconBase+"FlashStatus.png"; iconSize:46; label: "";')
s=s.replace('iconSize: 46\n            outlined: false', 'iconSize: 74\n            outlined: false')
s=s.replace('objectName: "FlashMaster"; x: 500; y: 3', 'objectName: "FlashMaster"; x: 492; y: 0; width:76; height:82; iconSize:45; labelSize:18; centeredLayout:true')
radio=v['/common/RadioModeButton.qml']
radio=radio.replace('id: button', 'id: button\n    property real iconSize:30\n    property real labelSize:15\n    property bool centeredLayout:false',1)
radio=radio.replace('width: 30; height: 30; anchors.horizontalCenter: parent.horizontalCenter; y: 7', 'width:button.iconSize;height:button.iconSize;anchors.horizontalCenter:parent.horizontalCenter;y:button.centeredLayout?(button.height-button.iconSize-26)/2:7')
radio=radio.replace('c.clearRect(0,0,width,height)', 'c.reset();c.clearRect(0,0,width,height);c.scale(width/30,height/30)')
radio=radio.replace('anchors.bottomMargin: 5', 'anchors.bottomMargin:button.centeredLayout?(button.height-button.iconSize-26)/2:5')
radio=radio.replace('font.pixelSize: 15','font.pixelSize:button.labelSize')
v['/common/RadioModeButton.qml']=radio
# Child-page backdrops cover the entire display, while moving with the page.
a=s.index('id:selectionPane;');b=s.index('id:detailSwipe;',a)
part=s[a:b].replace('Rectangle {anchors.fill:parent;color:"black"}', 'Rectangle {objectName:"SelectionBackdrop";x:-16;y:-4;width:640;height:parent.height+4;color:"black"}')
part=part.replace('font.pixelSize: 27; font.family: page.fontName','font.pixelSize: 36; font.family: page.fontName')
part=part.replace('rowSpacing: 7; columnSpacing: 10','rowSpacing: 8; columnSpacing: 10')
part=part.replace('width: 136; height: 54','width: 136; height: 60')
part=part.replace('y: 8; width: 7; height: 38','y: 10; width: 7; height: 40')
s=s[:a]+part+s[b:]
s=s.replace('Rectangle {anchors.fill:parent;color:"black";z:-1}', 'Rectangle {objectName:"DetailBackdrop";x:-16;y:-4;width:640;height:parent.height+4;color:"black";z:-1}')
marker='            visible: page.screen==="wireless"\n            FlashText'
assert marker in s
s=s.replace(marker, '            visible: page.screen==="wireless"\n            Rectangle {objectName:"WirelessBackdrop";x:-16;y:-4;width:640;height:480-parent.y+4;color:"black";z:-1}\n            FlashText',1)
s=s.replace('        Flickable {\n            id:settingsList;', '        Rectangle {objectName:"SettingsBackdrop";x:settingsList.x-16;y:6;width:640;height:parent.height-6;color:"black";visible:settingsList.visible}\n        Flickable {\n            id:settingsList;',1)
s=s.replace('y: 82; width: 640; height: 1; color: "#555"; opacity: 1; visible: page.screen!=="wireless"', 'y: 81; width: 640; height: 1; color: "#555"; opacity: 1')
s=s.replace('y: 397; width: 640; height: 1; color: "#555"; opacity: 1; visible: page.screen!=="settings" && page.screen!=="selection" && page.screen!=="power"', 'y: 396; width: 640; height: 1; color: "#555"; opacity: 1; visible:page.screen==="groups"')
s=s.replace('text: page.errorText; visible: text.length>0;', 'text: page.errorText; visible: text.length>0 && page.screen==="groups";')
# A one-pixel optical adjustment requested after the preceding camera trial.
s=s.replace('x: 344; y: 0; spacing: 8; height: 82','x: 344; y: -1; spacing: 8; height: 82')
s=s.replace('x: 60; y: 0; width: 280; height: 82','x: 60; y: -1; width: 280; height: 82')
s=s.replace('"FlashMaster"; x: 492; y: 0;', '"FlashMaster"; x: 492; y: -1;')
s=s.replace('x: 574; y: 25;', 'x: 574; y: 24;')
v['/controlscreen/FlashStyle.qml']=v['/controlscreen/FlashStyle.qml'].replace('footerTop: 398','footerTop: 397')
# Do not count a trailing gutter as part of the last visible cell. Each
# divider-to-divider (or display-edge) footer cell is exactly 100 pixels.
s=s.replace('model:[327,427,527]', 'model:[340,440,540]')
for name, old, new in [('FlashTest',327,340),('FlashChooseGroups',427,440),('FlashSettings',527,540)]:
    s=s.replace('"'+name+'"; x: '+str(old)+';', '"'+name+'"; x: '+str(new)+';')
s=s.replace('x: 13; y: flashStyle.footerTop; width: 314;', 'x: 0; y: flashStyle.footerTop; width: 340;')
a=s.index('id: groupList;');b=s.index('id:selectionSwipe',a)
part=s[a:b].replace('y: flashStyle.contentTop;', 'y: 82;')
part=part.replace('page.screen==="groups" ? 304', 'page.screen==="groups" ? 314')
part=part.replace('width: 640; height: 76', 'width: 640; height: 78.5')
part=part.replace('Math.round(contentY/76)*76', 'Math.round(contentY/78.5)*78.5')
s=s[:a]+part+s[b:]
v['/controlscreen/FlashPage.qml']=s
assert 'width: 640; height: 78.5' in s
old_arrow='Image { anchors.centerIn: parent; width: 22; height: 20; source: page.iconBase+"EVF_ArrowRight.png"; fillMode: Image.PreserveAspectFit }'
assert old_arrow in s
s=s.replace(old_arrow, '''Canvas {objectName:"FlashDetailChevron";anchors.centerIn:parent;width:24;height:40
    onPaint:{var c=getContext("2d");c.clearRect(0,0,width,height);c.strokeStyle="white";c.lineWidth=4;c.lineCap="square";c.lineJoin="miter";c.beginPath();c.moveTo(3,3);c.lineTo(20,20);c.lineTo(3,37);c.stroke()}
}''')
v['/controlscreen/FlashPage.qml']=s
assert all(t in s for t in ['FlashExposureSummary','FlashTest','FlashChooseGroups','FlashSettings','page.syncText','page.shutterText'])
# Every navigation chevron uses one shape and one visual size.
import re
s=s.replace('import QtQuick 2.5','import QtQuick 2.5\nimport "qrc:/components" as HblUi',1)
if 'import "qrc:/components" as HblUi' not in s:
    s='import "qrc:/components" as HblUi\n'+s
s=re.sub(r'Canvas \{anchors.centerIn:parent;width:24;height:40\s+onPaint:\{[^\n]+\}\s*\}', 'HblUi.NavigationChevron {anchors.centerIn:parent}',s)
s=re.sub(r'Canvas \{objectName:"FlashDetailChevron";anchors.centerIn:parent;width:24;height:40\s+onPaint:\{[^\n]+\}\s*\}', 'HblUi.NavigationChevron {objectName:"FlashDetailChevron";anchors.centerIn:parent;forward:true}',s)
v['/controlscreen/FlashPage.qml']=s
v['/components/NavigationChevron.qml']=(P/'NavigationChevron.qml').read_text(encoding='utf-8')
v['/controlscreen/FlashText.qml']=v['/controlscreen/FlashText.qml'].replace('    font.weight: Font.Normal\n','')
s=s.replace('property string fontName: "Helvetica Neue LT Std"','Text {id:menuFontReference;visible:false}\n    property string fontName: menuFontReference.font.family')
a=s.index('id: groupList;');b=s.index('id:selectionSwipe',a)
part=s[a:b].replace('font.pixelSize: flashStyle.secondarySize+2','font.pixelSize: 32').replace('font.pixelSize: flashStyle.groupSize+4','font.pixelSize: 32')
s=s[:a]+part+s[b:]
v['/controlscreen/FlashPage.qml']=s
header_start=s.index('x: 344; y: -1; spacing: 8; height: 82')
header_end=s.index('        RadioModeButton {',header_start)
header=s[header_start:header_end].replace('FlashValueText {','FlashHeaderText {').replace('font.weight: Font.Light','font.weight: menuFontReference.font.weight')
s=s[:header_start]+header+s[header_end:]
v['/controlscreen/FlashPage.qml']=s
v['/controlscreen/FlashHeaderText.qml']=(P/'FlashHeaderText.qml').read_text(encoding='utf-8')
v['/controlscreen/ExposureRuler.qml']=(P/'ExposureRuler.qml').read_text(encoding='utf-8')
v['/settings/components/SettingsChoicePopup.qml']=(P/'SettingsChoicePopup.qml').read_text(encoding='utf-8')
v['/components/controls/OwnParameterSelector.qml']=(P/'OwnParameterSelector.qml').read_text(encoding='utf-8')
control=v['/controlscreen/ControlScreen.qml']
assert control.count('PopupListSelector {')==3
v['/controlscreen/ControlScreen.qml']=control.replace('PopupListSelector {','OwnParameterSelector {')
v['/settings/components/ListSelectorSettings.qml']='import QtQuick 2.5\nSettingsChoicePopup {}\n'
v['/settings/components/RadioListSelector.qml']='import QtQuick 2.5\nSettingsChoicePopup {}\n'
v['/settings/components/FlashStepSelector.qml']='''import QtQuick 2.5
SettingsChoicePopup {
    viewfinderChoices:["0.3 EV","0.1 EV"]
    signal stepSelected(bool thirds)
    function saveViewfinder(text){var i=viewfinderChoices.indexOf(text);if(i>=0)stepSelected(i===0)}
}
'''
s=s.replace('objectName:"FlashBack";x:4;y:8;width:60;height:56','objectName:"FlashBack";x:4;y:-1;width:60;height:82')
s=s.replace('enabled:!selectionSwipe.drag.active;NumberAnimation','enabled:!selectionSwipe.drag.active && !selectionBlankSwipe.pressed;NumberAnimation')
pos=s.index('        MouseArea {\n            id:detailSwipe;')
s=s[:pos]+'''        MouseArea {
            id:selectionBlankSwipe;objectName:"SelectionBlankSwipe"
            x:0;y:390;width:parent.width;height:parent.height-y;z:3
            enabled:page.screen==="selection";visible:enabled;preventStealing:true
            property real pressX:0;property real pressY:0;property bool horizontal:false
            onPressed:{pressX=mouse.x;pressY=mouse.y;horizontal=false}
            onPositionChanged:if(pressed){
                var dx=mouse.x-pressX,dy=mouse.y-pressY
                if(!horizontal && dx>constants.dragThreshold && dx>Math.abs(dy)*1.5)horizontal=true
                if(horizontal)selectionPane.x=flashStyle.pageInset+Math.max(0,dx)
            }
            onReleased:{
                if(horizontal && selectionPane.x>flashStyle.pageInset+640/constants.swipeLengthDividor){page.requestBack();selectionPane.x=flashStyle.pageInset+640}
                else selectionPane.x=flashStyle.pageInset
                horizontal=false
            }
            onCanceled:{selectionPane.x=flashStyle.pageInset;horizontal=false}
        }
'''+s[pos:]
v['/controlscreen/FlashPage.qml']=s
# User trial: increase the shared 32px text tier by two steps everywhere in
# Match the accepted custom settings release curve, independent of firmware
# menu duration (which differs from the custom page's fixed 200 ms).
v['/controlscreen/FlashPage.qml']=v['/controlscreen/FlashPage.qml'].replace('duration:constants.menuSwipeDuration;easing.type:Easing.InOutQuad','duration:200;easing.type:Easing.OutCubic').replace('duration:constants.menuSwipeDuration;easing.type:Easing.OutCubic','duration:200;easing.type:Easing.OutCubic')
# flash UI, matching the menu/settings tier; descriptions retain their size.
for path in list(v):
    if path.startswith('/controlscreen/Flash') and path.endswith('.qml'):
        v[path]=re.sub(r'(font\.pixelSize:\s*)32\b',r'\g<1>36',v[path])
        v[path]=v[path].replace('index===9 || index===11 ? 24 : 32','index===9 || index===11 ? 24 : 36')
s=v['/controlscreen/FlashPage.qml']
# Passive diagnostics: no synthetic touch or camera action. Record only the
from flash_release import apply_flash_release
s=apply_flash_release(s)
s=s.replace('model:[340,412,492,568]','model:[340,492,568]')
s=s.replace('x: 344; y: -1; spacing: 8; height: 82','x: 344; y: -1; spacing: 4; height: 82')
s=s.replace('width: 64; height: parent.height','width: 72; height: parent.height')
s=s.replace('objectName: "FlashBatterySlot"; x: 574; y: 24; width: 50; height: 32',
            'objectName: "FlashBatterySlot"; x: 568; y: -1; width: 64; height: 82')
s=s.replace('height: 30\n                source: page.batterySource','height: 59\n                source: page.batterySource')
s=s.replace('item.batteryWidth=19\n                    item.lineWidth=2.5\n                    item.sizeFactor=19/23',
            'item.batteryWidth=23\n                    item.lineWidth=3\n                    item.sizeFactor=1')
v['/controlscreen/FlashPage.qml']=s
# gesture eligibility flags when the user presses, never image coordinates.
live=v['/liveview/LiveViewOverlay.qml']
marker='    function pickFocusPoint(px, py) {'
assert live.count(marker)==1
live=live.replace(marker,'''    function reportFocusTouchState() {
        console.log("FocusTouch eligibility", root.inActiveWindow,
            GlobalStateInfo.evfActive, root.isInHDMI, GlobalStateInfo.afSelectionActive,
            VideoControl.videoMode === VideoControl.View,
            directFocusGrid.afItemWidth > 0 && directFocusGrid.afItemHeight > 0)
    }
'''+marker,1)
v['/liveview/LiveViewOverlay.qml']=live
live=v['/liveview/LiveViewImage.qml']
assert live.count('onPressed: info.startZoomTimer()')==1
live=live.replace('onPressed: info.startZoomTimer()',
    'onPressed: {info.reportFocusTouchState();info.startZoomTimer()}',1)
v['/liveview/LiveViewImage.qml']=live
pad=v['/liveview/Touchpad.qml']
assert '    function beginFocusDrag() {' in pad
pad=pad.replace('    function beginFocusDrag() {','''    property bool focusDragHeld: false
    function finishFocusDrag() {
        if (focusDragHeld) GlobalStateInfo.focusDelivery.endDrag()
        focusDragHeld = false
    }
    onCanceled: {finishFocusDrag();wasInTouchArea=false;GlobalStateInfo.touchpadZoomActive=false}
    onEnabledChanged: if (!enabled) finishFocusDrag()
    onInFocusModeChanged: if (!inFocusMode) finishFocusDrag()
    Component.onDestruction: finishFocusDrag()
    function beginFocusDrag() {
        if (inFocusMode && !focusDragHeld) {
            GlobalStateInfo.focusDelivery.beginDrag()
            focusDragHeld = true
        }''',1)
pad=pad.replace('    onReleased: {','    onReleased: {\n        finishFocusDrag()\n        wasInTouchArea = false',1)
from evf_touch_owner import apply_touch_owner
pad=apply_touch_owner(pad)
if '--native-touch' in sys.argv:
    from native_touch import apply_native_touch
    pad=apply_native_touch(pad)
v['/liveview/Touchpad.qml']=pad
from parameter_popovers import apply_parameter_popovers
apply_parameter_popovers(v,P)
from parameter_residency import apply_parameter_residency
apply_parameter_residency(v,P)
from raw_replay_recovery import apply_raw_replay_recovery
apply_raw_replay_recovery(v,P)
v['/common/FocusDelivery.qml']=(P.parents[1]/'combined-runtime/four-module-r1/persistent-r1/qml/common/FocusDelivery.qml').read_text(encoding='utf-8')
if '--native-focus' in sys.argv:
    v['/common/FocusDelivery.qml']=(P/'NativeFocusDelivery.qml').read_text(encoding='utf-8')
from focus_indicator_motion import apply_focus_indicator_motion
v['/liveview/AFIndicator.qml']=apply_focus_indicator_motion(v['/liveview/AFIndicator.qml'])
live=v['/liveview/LiveViewImage.qml']
assert 'onPressed: {info.reportFocusTouchState();info.startZoomTimer()}' in live and 'onReleased: info.startZoomTimer()' in live
live=live.replace('onPressed: {info.reportFocusTouchState();info.startZoomTimer()}', 'onPressed: {GlobalStateInfo.focusDelivery.beginDrag();info.reportFocusTouchState();info.startZoomTimer()}')
live=live.replace('onReleased: info.startZoomTimer()', 'onReleased: {GlobalStateInfo.focusDelivery.endDrag();info.startZoomTimer()}\n        onCanceled: GlobalStateInfo.focusDelivery.endDrag()')
v['/liveview/LiveViewImage.qml']=live
enable_viewfinder='--enable-own-viewfinder' in sys.argv
if enable_viewfinder:
    from viewfinder_ui import apply_viewfinder_ui
    apply_viewfinder_ui(v,P)
enable_replay='--enable-replay' in sys.argv
lock_format=enable_replay or '--lock-format' in sys.argv
if enable_replay:
    from replay_routes import apply_replay_routes,apply_evf_replay
    v['/common/TouchWindow.qml']=apply_replay_routes(v['/common/TouchWindow.qml'])
    apply_evf_replay(v)
    for name in ['NativePhotoPlayback.qml','PhotoPlaybackPage.qml','JpegPlaybackSurface.qml','CaptureIdentity.js']:
        v['/components/'+name]=(P/name).read_text(encoding='utf-8')
if lock_format:
    v['/settings/NativeSettingsPage.qml']=v['/settings/NativeSettingsPage.qml'].replace('property bool formatLocked:false','property bool formatLocked:true')
    touch=v['/common/TouchWindow.qml'];pos=touch.rfind('}')
    v['/common/TouchWindow.qml']=touch[:pos]+'\n    Loader {source:"qrc:///settings/CaptureFormatPolicy.qml"}\n'+touch[pos:]
sealed_qml='--sealed-qml' in sys.argv
experimental_network='--experimental-network' in sys.argv
native_flash='--native-flash' in sys.argv
if native_flash:
    from native_flash import apply_native_flash
    v['/controlscreen/FlashPage.qml']=apply_native_flash(v['/controlscreen/FlashPage.qml'])
native_page_pool='--native-page-pool' in sys.argv
if native_page_pool:
    from native_page_pool import apply_native_page_pool
    v['/mainmenu/PagePool.qml']=apply_native_page_pool(v['/mainmenu/PagePool.qml'])
native_settings='--native-settings-rules' in sys.argv
if native_settings:
    from native_settings_rules import apply_native_settings_adapter,apply_native_settings_page
    v['/settings/NativeSettingsPage.qml']=apply_native_settings_adapter(v['/settings/NativeSettingsPage.qml'])
    v['/settings/SettingsPage.qml']=apply_native_settings_page(v['/settings/SettingsPage.qml'])
if sealed_qml and experimental_network:
    for name in ['Main.qml','Entry.qml']:
        v['/hblprotected/network/'+name]=(P/name).read_text(encoding='utf-8')
blob=rcc(v);assert read_rcc(blob)==v
(P/'build/flash-ui.rcc').write_bytes(blob)
import json
(P/'build/ui-features.json').write_text(json.dumps({'newReplayEnabled':enable_replay,'ownViewfinderEnabled':enable_viewfinder,'formatLockEnabled':lock_format,'nativeFocusCore':'--native-focus' in sys.argv,'nativeTouchCore':'--native-touch' in sys.argv,'nativeFlashCore':native_flash,'nativePagePoolCore':native_page_pool,'nativeSettingsRules':native_settings,'sealedQml':sealed_qml,'experimentalNetwork':experimental_network}),encoding='utf-8')
(P/'build/flash-source/FlashPage.qml').write_text(v['/controlscreen/FlashPage.qml'],encoding='utf-8')
(P/'build/flash-source/FlashText.qml').write_text(v['/controlscreen/FlashText.qml'],encoding='utf-8')
(P/'build/flash-source/FlashStyle.qml').write_text(v['/controlscreen/FlashStyle.qml'],encoding='utf-8')
(P/'build/flash-source/FlashIconButton.qml').write_text(v['/controlscreen/FlashIconButton.qml'],encoding='utf-8')
(P/'build/flash-source/RadioModeButton.qml').write_text(v['/common/RadioModeButton.qml'],encoding='utf-8')
print('RAM candidate built and round-trip verified: direct main menu, merged focus settings, flash layout and gestures')
