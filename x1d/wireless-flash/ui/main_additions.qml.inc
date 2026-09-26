
    // Experimental wireless flash: all settings are session-local.
    property bool hblRfEnabled: typeof hblNative !== "undefined" && hblNative.enabled
    property int hblRfDelayMs: hblRfAvailable ? hblNative.delayMs : 0
    property int hblRfSource: hblRfAvailable ? hblNative.source : 0
    property int hblRfProgress: hblRfAvailable ? hblNative.progressThreshold : 0
    property int hblRfStepMs: 10
    property int hblRfPowerIndex: hblRfAvailable ? hblNative.powerIndex : 10
    property bool hblRfAvailable: typeof hblNative !== "undefined"
    property bool hblRfBusy: hblRfAvailable && hblNative.radioBusy
    property bool hblRfReady: hblRfAvailable && hblNative.radioReady
    property string hblRfStatus: hblRfAvailable ? hblNative.status : "等待机内事件接入"
    signal hblRfConfigurationChanged()
    function hblRfConfigure(on, delay, source, progress) {
        source = 0; delay = 0; progress = 0;
        if (!hblRfAvailable) {
            hblRfConfigurationChanged();
            return !on;
        }
        hblNative.command = "configure " + (on ? "1" : "0") + " " + source + " " + delay + " " + progress;
        hblRfConfigurationChanged();
        return hblRfEnabled === on;
    }
    function hblRfTestOnce() {
        if (hblRfAvailable) hblNative.command = "test";
    }
    function hblRfPrepare() {
        if (hblRfAvailable) hblNative.command = "prepare";
    }
    function hblRfPageClosed() {
        if (hblRfAvailable) hblNative.command = "pageclosed";
    }
    function hblRfSetPower(index) {
        if (hblRfAvailable && index >= 10 && index <= 100 && Math.floor(index) === index)
            hblNative.command = "power " + index;
    }
    function hblRfCount(name) {
        return hblRfAvailable ? hblNative[name] : 0;
    }
    function hblRfCancel() {
        if (hblRfAvailable) hblNative.command = "cancel";
    }
    Component.onDestruction: hblRfCancel()
