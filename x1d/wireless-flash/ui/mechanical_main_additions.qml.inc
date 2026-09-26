
    // Experimental wireless flash: all settings are session-local.
    property bool hblRfEnabled: typeof hblNative !== "undefined" && hblNative.enabled
    property int hblRfDelayUs: hblRfAvailable ? hblNative.delayUs : 0
    property int hblRfSource: hblRfAvailable ? hblNative.source : 3
    property int hblRfProgress: hblRfAvailable ? hblNative.progressThreshold : 0
    property int hblRfStepUs: 10
    property var hblRfSourceDelays: [0,0,0,0,0,0,0]
    function hblRfSelectSource(source) {
        hblRfConfigure(hblRfEnabled,hblRfSourceDelays[source],source);
    }
    function hblRfAdjustDelay(delay) {
        delay=Math.max(0,Math.min(5000000,Math.round(delay/10)*10));
        var next=hblRfSourceDelays.slice(0); next[hblRfSource]=delay; hblRfSourceDelays=next;
        hblRfConfigure(hblRfEnabled,delay,hblRfSource);
    }
    property int hblRfPowerIndex: hblRfAvailable ? hblNative.powerIndex : 10
    property bool hblRfAvailable: typeof hblNative !== "undefined"
    property bool hblRfBusy: hblRfAvailable && hblNative.radioBusy
    property bool hblRfReady: hblRfAvailable && hblNative.radioReady
    property string hblRfStatus: hblRfAvailable ? hblNative.status : "等待机内事件接入"
    signal hblRfConfigurationChanged()
    function hblRfConfigure(on, delay, source, progress) {
        source = source === undefined ? hblRfSource : source;
        delay = delay === undefined ? hblRfDelayUs : delay;
        progress = 0;
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
