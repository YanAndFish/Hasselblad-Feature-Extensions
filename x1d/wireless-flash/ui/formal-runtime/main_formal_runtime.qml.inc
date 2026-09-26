    // 安装专用、原厂活动通知；不改用户待机配置、不唤醒已睡眠相机。
    Timer {
        id: formalInstallHoldTimer
        interval: 500; repeat: true; triggeredOnStart: true
        running: typeof hblNative!=="undefined" && hblNative.installationHold
        onTriggered: {
            var healthy = System.system_state===System.StateUp && ErrorControl.code===Errors.ErrorNone &&
                          mainWindow.status===Loader.Ready && mainWindow.item && !mainWindow.item.sleeping &&
                          control.state!=="sleeping" && !Camera.inSession && !Camera.exposing
            if (healthy) mainWindow.item.idleWakeupOrForceOff(true)
            hblNative.installPulse = !!healthy
        }
    }
    FormalExposureGate {
        id: formalExposureGate
        nativeAdapter: typeof hblNative!=="undefined" ? hblNative : null
        contextOwner: mainWindow.item
        electronic: configstore.eshutter
        // TV 是原厂当前曝光参数，单位 1/12 EV；传名义档位供机械策略查表。
        // 电子快门的实际调度必须取本次 FARM GFS3.exposure，禁止用此值替代。
        exposureUs: !cambody.TV_out_of_range && !cambody.isBMode && !cambody.isTMode &&
                    isFinite(cambody.TV) && cambody.TV>=-192 && cambody.TV<=168 ?
                    nominalShutterUs(cambody.TV, electronic) : 0
        function nominalShutterUs(tv, electronicMode) {
            var nominal=[8000,6250,5000,4000,3125,2500,2000,1563,1250,1000,800,625,500]
            if (tv>=84 && tv<=132 && (tv-84)%4===0) return nominal[(tv-84)/4]
            if (tv<84 || electronicMode) return Math.round(1000000*Math.pow(2,-tv/12))
            return 0
        }
        contextValid: evfWindow.status===Loader.Ready && mainWindow.status===Loader.Ready &&
                      mainWindow.item && !mainWindow.item.sleeping && control.state!=="sleeping" &&
                      System.camera_mode!==System.CameraModeVideo &&
                      System.tethered_mode!==System.TetheredModeUSBLiveView &&
                      !(guiconfig.isWedge && configstore.CustomOption_RangeExpLock &&
                       ((configstore.ExpMode===Config.ExpMode_ShutterSpeed && cambody.AV_out_of_range) ||
                        (configstore.ExpMode===Config.ExpMode_Aperture && cambody.TV_out_of_range) ||
                        (configstore.ExpMode===Config.ExpMode_Program && (cambody.TV_out_of_range || cambody.AV_out_of_range))))
        onContinueExposure: {
                    Camera.startExposing(liveviewAfterExposure)
                    if (!Camera.exposing) {
                        GlobalStateInfo.waitingForExpose = true
                    }
                    mainWindow.item.wasExposingWedge = true
                    if (GlobalStateInfo.evfActive) {
                        mainWindow.item.wasExposingInEvf = true
                    }
        }
        onCancelled: {
            if(mainWindow.item && (!configstore.selfTimerActive && !configstore.intervalActive && !configstore.bracketingActive && !configstore.focusBracketingActive))
                mainWindow.item.preventIdle(false)
        }
    }
    Connections {
        target: Camera
        onExposingChanged: if (!Camera.exposing) formalExposureGate.shotEnded()
        onInSessionChanged: if (!Camera.inSession) { formalExposureGate.cancel(); formalExposureGate.shotEnded() }
    }
    Connections {
        target: ErrorControl
        onCodeChanged: if (ErrorControl.code!==Errors.ErrorNone) { formalExposureGate.cancel(); formalExposureGate.shotEnded() }
    }
