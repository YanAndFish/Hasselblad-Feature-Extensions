import QtQuick 2.0
import com.hasselblad.video 1.0
import com.hasselblad.farm 1.0
import com.hasselblad.systemmanager 1.0

import "qrc:///components"
import "qrc:///settings"   // TODO: For Photo, maybe that component shall be moved to components on the top level?


Item {
    id: video_overlay
    property bool lifecycleCurrent: false
    visible: true
    anchors.fill: parent
    property bool loadImage: false
    property int fileIndex
    property string fileName
    property int fileSize
    property int metaVolumeType
    property string metaDateTime
    property string metaImgName
    property bool ramOnly: farm.ram_only_mode === Farm.RamModeRamOnly
    property bool isTethered: System.isTethered

    Rectangle {
        id: videoTop
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
        }
        height: constants.botMetaHeightSimple
        color: "black"

        Rectangle {
            id: volumeBack
            color: ramOnly ? "red" : "transparent"
            border.color: "white"
            border.width: 2
            visible: videoTop.visible || ramOnly
            width: ramOnly ? 450: 40
            anchors {
                top: videoTop.top
                left: videoTop.left
                bottom: videoTop.bottom
                topMargin: 4
                leftMargin: constants.metaDataMargins
                bottomMargin: 4
            }
        }

        Text {
            id: cardSymbol
            color: "white"
            anchors {
                fill: volumeBack
                topMargin: ramOnly && guiconfig.usingUnicodeLanguage ? 0 : constants.metaDataVertOffset + 2
                leftMargin: 2
                rightMargin: 2
            }
            // TODO: Here fix the CARD type & slot preferably with an image instead of text.
            text: ramOnly ? qsTr("DEMO - NO STORAGE").toUpperCase() + guiconfig.emptyString : volumeSymbol(metaVolumeType)
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            fontSizeMode: Text.Fit
            font.pixelSize: constants.mediaBrowseFontSize
            font.bold: ramOnly && !guiconfig.usingUnicodeLanguage
            font.family: ramOnly && guiconfig.usingUnicodeLanguage ? "DroidSansFallback" : constants.dialogTextFontName
        }

        Text {
            id: imgName
            color: "white"
            font.pixelSize: constants.mediaBrowseFontSize
            visible: !ramOnly
            font.family: constants.metaDataTextFontName
            anchors {
                left: volumeBack.right
                right: imgDate.left
                verticalCenter: videoTop.verticalCenter
                verticalCenterOffset: constants.metaDataVertOffset
                leftMargin: constants.metaDataMargins / 2
                rightMargin: constants.metaDataMargins
            }
            elide: Text.ElideRight
            // TODO: Here fix the CARD type+ slot preferably with an image instead of text.
            text: metaImgName.replace(/\.[^/.]+$/, "") // This regex cuts off the file extension from the picture name!
        }

        Text {
            id: imgDate
            color: "white"
            visible: !ramOnly
            font.pixelSize:  constants.mediaBrowseFontSize
            font.family: constants.metaDataTextFontName
            anchors {
                right: imgTime.left
                verticalCenter: videoTop.verticalCenter
                verticalCenterOffset: constants.metaDataVertOffset
                leftMargin: constants.metaDataMargins
                rightMargin: 65 /*constants.metaDataMargins*/
            }
            text: metaDateTime.length ? metaDateTime.split('T')[0].slice(2) : "" // Cutting off the thousands in the year!
        }

        Text {
            id: imgTime
            color: "white"
            font.pixelSize:  constants.mediaBrowseFontSize
            font.family: constants.metaDataTextFontName
            anchors {
                right: videoTop.right
                verticalCenter: videoTop.verticalCenter
                verticalCenterOffset: constants.metaDataVertOffset
                rightMargin: constants.metaDataMargins
            }
            text: metaDateTime.length ? metaDateTime.split('T')[1] : ""
        }
    }


    Rectangle {
        id: videoBottom
        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        height: constants.botMetaHeightSimple
        color: "black"

        Text {
            text: ((VideoControl.position / 60) < 10 ? "0" : "") + Math.floor((VideoControl.position / 60)) + ":" +
                  ((VideoControl.position % 60) < 10 ? "0" : "") + Math.round((VideoControl.position % 60))
            color: "white"
            font.pixelSize: constants.mediaBrowseFontSize
            anchors {
                verticalCenter: parent.verticalCenter
                verticalCenterOffset: 4
                left: parent.left
                leftMargin: constants.metaDataMargins
            }
            horizontalAlignment: Text.AlignLeft
        }
        Text {
            // TODO: Set total time of video here
            text: ((VideoControl.duration / 60) < 10 ? "0" : "") + Math.floor((VideoControl.duration / 60)) + ":" +
                  ((VideoControl.duration % 60) < 10 ? "0" : "") + Math.round((VideoControl.duration % 60))
            color: "white"
            font.pixelSize: constants.mediaBrowseFontSize
            anchors {
                verticalCenter: parent.verticalCenter
                verticalCenterOffset: 4
                right: parent.right
                rightMargin: constants.metaDataMargins
            }
            horizontalAlignment: Text.AlignRight
        }

        // A progressbar
        ProgressBar {
            anchors.centerIn: parent
            width: 380
            height: 20
            percentageAnimDelay: VideoControl.position === 0 ? 0 : 1
            progressPercent: VideoControl.duration === 0 ? 0 : VideoControl.position / (VideoControl.duration - 1)
        }

    }

    ResidentBrowsePhoto {
        lifecycleCurrent: video_overlay.lifecycleCurrent
        id: preview
        visible: VideoControl.videoMode !== VideoControl.Playback && video_overlay.loadImage && status !== Image.Error
        anchors.fill: parent

        fillMode: Image.PreserveAspectFit
        source: lifecycleCurrent && video_overlay.loadImage ? image : ""

        onStatusChanged: {
            if (status === Image.Ready) {
                list_delegate.loaded()
            }
        }
    }

    // Video placeholder
    Rectangle {
        visible: VideoControl.videoMode !== VideoControl.Playback && !preview.visible
        color: "darkgrey"
        anchors {
            top: videoTop.bottom
            bottom: videoBottom.top
            left: parent.left
            right: parent.right
        }
    }

    Image {
        source: "qrc:///icons/Video_play_large.png"
        anchors.centerIn: parent
        visible: VideoControl.videoMode !== VideoControl.Playback
    }

//    Image{
//        source: "qrc:///icons/PlaybackPause.png"
//        anchors.centerIn: parent
//        // TODO: I have no idea what property to use, so correct this when that is more clear:
//        visible: VideoControl.videoMode === VideoControl.Playback && VideoControl.position !== 0
//    }

    function volumeSymbol(index)
    {
        // Tethered mode overrides any storage volume.
        if(isTethered)
            return "USB"
        return guiconfig.storageSlotLetter(index)
    }

}
