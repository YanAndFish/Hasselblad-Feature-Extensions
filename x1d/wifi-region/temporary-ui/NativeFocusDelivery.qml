import QtQuick 2.0
import com.hasselblad.camera 1.0
QtObject {
    id: delivery
    readonly property var core: _hblFocusCore
    readonly property bool active: core.v[3]
    readonly property bool dragging: core.v[2]
    readonly property real displayed: core.v[0]
    readonly property bool pending: core.v[1]
    property var actions: []
    readonly property int writes: core.e0
    readonly property int completions: core.e1
    readonly property int failures: core.e2
    function request(operation,value) {core.request=[operation,value===undefined?0:value]}
    function beginDrag() {request(1)}
    function endDrag() {request(2)}
    function select(point) {request(3,point)}
    function pump() {request(5)}
    function accept(point) {request(0,point)}
    function abortDelivery() {actions=[];request(6)}
    function afterCoordinates(kind,action) {
        if(!active){action();return}
        var next=actions.slice(0);next.push({kind:kind,run:action});actions=next
        request(7)
    }
    function cancel(kind) {
        var next=[]
        for(var i=0;i<actions.length;++i)if(actions[i].kind!==kind)next.push(actions[i])
        actions=next
    }
    onWritesChanged: Camera.focus_point=core.p
    onCompletionsChanged: {
        var ready=actions;actions=[]
        for(var i=0;i<ready.length;++i)ready[i].run()
    }
    onFailuresChanged: actions=[]
    Component.onCompleted: accept(Camera.focus_point)
    property Connections feedback: Connections {
        target: Camera
        onFocus_pointChanged: delivery.accept(Camera.focus_point)
    }
}
