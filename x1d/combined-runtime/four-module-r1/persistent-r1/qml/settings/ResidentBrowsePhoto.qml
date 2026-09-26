import QtQuick 2.0
import com.hasselblad.demostate 1.0
import com.hasselblad.storage 1.0

import "qrc:///settings"
import "qrc:///liveview"

Image {
    id: img
    property bool lifecycleCurrent: false
    //fillMode: Image.PreserveAspectFit
    //clip: true
    asynchronous: true
    cache: false
    property bool showOverExposureMask: false

    Connections {
        target: img.lifecycleCurrent ? ContentModel : null
        onIsBrowsingPossibleChanged: {
            if (img.status === Image.Error) {
                console.log("Will try reload", img.source)
                var src = img.source
                img.source = ""
                img.source = src
            }
        }
    }

    onStatusChanged: {
        console.log("Photo status: ", status)
        if (status === Image.Error)
            console.log("Failed to load texture", img.source, "download possible:", ContentModel.isBrowsingPossible)
    }

    Rectangle {
        id: rectangle
        visible: false
        anchors.fill: parent

        Text {
            id: text
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 65
            color: "white"
            font.pixelSize: constants.mediaBrowseFontSize
            font.family: constants.metaDataTextFontName
        }
    }

    states: [
        State {
            name: "failure"
            when: img.status === Image.Error && ContentModel.isBrowsingPossible
            PropertyChanges { target: rectangle; color: "black"; visible: true }
            PropertyChanges { target: exp_effect; visible: false }
            PropertyChanges { target: text; text: qsTr("Busy - Can not show preview") + guiconfig.emptyString}
        },
        State {
            name: "loading"
            when: img.status === Image.Error && !ContentModel.isBrowsingPossible
            PropertyChanges { target: rectangle; color: "black"; visible: true }
            PropertyChanges { target: exp_effect; visible: false }
            PropertyChanges { target: text; text: qsTr("Loading...") + guiconfig.emptyString}
        },
        State {
            name: "ready"
            when: img.status === Image.Ready && ContentModel.isBrowsingPossible
            PropertyChanges { target: rectangle; visible: false }
        }
    ]

    ShaderEffect {
        id: exp_effect
        visible: img.showOverExposureMask
        blending: visible
        width: parent.width
        height: parent.height
        property variant src: img.lifecycleCurrent ? img : null

        vertexShader: "
          uniform highp mat4 qt_Matrix;
          attribute highp vec4 qt_Vertex;
          attribute highp vec2 qt_MultiTexCoord0;
          varying highp vec2 coord;
          void main() {
              coord = qt_MultiTexCoord0;
              gl_Position = qt_Matrix * qt_Vertex;
          }"
        fragmentShader: "
          varying highp vec2 coord;
          uniform sampler2D src;
          uniform lowp float qt_Opacity;
          void main() {
              lowp vec4 tex = texture2D(src, coord);
              bool overexposed = tex.r > 0.994 || tex.g > 0.994 || tex.b > 0.994;
              gl_FragColor = vec4(overexposed ? 0.0 : tex.r,
                                  overexposed ? 0.0 : tex.g,
                                  overexposed ? 0.0 : tex.b,
                                  tex.a) * qt_Opacity;
            }"
    }

    CropOverlay {
        id: cropOverlay
        anchors.fill: parent
        fixedMode: true
        cropx: (typeof cropX !== "undefined") ? cropX : 0
        cropy: (typeof cropY !== "undefined") ? cropY : 0
    }
}

