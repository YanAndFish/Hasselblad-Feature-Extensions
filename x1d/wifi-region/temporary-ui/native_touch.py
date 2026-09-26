"""将自研触点所有权和连续焦点映射换成薄适配层，保留原厂缩放接口。"""
def apply_native_touch(text):
    a=text.index('    property real continuousFocusX:')
    b=text.index('    property int padWidth:',a)
    text=text[:a]+'''    property var nativePad: _hblTouchCore
    function finishFocusDrag() {sendTouch(3,[])}
    onCanceled: {finishFocusDrag();GlobalStateInfo.touchpadZoomActive=false}
    onEnabledChanged: if(!enabled)finishFocusDrag()
    onInFocusModeChanged: if(!inFocusMode)finishFocusDrag()
    Component.onDestruction: finishFocusDrag()
'''+text[b:]
    text=text.replace('    property bool wasInTouchArea: false\n','')
    a=text.index('    function acquireTouch(points) {')
    b=text.index('    function updateZoomPosition',a)
    text=text[:a]+'''    function sendTouch(operation,points) {
        if(!nativePad)return
        var values=[]
        for(var i=0;i<points.length;i++)values.push([points[i].pointId,points[i].x,points[i].y])
        nativePad.request=[root,operation,values,[enabled,inFocusMode,inZoomMode,GlobalStateInfo.touchpadZoomActive,
            xStart,yStart,padWidth,padHeight,width,height,afc.xCount,afc.yCount,
            afc.gridXMargin,afc.gridYMargin,afc.afItemWidth,afc.afItemHeight,
            Camera.firstComponent(GlobalStateInfo.focusDelivery.displayed),Camera.secondComponent(GlobalStateInfo.focusDelivery.displayed)]]
        var r=nativePad.result
        if(r.length!==5)return
        if(r[0]&1)GlobalStateInfo.focusDelivery.beginDrag()
        if(r[0]&2)GlobalStateInfo.focusDelivery.endDrag()
        if(r[0]&4)GlobalStateInfo.touchpadZoomActive=true
        if(r[0]&8)GlobalStateInfo.touchpadZoomActive=false
        if(r[0]&16){xLastPos=r[3];yLastPos=r[4]}
        if(r[0]&32){GlobalStateInfo.afSselectedIndex=-1;GlobalStateInfo.focusDelivery.select(Camera.combine(r[1],r[2]))}
        if(r[0]&64)updateZoomPosition(r[3],r[4])
    }
    function acquireTouch(points) {sendTouch(0,points)}
    function releaseTouch(points) {sendTouch(1,points)}
    function updateTouch(points) {sendTouch(2,points)}
    onPressed: acquireTouch(touchPoints)
    onReleased: releaseTouch(touchPoints)
    onTouchUpdated: updateTouch(touchPoints)

'''+text[b:]
    return text
