"""引闪页业务行为回归：固定旧 QML 为 oracle，在 Qt6 离线逐事件重放。

默认命令只验证基线并输出 oracle，不代表候选通过：
    py -3.14 -B x1d/wifi-region/temporary-ui/CodeTests/flash_native_regression.py

候选可以通过 --candidate-qml 提供同接口 FlashPage.qml，可同时使用
--candidate-adapter 提供 install_context(context) 安装离线上下文桥。
独立 adapter 也可以导出 create_candidate(context)，
返回 QObject 或 QML 字符串。context 为字典，含 engine、output_dir、
baseline_source、simplify_source 和 make_component(source, label)。桥应将
QObject/PropertyMap/ctypes 回调等引用放入 context['keep_alive']，并把桥错误
追加到 context['errors']。不启动任何设备、网络、官方程序或硬件接口。

主事件只允许 set/call；case.callbacks 可在指定 signal 次数同步执行相同事件，
以及受限 signalAppend（对原始 signal 数组参数追加 JSON 值，无任意 eval）。
返回值、全部业务状态和有序业务 signals 都被比较。
候选差异默认失败；不自动更新 oracle，也不通过忽略字段掩盖差异。
输入基线固定在 build/flash-native-regression/FlashPage.baseline.qml，SHA-256
硬编码绑定本次迁移前版本；运行日志、精简组件、JSONL 和报告仅写到该目录。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import random
import re
import sys
import traceback
from typing import Any

sys.dont_write_bytecode = True
MODULE = Path(__file__).resolve().parents[1]
REPO = MODULE.parents[2]
OUTPUT = MODULE / "build/flash-native-regression"
BASELINE = OUTPUT / "FlashPage.baseline.qml"
SOURCE = MODULE / "build/flash-source/FlashPage.qml"
BASELINE_SHA256 = "5df37c37843bac7084cae31d08516141e44b1a2c9215bd1db7860dc318cb8241"
FORMAT = "hbl-flash-business-v1"
UNDEFINED = {"$type": "undefined"}

# 这些是页面/适配层的可观察业务状态；不将字体、布局和动画计时纳入业务判定。
STATE_FIELDS = [
    "pageActive", "connected", "masterEnabled", "busy", "supportedGroupCount",
    "modelingLampAvailable", "canTest", "sendPowerUpdates", "sendFlashSync",
    "powerUpdateAllowed", "flashSyncAllowed", "stateText", "errorText",
    "apertureText", "shutterSpeedText", "isoText", "channel", "wirelessId",
    "mechanicalDelays", "calibrationEditable", "calibrationOpen", "wirelessField",
    "wirelessInput", "wirelessInputFresh", "wirelessOff", "wirelessInputValid",
    "syncText", "shutterText", "hasDraftChanges", "selectedGroup", "visibleGroups",
    "visibleGroupCount", "groupScrollY", "screen", "popupOpen", "thirdStopSteps",
    "adjustmentStepText", "groupAdjustmentSteps", "groupAdjustmentTenths",
    "applyingGroupAdjustment", "powerGestureActive", "swipeSpanEv", "lampStates",
    "currentPower", "currentGroupEnabled", "hasActiveGroups", "minimumPower",
    "maximumPower",
    "regressionCanIncrease", "regressionCanDecrease",
    "regressionIncreaseChangeCount", "regressionDecreaseChangeCount",
]
TEST_FUNCTIONS = {"regressionSetModelGroup"}


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixed_baseline() -> str:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not BASELINE.exists():
        # 只允许从已知旧版复制；不会把父任务后续生成的新实现当成旧基线。
        data = SOURCE.read_bytes()
        if hashlib.sha256(data).hexdigest() != BASELINE_SHA256:
            raise RuntimeError("旧基线副本缺失且源文件已改变，拒绝建立新 oracle。")
        BASELINE.write_bytes(data)
    actual = file_hash(BASELINE)
    if actual != BASELINE_SHA256:
        raise RuntimeError(f"固定基线哈希不符：{actual}")
    save_json(OUTPUT / "baseline-manifest.json", {
        "schema": FORMAT,
        "source": "x1d/wifi-region/temporary-ui/build/flash-source/FlashPage.qml",
        "fixedCopy": "FlashPage.baseline.qml",
        "sha256": actual,
        "provenance": "父任务指定的已装包对应旧业务 QML；本测试不读取设备。",
        "hardwareRequests": 0,
    })
    return BASELINE.read_text(encoding="utf-8")


def simplify_source(source: str) -> str:
    """仅移除视觉依赖和 canvas 子树，页级业务代码保持原文。"""
    # 两个固定锚点使未知页面结构显式失败，避免宽松解析静默丢失业务函数。
    match = re.search(r"(?m)^    Item\s*\{\s*\n\s*id:\s*canvas;", source)
    if not match:
        raise ValueError("候选不是可识别的 FlashPage.qml；请用 adapter 返回精简组件。")
    prefix = source[:match.start()]
    prefix = re.sub(r"(?m)^import .*\n", "", prefix)
    prefix = prefix.replace("FlashStyle { id: flashStyle }", "QtObject { id: flashStyle; property real pageInset: 16 }")
    if "FlashStyle {" in prefix or "qrc:/components" in prefix:
        raise ValueError("业务提取仍包含外部 UI 依赖。")
    return "import QtQuick 2.5\n" + prefix + """
    // 离线测试专用布局替身；没有相机、文件、网络或无线对象。
    width: 640; height: 480
    property alias regressionScrollY: groupList.contentY
    Item { id: groupList; property real contentY: 0 }
    Item { id: detailPane }
    QtObject { id: detailSwipe; property int direction: 0 }
    // 两条真实 QML 绑定用于暴露桥的依赖丢失和 result 通知污染。
    // 只计每条绑定的变化次数，避免跨 Qt 版本的无关绑定求值顺序影响比较。
    property bool regressionBindingsReady: false
    property int regressionIncreaseChangeCount: 0
    property int regressionDecreaseChangeCount: 0
    readonly property bool regressionCanIncrease: page.canAdjustVisiblePower(1)
    readonly property bool regressionCanDecrease: page.canAdjustVisiblePower(-1)
    onRegressionCanIncreaseChanged: if (regressionBindingsReady) regressionIncreaseChangeCount++
    onRegressionCanDecreaseChanged: if (regressionBindingsReady) regressionDecreaseChangeCount++
    Component.onCompleted: regressionBindingsReady = true
    function regressionSetModelGroup(index, active, value) {
        // 直接模拟外部 ListModel 回写，刻意绕过候选 nativeFlash 入口。
        groups.setProperty(index, "active", active)
        groups.setProperty(index, "tenthStops", value)
    }
}
"""


def call(name: str, *args: Any, expect: dict | None = None) -> dict:
    event = {"op": "call", "method": name, "args": list(args)}
    if expect is not None:
        event["expect"] = expect
    return event


def set_value(name: str, value: Any, expect: dict | None = None) -> dict:
    event = {"op": "set", "property": name, "value": value}
    if expect is not None:
        event["expect"] = expect
    return event


def expected(result: Any = UNDEFINED, commands: list | None = None, **state: Any) -> dict:
    out = {"result": result}
    if commands is not None:
        out["commands"] = commands
    out.update({"state." + key: value for key, value in state.items()})
    return out


def power_change(index: int, active: bool, power: int, delivery: bool = False) -> list:
    signals = [["groupDraftChanged", index, active, power]]
    if delivery:
        signals.append(["powerUpdateRequested", index, active, power])
    return signals


def targeted_cases() -> list[dict]:
    """先写期望行为，再通过真实旧代码验证；未引用候选算法。"""
    cases = []

    def add(name: str, coverage: str, events: list[dict], callbacks: list[dict] | None = None) -> None:
        case = {"name": name, "coverage": coverage, "events": events}
        if callbacks:
            case["callbacks"] = callbacks
        cases.append(case)

    events = [set_value("selectedGroup", 0), call("setGroup", 0, True, 0, False)]
    for value in [3, 7, 10, 13, 17, 20]:
        events.append(call("adjustPower", 1, expect=expected(True, power_change(0, True, value), currentPower=value)))
    for value in [17, 13, 10, 7, 3, 0]:
        events.append(call("adjustPower", -1, expect=expected(True, power_change(0, True, value), currentPower=value)))
    events += [call("adjustPower", -1, expect=expected(True, [], currentPower=0)),
               call("adjustPower", 0, expect=expected(False, [], currentPower=0))]
    add("third-stop-sequence", "0/3/7/10 与上下边界，非法方向不产生草稿", events)

    # 手工固定合法档位表，使验证独立于候选的取整/循环实现。
    anchors = [0, 3, 7, 10, 13, 17, 20, 23, 27, 30, 33, 37, 40,
               43, 47, 50, 53, 57, 60, 63, 67, 70, 73, 77, 80]
    events = []
    for value in range(81):
        upper = next((n for n in anchors if n > value), 81)
        lower = next((n for n in reversed(anchors) if n < value), -1)
        events += [call("steppedPower", value, 1, expect=expected(upper, [])),
                   call("steppedPower", value, -1, expect=expected(lower, []))]
    events.append(call("setAdjustmentStep", False, False, expect=expected(True, [], adjustmentStepText="0.1 EV")))
    for value in range(81):
        for direction in [-1, 1]:
            events.append(call("steppedPower", value, direction, expect=expected(value + direction, [])))
    add("all-power-step-neighbours", "81 个十分之一档值切换后的相邻档，十分之一档全范围", events)

    events = [set_value("visibleGroups", [0, 2, 4]), set_value("modelingLampAvailable", True),
              call("toggleLamp", 1), call("setGroup", 0, True, 10, False),
              call("setGroup", 1, True, 32, False), call("setGroup", 2, False, 30, False),
              call("setGroup", 4, True, 60, False)]
    for step, values in enumerate([(13, 33, 63), (17, 37, 67), (20, 40, 70)], 1):
        commands = [power_change(i, a, v)[0] for i, a, v in zip([0, 2, 4], [True, False, True], values)]
        events.append(call("adjustVisiblePower", 1, expect=expected(True, commands, **{
            "groups.0": [True, values[0]], "groups.2": [False, values[1]],
            "groups.4": [True, values[2]], "groups.1": [True, 32], "lampStates.1": True,
            "groupAdjustmentSteps": step, "groupAdjustmentTenths": [3, 7, 10][step - 1],
        })))
    events += [call("setGroup", 4, True, 80, False),
               call("canAdjustVisiblePower", 1, expect=expected(False, [])),
               call("adjustVisiblePower", 1, expect=expected(False, [], **{
                   "groups.0": [True, 20], "groups.2": [False, 40], "groups.4": [True, 80],
                   "groupAdjustmentSteps": 0, "applyingGroupAdjustment": False})),
               call("setGroup", 0, True, 0, False),
               call("adjustVisiblePower", -1, expect=expected(False, [], **{
                   "groups.0": [True, 0], "groups.2": [False, 40], "groups.4": [True, 80]})),
               set_value("visibleGroups", []),
               call("adjustVisiblePower", 1, expect=expected(False, []))]
    add("batch-atomic-boundaries", "整批到边界不动，隐藏组、禁用组开关和灯状态保持", events)

    events = [set_value("visibleGroups", [0, 1]), call("setGroup", 0, True, 20, False),
              call("setGroup", 1, False, 50, False), call("adjustVisiblePower", 1),
              set_value("regressionScrollY", 180), call("toggleVisibleGroup", 5,
                  expect=expected(True, [["visibleGroupsRequested", [0, 1, 5]]],
                                  visibleGroups=[0, 1, 5], groupAdjustmentSteps=0, groupScrollY=0)),
              call("toggleVisibleGroup", 1, expect=expected(True, [["visibleGroupsRequested", [0, 5]]],
                                                         **{"groups.1": [False, 53]})),
              call("groupIsVisible", 1, expect=expected(False, [])),
              call("groupIsVisible", 5, expect=expected(True, [])),
              set_value("supportedGroupCount", 5)]
    for invalid in [-1, 1.5, 5, 16]:
        events.append(call("toggleVisibleGroup", invalid, expect=expected(False, [], visibleGroups=[0, 5])))
    add("visible-group-selection", "组别选择排序、滚动复位、支持数量与非法索引", events)

    events = [set_value("selectedGroup", 0), call("setGroup", 0, True, 40, False)]
    previous = 40
    for steps, value in [(1, 43), (2, 47), (2, 47), (1, 43), (0, 40), (-1, 37),
                         (2, 47), (300, 80), (-300, 0), (0, 40)]:
        commands = [] if value == previous else power_change(0, True, value)
        events.append(call("swipePower", 0, 40, steps, expect=expected(True, commands, currentPower=value)))
        previous = value
    events += [call("setAdjustmentStep", False, False),
               call("swipePower", 0, 40, 7, expect=expected(True, power_change(0, True, 47), currentPower=47)),
               call("swipePower", 0, 40, -7, expect=expected(True, power_change(0, True, 33), currentPower=33)),
               call("swipePower", 0, 40, 0, expect=expected(True, power_change(0, True, 40), currentPower=40)),
               call("swipePower", 0, 40, 0.5, expect=expected(False, [], currentPower=40)),
               call("toggleGroup", 0), call("swipePower", 0, 40, 3, expect=expected(False, [], currentPower=40)),
               call("quickAdjust", 0, 1, expect=expected(False, [], currentPower=40))]
    add("swipe-press-origin", "每次以按压起值计算，重复、回滑、跨边界不累计漂移", events)

    add("swipe-rejects-nonnumeric-origin", "零步拖动的 null/空字符串起值应被拒绝且不产生草稿或发送", [
        set_value("selectedGroup", 0), call("setGroup", 0, True, 40, False),
        set_value("connected", True), set_value("masterEnabled", True),
        call("swipePower", 0, None, 0, expect=expected(False, [], currentPower=40, hasDraftChanges=False)),
        call("swipePower", 0, "", 0, expect=expected(False, [], currentPower=40, hasDraftChanges=False)),
    ])

    add("visible-signal-shares-array", "visibleGroupsRequested 的原始数组参数同步 push，应共享到页面列表", [
        set_value("visibleGroups", [0, 1]),
        call("toggleVisibleGroup", 2, expect=expected(True, [["visibleGroupsRequested", [0, 1, 2]]],
             visibleGroups=[0, 1, 2, 15])),
        call("groupIsVisible", 15, expect=expected(True, [])),
        call("adjustVisiblePower", 1, expect=expected(True,
             [["groupDraftChanged", i, False, 43] for i in [0, 1, 2, 15]],
             **{"groups.15": [False, 43], "visibleGroups": [0, 1, 2, 15]})),
        call("toggleVisibleGroup", 15, expect=expected(True, [["visibleGroupsRequested", [0, 1, 2]]],
             **{"visibleGroups": [0, 1, 2], "groups.15": [False, 43]})),
    ], [{"signal": "visibleGroupsRequested", "occurrence": 1,
         "events": [{"op": "signalAppend", "argument": 0, "value": 15}]}])

    events = [call("toggleLamp", 0, expect=expected(False, [])),
              set_value("modelingLampAvailable", True), set_value("connected", True),
              set_value("masterEnabled", True), call("toggleGroup", 3,
                  expect=expected(True, power_change(3, True, 40, True), currentGroupEnabled=True)),
              call("toggleLamp", 3, expect=expected(True, [["modelingLampDraftChanged", 3, True]], **{"lampStates.3": True})),
              call("openGroup", 3, expect=expected(UNDEFINED, [], selectedGroup=3, screen="power")),
              call("toggleGroup", 3, expect=expected(True, power_change(3, False, 40, True), **{
                  "currentGroupEnabled": False, "currentPower": 40, "lampStates.3": True})),
              call("openGroup", 1, expect=expected(UNDEFINED, [], selectedGroup=1, currentPower=40)),
              set_value("supportedGroupCount", 4)]
    for invalid in [-1, 0.5, 4, 16]:
        events.append(call("toggleLamp", invalid, expect=expected(False, [])))
    add("group-and-lamp-controls", "组切换与开关保留功率，灯开关单独发草稿，能力门控", events)

    events = [call("setGroup", 15, True, 40, False)]
    for connected, master, busy, power, sync, can_test in itertools.product([False, True], repeat=6):
        events += [set_value(k, v) for k, v in [
            ("connected", connected), ("masterEnabled", master), ("busy", busy),
            ("sendPowerUpdates", power), ("sendFlashSync", sync), ("canTest", can_test)]]
        allow_power = connected and master and not busy and power
        allow_sync = connected and master and not busy and sync
        allow_test = allow_sync and can_test
        events += [call("requestPowerUpdate", 15, expect=expected(allow_power,
                        [["powerUpdateRequested", 15, True, 40]] if allow_power else [])),
                   call("requestFlashSync", expect=expected(allow_sync, [["flashSyncRequested"]] if allow_sync else [])),
                   call("requestTest", expect=expected(allow_test, [["testRequested"]] if allow_test else []))]
    events += [set_value("busy", False), call("setGroup", 15, False, 40, False),
               call("requestTest", expect=expected(False, []))]
    add("delivery-gate-truth-table", "64 组发送条件组合及隐藏活动组试闪条件", events)

    events = [call("setDeliveryOptions", False, False, expect=expected(True,
                  [["deliveryOptionsChanged", True, False]], sendPowerUpdates=True, sendFlashSync=False)),
              call("setDeliveryOptions", False, False, expect=expected(True, [])),
              call("setDeliveryOptions", "ignored-by-baseline", False, expect=expected(True, [])),
              call("setDeliveryOptions", True, "invalid", expect=expected(False, [])),
              call("setGroup", 2, True, 30, True, expect=expected(True, power_change(2, True, 30))),
              set_value("connected", True, expect=expected(UNDEFINED, [])),
              set_value("masterEnabled", True, expect=expected(UNDEFINED, [])),
              call("setDeliveryOptions", False, True, expect=expected(True,
                  [["deliveryOptionsChanged", True, True]], sendPowerUpdates=True, sendFlashSync=True))]
    add("delivery-preference-no-replay", "偏好强制功率更新保持旧行为，恢复发送不补发历史事件", events)

    add("reentrant-draft-blocks-delivery", "草稿 signal 同步置 busy，随后的功率发送重新检查门控", [
        set_value("connected", True), set_value("masterEnabled", True),
        call("setGroup", 0, True, 43, True,
             expect=expected(True, [["groupDraftChanged", 0, True, 43]], busy=True, powerUpdateAllowed=False)),
    ], [{"signal": "groupDraftChanged", "occurrence": 1, "events": [set_value("busy", True)]}])

    add("reentrant-draft-rewrites-group", "草稿 signal 同步外部回写，发送时重新读取组开关与功率", [
        set_value("connected", True), set_value("masterEnabled", True),
        call("setGroup", 0, True, 43, True, expect=expected(True,
             [["groupDraftChanged", 0, True, 43], ["powerUpdateRequested", 0, False, 77]],
             **{"groups.0": [False, 77]})),
    ], [{"signal": "groupDraftChanged", "occurrence": 1,
         "events": [call("setGroup", 0, False, 77, False)]}])

    add("reentrant-batch-blocks-later-deliveries", "批量第一组发送 signal 同步置 busy，后续组保留草稿而停止发送", [
        set_value("connected", True), set_value("masterEnabled", True), set_value("visibleGroups", [0, 1, 2]),
        call("adjustVisiblePower", 1, expect=expected(True,
             [["groupDraftChanged", 0, False, 43], ["powerUpdateRequested", 0, False, 43],
              ["groupDraftChanged", 1, False, 43], ["groupDraftChanged", 2, False, 43]],
             **{"busy": True, "groupAdjustmentSteps": 1, "groups.0": [False, 43],
                "groups.1": [False, 43], "groups.2": [False, 43]})),
    ], [{"signal": "powerUpdateRequested", "occurrence": 1, "events": [set_value("busy", True)]}])

    events = [call("setGroup", 0, True, 20, False, expect=expected(True, [], hasDraftChanges=False)),
              set_value("connected", True), set_value("masterEnabled", True),
              call("setGroup", 0, False, 21, False, expect=expected(True, [], hasDraftChanges=False)),
              call("setGroup", 0, False, 21, True, expect=expected(True, [], hasDraftChanges=False)),
              call("setGroup", 0, False, 22, True, expect=expected(True, power_change(0, False, 22, True), hasDraftChanges=True)),
              set_value("hasDraftChanges", False), set_value("visibleGroups", [0]),
              call("adjustVisiblePower", 1),
              call("setGroup", 0, False, 23, False, expect=expected(True, [], groupAdjustmentSteps=1)),
              call("setGroup", 0, False, 24, False, expect=expected(True, [], groupAdjustmentSteps=0)),
              set_value("supportedGroupCount", 4)]
    for index, value in [(-1, 40), (4, 40), (1.5, 40), (1, -1), (1, 81), (1, 1.5)]:
        events.append(call("setGroup", index, True, value, True, expect=expected(False, [])))
    add("external-versus-draft", "外部回写不发送，相同值幂等，asDraft 才发草稿，单组改值重置批量步数", events)

    events = [set_value("visibleGroups", [0]),
              call("setGroup", 0, False, 80, False, expect=expected(True, [],
                  regressionCanIncrease=False, regressionCanDecrease=True,
                  regressionIncreaseChangeCount=1, regressionDecreaseChangeCount=0))]
    for e in [call("requestPowerUpdate", 0), call("requestFlashSync"), call("requestTest"),
              call("openWireless", "id"), call("canAdjustVisiblePower", -1),
              call("steppedPower", 40, 1), call("groupPower", 0), call("closeDetail")]:
        e["expect"] = {"state.regressionCanIncrease": False, "state.regressionCanDecrease": True,
                       "state.regressionIncreaseChangeCount": 1, "state.regressionDecreaseChangeCount": 0}
        events.append(e)
    events += [call("setGroup", 0, False, 0, False, expect=expected(True, [],
                   regressionCanIncrease=True, regressionCanDecrease=False,
                   regressionIncreaseChangeCount=2, regressionDecreaseChangeCount=1)),
               call("regressionSetModelGroup", 0, False, 40, expect=expected(UNDEFINED, [],
                   regressionCanIncrease=True, regressionCanDecrease=True,
                   regressionIncreaseChangeCount=2, regressionDecreaseChangeCount=2)),
               set_value("maximumPower", 40, expect=expected(UNDEFINED, [],
                   regressionCanIncrease=False, regressionIncreaseChangeCount=3)),
               set_value("minimumPower", 40, expect=expected(UNDEFINED, [],
                   regressionCanDecrease=False, regressionDecreaseChangeCount=3)),
               set_value("minimumPower", 0), set_value("maximumPower", 80),
               call("regressionSetModelGroup", 0, False, 79),
               set_value("maximumPower", 79, expect=expected(UNDEFINED, [], regressionCanIncrease=False)),
               call("setAdjustmentStep", False, False, expect=expected(True, [], regressionCanIncrease=False)),
               call("regressionSetModelGroup", 0, False, 78, expect=expected(UNDEFINED, [], regressionCanIncrease=True))]
    add("qml-binding-dependencies", "外部/asDraft=false 回写、范围/步长绑定自动更新，无关原生调用不引起 canAdjust 往返变化", events)

    events = [call("wirelessKey", "1", expect=expected(False, [])),
              call("openWireless", "invalid", expect=expected(False, [])),
              call("openWireless", "channel", expect=expected(True, [], wirelessInput="5", wirelessInputFresh=True)),
              call("wirelessKey", "3", expect=expected(True, [], wirelessInput="3", wirelessInputValid=True)),
              call("wirelessKey", "2", expect=expected(True, [], wirelessInput="32", wirelessInputValid=True)),
              call("wirelessKey", "1", expect=expected(False, [], wirelessInput="32")),
              call("confirmWireless", expect=expected(True, [["wirelessConfigurationRequested", 32, 5]], channel=5, screen="groups")),
              set_value("channel", 32), call("openWireless", "channel"),
              call("wirelessKey", "清除", expect=expected(True, [], wirelessInput="", wirelessInputValid=False)),
              call("confirmWireless", expect=expected(False, [])),
              call("wirelessKey", "0", expect=expected(True, [], wirelessInputValid=False)),
              call("wirelessKey", "1", expect=expected(True, [], wirelessInput="01", wirelessInputValid=True)),
              call("confirmWireless", expect=expected(True, [["wirelessConfigurationRequested", 1, 5]])),
              call("openWireless", "channel"), call("wirelessKey", "3"), call("wirelessKey", "3"),
              call("confirmWireless", expect=expected(False, [], wirelessInput="33", wirelessInputValid=False)),
              call("wirelessKey", "退格", expect=expected(True, [], wirelessInput="3", wirelessInputValid=True)),
              call("wirelessKey", "x", expect=expected(False, [], wirelessInput="3")),
              call("openWireless", "id"), call("wirelessKey", "9"), call("wirelessKey", "9"),
              call("confirmWireless", expect=expected(True, [["wirelessConfigurationRequested", 32, 99]], wirelessId=5)),
              call("openWireless", "id"), set_value("wirelessOff", True), set_value("wirelessInput", ""),
              set_value("wirelessInputFresh", True),
              call("confirmWireless", expect=expected(True, [["wirelessConfigurationRequested", 32, 0]])),
              set_value("wirelessId", 0), call("openWireless", "id", expect=expected(True, [], wirelessOff=True)),
              call("wirelessKey", "退格", expect=expected(True, [], wirelessInput="", wirelessOff=False, wirelessInputValid=False)),
              set_value("wirelessOff", True), call("wirelessKey", "7", expect=expected(True, [], wirelessInput="7", wirelessOff=False)),
              call("confirmWireless", expect=expected(True, [["wirelessConfigurationRequested", 32, 7]]))]
    add("wireless-digit-editor", "CH 1–32 / ID 1–99/OFF、替换首键、长度、退格、确认与外部回写", events)

    events = [set_value("pageActive", True), call("openGroup", 2), set_value("calibrationOpen", True),
              call("requestBack", expect=expected(UNDEFINED, [], calibrationOpen=False, screen="power")),
              call("requestBack", expect=expected(UNDEFINED, [], screen="groups")),
              call("requestBack", expect=expected(UNDEFINED, [["backRequested"]])),
              call("openWireless", "id"), set_value("calibrationOpen", True),
              set_value("pageActive", False, expect=expected(UNDEFINED, [], screen="groups", calibrationOpen=False)),
              set_value("pageActive", True, expect=expected(UNDEFINED, [])),
              call("setAdjustmentStep", False, True, expect=expected(True, [["adjustmentStepRequested", False]], thirdStopSteps=False)),
              call("setAdjustmentStep", False, True, expect=expected(True, [])),
              call("setAdjustmentStep", "invalid", True, expect=expected(False, []))]
    for value, base, fraction in [(0, "1/256", ""), (3, "1/256", "+0.3"),
                                  (7, "1/256", "+0.7"), (40, "1/16", ""), (80, "1/1", "")]:
        events += [call("powerText", value, expect=expected(base, [])),
                   call("fractionText", value, expect=expected(fraction, []))]
    add("navigation-and-format", "返回优先级、隐藏页不发命令、调整步长幂等与功率文本", events)
    return cases


def random_cases(seed: int, count: int, length: int) -> list[dict]:
    """可复现的真实接口事件；不生成会令旧 QML 非法取 ListModel 的索引。"""
    rng = random.Random(seed)
    cases = []
    for case_index in range(count):
        events = []
        for _ in range(length):
            group = rng.randrange(16)
            direction = rng.choice([-1, 1])
            choice = rng.randrange(22)
            if choice == 0:
                e = call("setGroup", group, bool(rng.getrandbits(1)), rng.randrange(81), bool(rng.getrandbits(1)))
            elif choice == 1:
                e = call("toggleGroup", group)
            elif choice == 2:
                e = call("toggleLamp", group)
            elif choice == 3:
                e = call("quickAdjust", group, direction)
            elif choice == 4:
                e = call("swipePower", group, rng.randrange(81), rng.randrange(-100, 101))
            elif choice == 5:
                e = call("adjustPower", direction)
            elif choice == 6:
                e = call("adjustVisiblePower", direction)
            elif choice == 7:
                e = call("toggleVisibleGroup", group)
            elif choice == 8:
                e = call("setAdjustmentStep", bool(rng.getrandbits(1)), bool(rng.getrandbits(1)))
            elif choice == 9:
                e = call("setDeliveryOptions", bool(rng.getrandbits(1)), bool(rng.getrandbits(1)))
            elif choice == 10:
                e = set_value(rng.choice(["connected", "masterEnabled", "busy", "canTest", "modelingLampAvailable", "sendPowerUpdates", "sendFlashSync"]), bool(rng.getrandbits(1)))
            elif choice == 11:
                e = call("requestPowerUpdate", group)
            elif choice == 12:
                e = call("requestFlashSync")
            elif choice == 13:
                e = call("requestTest")
            elif choice == 14:
                e = call("openWireless", rng.choice(["channel", "id"]))
            elif choice == 15:
                e = call("wirelessKey", rng.choice(list("0123456789") + ["退格", "清除", "x"]))
            elif choice == 16:
                e = call("confirmWireless")
            elif choice == 17:
                e = call("openGroup", group)
            elif choice == 18:
                e = call("requestBack")
            elif choice == 19:
                e = set_value(rng.choice(["pageActive", "calibrationOpen", "hasDraftChanges"]), bool(rng.getrandbits(1)))
            elif choice == 20:
                e = set_value("visibleGroups", sorted(rng.sample(range(16), rng.randrange(17))))
            else:
                e = set_value("channel", rng.randrange(1, 33)) if rng.getrandbits(1) else set_value("wirelessId", rng.randrange(100))
            events.append(e)
        cases.append({"name": f"random-{case_index + 1:02d}", "coverage": "随机交错状态/方法轨迹", "events": events})
    return cases


def at_path(value: Any, path: str) -> Any:
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def first_difference(left: Any, right: Any, path: str = "") -> dict | None:
    if type(left) is not type(right):
        # JSON 中等价的整数/实数不会构成迁移差异，bool 仍严格区分。
        if type(left) in (int, float) and type(right) in (int, float) and left == right:
            return None
        return {"path": path, "expected": left, "actual": right}
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return {"path": path, "expectedKeys": sorted(left), "actualKeys": sorted(right)}
        for key in left:
            diff = first_difference(left[key], right[key], f"{path}.{key}".strip("."))
            if diff:
                return diff
    elif isinstance(left, list):
        if len(left) != len(right):
            return {"path": path, "expectedLength": len(left), "actualLength": len(right)}
        for i, (a, b) in enumerate(zip(left, right)):
            diff = first_difference(a, b, f"{path}.{i}".strip("."))
            if diff:
                return diff
    elif left != right:
        return {"path": path, "expected": left, "actual": right}
    return None


class Runner:
    def __init__(self, baseline_source: str, adapter_path: Path | None, candidate_qml: Path | None):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QML_DISABLE_DISK_CACHE"] = "1"
        os.environ["QML_DISK_CACHE_PATH"] = str(OUTPUT / "qml-cache")
        os.environ["QT_SHADER_CACHE_PATH"] = str(OUTPUT / "shader-cache")
        sys.path.insert(0, str(REPO / "x1d/wireless-flash/build/ui-test-python"))
        from PySide6.QtCore import QUrl, qVersion
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine

        self.app = QGuiApplication.instance() or QGuiApplication([])
        self.engine = QQmlEngine()
        self.qt_version = qVersion()
        self.QUrl = QUrl
        self.QQmlComponent = QQmlComponent
        self.baseline_source = baseline_source
        self.signal_names = re.findall(r"(?m)^    signal (\w+)\(", baseline_source)
        self.function_names = set(re.findall(r"(?m)^    function (\w+)\(", baseline_source)) | TEST_FUNCTIONS
        self.writable_fields = set(re.findall(r"(?m)^    property \w+ (\w+)\s*:", baseline_source)) | {"regressionScrollY"}
        self.keep_alive = []
        self.errors = []
        self.qml_warnings = []
        self.engine.warnings.connect(lambda warnings: self.qml_warnings.extend(e.toString() for e in warnings))
        self.context = {"engine": self.engine, "output_dir": OUTPUT,
                        "baseline_source": baseline_source, "simplify_source": simplify_source,
                        "make_component": self.make_component, "keep_alive": self.keep_alive, "errors": self.errors}
        self.adapter = None
        self.candidate_source = candidate_qml.read_text(encoding="utf-8") if candidate_qml else None
        if adapter_path:
            spec = importlib.util.spec_from_file_location("flash_regression_candidate_adapter", adapter_path)
            self.adapter = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = self.adapter
            spec.loader.exec_module(self.adapter)
            install_context = getattr(self.adapter, "install_context", None)
            if callable(install_context):
                install_context(self.context)
            if not candidate_qml and not callable(getattr(self.adapter, "create_candidate", None)):
                raise TypeError("独立 adapter 必须导出 create_candidate(context)。")
            if candidate_qml and not callable(install_context):
                raise TypeError("与 --candidate-qml 同时使用时 adapter 必须导出 install_context(context)。")

    def make_component(self, source: str, label: str = "candidate"):
        # adapter 可返回完整页或自带 stub 的独立 QML，后者不再二次裁切。
        if re.search(r"(?m)^    Item\s*\{\s*\n\s*id:\s*canvas;", source):
            source = simplify_source(source)
        path = OUTPUT / f"{label}.qml"
        path.write_text(source, encoding="utf-8")
        component = self.QQmlComponent(self.engine)
        component.setData(source.encode("utf-8"), self.QUrl.fromLocalFile(str(path)))
        obj = component.create()
        if not obj:
            raise RuntimeError("\n".join(e.toString() for e in component.errors()))
        self.keep_alive.extend([component, obj])
        return obj

    def create(self, name: str, callbacks: list[dict] | None = None):
        if name == "baseline":
            obj = self.make_component(self.baseline_source, "baseline-business")
        elif self.adapter and not self.candidate_source:
            obj = self.adapter.create_candidate(self.context)
            if isinstance(obj, str):
                obj = self.make_component(obj, "candidate-business")
        else:
            obj = self.make_component(self.candidate_source, "candidate-business")
        if obj is None:
            raise RuntimeError("create_candidate 返回空对象。")
        self.engine.globalObject().setProperty("regPage", self.engine.newQObject(obj))
        commands = []
        signal_counts = {}
        for name in self.signal_names:
            signal = getattr(obj, name, None)
            if signal is None:
                raise AttributeError(f"候选缺少业务 signal：{name}")

            def receive(*args, signal_name=name):
                try:
                    converted = [value.toVariant() if hasattr(value, "toVariant") else value for value in args]
                    commands.append(json.loads(json.dumps([signal_name, *converted], ensure_ascii=False)))
                    signal_counts[signal_name] = signal_counts.get(signal_name, 0) + 1
                    for callback in callbacks or []:
                        if (callback["signal"] == signal_name and
                                callback["occurrence"] == signal_counts[signal_name]):
                            for event in callback["events"]:
                                if event["op"] == "signalAppend":
                                    self.append_signal_argument(args, event)
                                else:
                                    self.invoke(event)
                except Exception as exc:
                    # PySide signal 回调异常不会自动向外层 evaluate 传播。
                    self.errors.append(f"signal callback {signal_name}: {exc}")

            signal.connect(receive)
            self.keep_alive.append(receive)
        return obj, commands

    def append_signal_argument(self, args: tuple, event: dict) -> None:
        """保留原始 QJSValue 对象身份；不能先转 QVariantList/JSON 再追加。"""
        index = event.get("argument")
        if type(index) is not int or not 0 <= index < len(args):
            raise ValueError("signalAppend.argument 必须是当前 signal 的有效参数索引。")
        target = args[index]
        if not hasattr(target, "isArray") or not target.isArray():
            raise TypeError("signalAppend 仅允许原始 QJSValue 数组参数。")
        # toScriptValue 只转换数据，不解析任意 JavaScript；value 必须可被 JSON 编码。
        value = json.loads(json.dumps(event["value"], ensure_ascii=False, allow_nan=False))
        result = target.property("push").callWithInstance(target, [self.engine.toScriptValue(value)])
        if result.isError():
            raise RuntimeError(f"signalAppend.push 失败：{result.toString()}")

    def evaluate(self, script: str) -> Any:
        result = self.engine.evaluate(script)
        if result.isError():
            raise RuntimeError(f"{result.toString()}\n{result.property('stack').toString()}")
        if self.errors:
            raise RuntimeError(f"候选离线桥错误：{self.errors}")
        if self.qml_warnings:
            raise RuntimeError(f"QML 警告：{self.qml_warnings}")
        return result.toVariant()

    def snapshot(self) -> dict:
        script = """(function(p) {
            var out = {}, fields = FIELDS;
            for (var n = 0; n < fields.length; n++) out[fields[n]] = p[fields[n]];
            out.groups = [];
            for (var i = 0; i < 16; i++) out.groups.push([p.groupActive(i), p.groupPower(i)]);
            out.groupAdjustmentText = p.groupAdjustmentText();
            return JSON.stringify(out);
        })(regPage)""".replace("FIELDS", json.dumps(STATE_FIELDS))
        out = json.loads(self.evaluate(script))
        missing = set(STATE_FIELDS) - out.keys()
        if missing:
            raise RuntimeError(f"候选缺少可观察状态：{sorted(missing)}")
        return out

    def invoke(self, event: dict) -> Any:
        if event["op"] == "call":
            method = event["method"]
            if method not in self.function_names:
                raise ValueError(f"不在基线方法白名单：{method}")
            invocation = f"regPage[{json.dumps(method)}].apply(regPage, {json.dumps(event['args'], ensure_ascii=False)})"
        elif event["op"] == "set":
            prop = event["property"]
            if prop not in self.writable_fields:
                raise ValueError(f"不在可写属性白名单：{prop}")
            invocation = f"(function(){{regPage[{json.dumps(prop)}]={json.dumps(event['value'], ensure_ascii=False)};}})()"
        else:
            raise ValueError(f"未知事件：{event['op']}")
        value = self.evaluate("""(function() {
            var value = INVOCATION;
            if (typeof value === 'undefined') value = {$type:'undefined'};
            else if (typeof value === 'number' && !isFinite(value)) value = {$type:'number', value:String(value)};
            return JSON.stringify(value);
        })()""".replace("INVOCATION", invocation))
        return json.loads(value)

    def execute(self, event: dict, commands: list) -> dict:
        commands.clear()
        value = self.invoke(event)
        return {"result": value, "state": self.snapshot(), "commands": list(commands)}

    def run(self, name: str, cases: list[dict], reference: list[dict] | None = None) -> tuple[list[dict], int]:
        records = []
        assertions = 0
        with (OUTPUT / f"{name}-trace.jsonl").open("w", encoding="utf-8") as log:
            for case in cases:
                obj, commands = self.create(name, case.get("callbacks"))
                initial = {"case": case["name"], "index": -1, "event": {"op": "reset"},
                           "observed": {"result": UNDEFINED, "state": self.snapshot(), "commands": list(commands)}}
                log.write(json.dumps(initial, ensure_ascii=False) + "\n")
                if reference:
                    self.compare_record(reference[len(records)], initial)
                records.append(initial)
                for index, event in enumerate(case["events"]):
                    record = {"case": case["name"], "index": index,
                              "event": {k: v for k, v in event.items() if k != "expect"},
                              "observed": self.execute(event, commands)}
                    log.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log.flush()
                    for path, value in event.get("expect", {}).items():
                        observed = at_path(record["observed"], path)
                        diff = first_difference(value, observed, path)
                        if diff:
                            save_json(OUTPUT / "failure.json", {"stage": name, "record": record, "difference": diff})
                            raise AssertionError(f"{name}/{case['name']} 事件 {index} 明确断言失败：{diff}")
                        assertions += 1
                    if reference:
                        self.compare_record(reference[len(records)], record)
                    records.append(record)
                # 每个 case 使用独立页面；先保留 QObject，防止回调引用被提前回收。
                self.keep_alive.append(obj)
        return records, assertions

    @staticmethod
    def compare_record(reference: dict, candidate: dict) -> None:
        diff = first_difference(reference, candidate)
        if diff:
            save_json(OUTPUT / "failure.json", {"stage": "candidate", "record": candidate,
                                                "baseline": reference, "difference": diff})
            raise AssertionError(f"候选差分失败 {candidate['case']} 事件 {candidate['index']}：{diff}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-qml", type=Path)
    parser.add_argument("--candidate-adapter", type=Path)
    parser.add_argument("--export-candidate-qml", type=Path,
                        help="只导出候选精简组件，供其他平台执行；本次候选状态仍为 not_run")
    parser.add_argument("--seed", type=int, default=20260922)
    parser.add_argument("--random-cases", type=int, default=4)
    parser.add_argument("--random-events", type=int, default=600)
    parser.add_argument("--events-file", type=Path, help="重放先前输出的 events.json；不自动生成新事件")
    args = parser.parse_args()
    source = fixed_baseline()
    export_candidate = args.export_candidate_qml or args.candidate_qml
    if export_candidate:
        candidate_source = export_candidate.read_text(encoding="utf-8")
        candidate_path = OUTPUT / "candidate-business.qml"
        candidate_path.write_text(simplify_source(candidate_source), encoding="utf-8")
        save_json(OUTPUT / "candidate-manifest.json", {
            "source": str(export_candidate.resolve().relative_to(REPO)),
            "sourceSha256": file_hash(export_candidate), "businessSha256": file_hash(candidate_path),
            "status": "exported_not_executed", "retainsNativeAliasesAndEntry": "nativeFlash" in candidate_source,
        })
    cases = json.loads(args.events_file.read_text(encoding="utf-8"))["cases"] if args.events_file else (
        targeted_cases() + random_cases(args.seed, args.random_cases, args.random_events))
    save_json(OUTPUT / "events.json", {"schema": FORMAT, "baselineSha256": BASELINE_SHA256,
                                     "seed": args.seed, "cases": cases})
    report = {"schema": FORMAT, "baselineSha256": BASELINE_SHA256,
              "baseline": "running", "candidate": "not_run", "passed": None,
              "hardwareRequests": 0, "hostBridgeSimulated": bool(args.candidate_adapter),
              "armRuntimeVerified": False, "seed": args.seed,
              "cases": len(cases), "events": sum(len(c["events"]) for c in cases),
              "coverage": [{"case": c["name"], "description": c["coverage"], "events": len(c["events"])} for c in cases],
              "scope": "只验证页级业务 props/models/functions，不覆盖原始 MouseArea 手势映射、视觉布局、动画或设备传输。"}
    save_json(OUTPUT / "result.json", report)
    try:
        runner = Runner(source, args.candidate_adapter, args.candidate_qml)
        reference, assertions = runner.run("baseline", cases)
        report.update({"baseline": "passed", "explicitAssertions": assertions,
                       "stateFields": len(STATE_FIELDS) + 2, "commandSignals": len(runner.signal_names),
                       "qtVersion": runner.qt_version, "oracleRecords": len(reference)})
        if args.candidate_adapter or args.candidate_qml:
            report["candidate"] = "running"
            save_json(OUTPUT / "result.json", report)
            candidate, _ = runner.run("candidate", cases, reference)
            report.update({"candidate": "passed", "passed": True, "eventComparisons": len(candidate)})
            input_path = args.candidate_adapter or args.candidate_qml
            report["candidateInput"] = str(input_path.resolve().relative_to(REPO))
            report["candidateInputSha256"] = file_hash(input_path)
        else:
            report["note"] = "基线明确断言通过并已保存 oracle；尚未提供候选，不能据此称原生迁移通过。"
        save_json(OUTPUT / "interface.json", {
            "schema": FORMAT, "stateFields": STATE_FIELDS, "signals": runner.signal_names,
            "derivedStateFields": ["groups", "groupAdjustmentText"],
            "observedStateFields": STATE_FIELDS + ["groups", "groupAdjustmentText"],
            "groupsEncoding": "16 项数组，每项为 [groupActive(i), groupPower(i)]。",
            "functions": sorted(runner.function_names), "testOnlyFunctions": sorted(TEST_FUNCTIONS),
            "writableProperties": sorted(runner.writable_fields),
            "recordFormat": {"case": "case-name", "index": 0, "event": {"op": "call", "method": "adjustPower", "args": [1]},
                             "observed": {"result": True, "state": "完整状态对象", "commands": [["groupDraftChanged", 0, True, 43]]}},
            "candidateAdapter": "create_candidate(context) -> QObject 或 QML；context 详见脚本说明。每个 case 建立全新组件，保留 bridge 引用到 context['keep_alive']。",
            "synchronousCallbacks": "case.callbacks=[{signal,occurrence,events}]。先记录命令，再在该 signal 的同步回调中执行 events；occurrence 在 case 内从 1 开始计数，不能延迟到主事件完成后。",
            "signalAppend": "仅限 callback.events：{op:'signalAppend',argument:0,value:15}。argument 从0编号，必须取 signal 回调收到的原始 QJSValue 数组，对其 push(value)；禁止先转 QVariantList/JSON 副本。命令记录保留追加前参数，页面 snapshot 在主事件结束后读取共享数组。value 为 JSON 数据，不执行任意 eval。",
            "undefinedResult": UNDEFINED,
            "resetRecord": "每个 case 创建新页面；初始记录 index=-1，event={op:'reset'}，result 为 undefined。set 事件返回 undefined。",
            "explicitAssertions": "event.expect 的 key 是相对于 observed 的点分路径，如 state.groups.0.1 或 commands；每项必须深比较。",
            "limitations": report["scope"],
        })
        save_json(OUTPUT / "result.json", report)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Exception as exc:
        report["passed"] = False
        report["error"] = str(exc)
        if report["baseline"] == "running":
            report["baseline"] = "failed"
        elif report["candidate"] == "running":
            report["candidate"] = "failed"
        save_json(OUTPUT / "result.json", report)
        (OUTPUT / "failure-traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
