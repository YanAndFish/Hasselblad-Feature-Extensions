    // 本会话一次性的活动保持；健康已醒时仅发原厂活动通知，不改待机设置。
    Timer {
        id: replayInstallHoldTimer
        interval: 500; repeat: true; triggeredOnStart: true
        running: typeof x1dReplaySession!=="undefined" && x1dReplaySession.installationHold
        onTriggered: {
            var healthy = System.system_state===System.StateUp && ErrorControl.code===Errors.ErrorNone &&
                          mainWindow.status===Loader.Ready && mainWindow.item && !mainWindow.item.sleeping &&
                          control.state!=="sleeping" && !Camera.inSession && !Camera.exposing
            if (healthy) mainWindow.item.idleWakeupOrForceOff(true)
            x1dReplaySession.installPulse = !!healthy
        }
    }
