import QtQuick 2.5
import com.hasselblad.camera 1.0
import com.hasselblad.bodysync 1.0
import "qrc:///scripts/Keys.js" as MKeys

FocusScope {
    id:root;anchors.fill:parent;z:100
    property Item returnToItem:null
    property bool preloadOnly:false
    property int selectedRow:0
    readonly property var options: {
        var result=[]
        if(Camera.canChange & Camera.PropFlashEVADJ)result.push({key:"FLASH_EVADJ",limit:36,step:4,icon:"Flash_adjust_for_popup.png"})
        if(Camera.canChange & Camera.PropEVADJ)result.push({key:"EVADJ",limit:60,step:Math.max(1,configstore.CustomOption_AdjStepsInc),icon:"Exposure_adjust_for_popup.png"})
        return result
    }
    function open(caller){returnToItem=caller;visible=true;forceActiveFocus();BodySync.currentState=BodySync.MENU}
    function close(){visible=false;focus=false;BodySync.currentState=BodySync.MAIN;if(returnToItem)returnToItem.forceActiveFocus()}
    function adjust(index,direction){if(index>=0 && index<sliders.count)sliders.itemAt(index).commit(sliders.itemAt(index).displayed+direction*options[index].step)}
    function present(){open(null)}
    Component.onCompleted:if(preloadOnly)visible=false;else present()
    Rectangle {anchors.fill:parent;color:constants.popupFadeoutColor;opacity:constants.fadeOutOpacity}
    MouseArea {anchors.fill:parent;onClicked:root.close()}
    Rectangle {
        x:69;y:69;width:parent.width-138;height:parent.height-138
        color:constants.popupBackgroundColor;radius:constants.outerBoxRadius
        border.width:2;border.color:constants.popupBorderColor
        MouseArea {anchors.fill:parent}
        Text {x:12;y:20;width:parent.width-24;text:qsTranslate("PopupExposureAdjust","EXPOSURE ADJUST")+guiconfig.emptyString;color:"white";font.pixelSize:28;horizontalAlignment:Text.AlignHCenter}
        Repeater {
            id:sliders;model:root.options
            delegate:Item {
                id:row;objectName:"OwnExposureSlider"+index
                x:20;y:72+index*126;width:parent.width-40;height:116
                property var option:modelData
                property real requested:0
                property bool pending:false
                readonly property real actual:Number(Camera[option.key])
                readonly property real displayed:touch.pressed || pending?requested:actual
                onActualChanged:if(Math.abs(actual-requested)<0.01)pending=false
                function commit(value){
                    requested=Math.max(-option.limit,Math.min(option.limit,Math.round(value/option.step)*option.step))
                    pending=true;ackDeadline.restart();Camera[option.key]=requested
                    if(actual===requested)pending=false
                }
                Timer {id:ackDeadline;interval:1500;onTriggered:row.pending=false}
                Image {x:0;y:0;source:"qrc:///icons/"+row.option.icon;fillMode:Image.PreserveAspectFit;width:44;height:36}
                Text {x:60;y:0;width:parent.width-60;text:(row.displayed>0?"+":"")+(row.displayed/12).toFixed(1);color:"white";font.pixelSize:36;horizontalAlignment:Text.AlignRight}
                Rectangle {x:0;y:49;width:parent.width;height:55;color:index===root.selectedRow?constants.highlightColor:"transparent"}
                Rectangle {x:16;y:76;width:parent.width-32;height:2;color:"white"}
                Repeater {model:row.option.limit/6+1;Rectangle {x:16+index*(row.width-32)/(row.option.limit/6);y:69;width:1;height:15;color:"white"}}
                Rectangle {x:16+(row.displayed+row.option.limit)/(2*row.option.limit)*(parent.width-32)-3;y:60;width:6;height:34;color:"white";border.color:"black";border.width:1}
                MouseArea {
                    id:touch;anchors.fill:parent;preventStealing:true
                    function move(position){row.commit(((Math.max(16,Math.min(row.width-16,position))-16)/(row.width-32)*2-1)*row.option.limit)}
                    onPressed:{root.selectedRow=index;move(mouse.x)}
                    onPositionChanged:if(pressed)move(mouse.x)
                }
            }
        }
    }
    Keys.onPressed:{
        event.accepted=true
        if(MKeys.pressedFn("ESCAPE",event.key)||MKeys.pressedFn("MENU",event.key)||MKeys.pressedFn("BROWSE",event.key))close()
        else if(MKeys.pressedFn("SELECT",event.key)){if(selectedRow+1<options.length)selectedRow++;else close()}
        else if(MKeys.pressedFn("LEFT",event.key))adjust(0,-1)
        else if(MKeys.pressedFn("RIGHT",event.key))adjust(0,1)
        else if(MKeys.pressedFn("UP",event.key))adjust(1,-1)
        else if(MKeys.pressedFn("DOWN",event.key))adjust(1,1)
        else if(MKeys.pressedFn("NAVLEFT",event.key))adjust(selectedRow,-1)
        else if(MKeys.pressedFn("NAVRIGHT",event.key))adjust(selectedRow,1)
        else event.accepted=false
    }
}
