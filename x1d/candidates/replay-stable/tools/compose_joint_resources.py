"""供唯一 GUI 资源协调方调用的纯函数；不读写其他候选或注册 RCC。"""
from pathlib import Path
import hashlib

HERE=Path(__file__).resolve().parents[1]
MARKER='// X1D_REPLAY_JOINT_RESOURCE_V1'

def compose(resources):
    if not isinstance(resources,dict) or '/main.qml' not in resources or 'main.qml' in resources:
        raise ValueError('需要唯一 /main.qml 的资源字典')
    main=resources['/main.qml']
    if not isinstance(main,str) or main.count('objectName: "mainRoot"')!=1 or not main.rstrip().endswith('}'):
        raise ValueError('原厂 mainRoot 锚点缺失或重复')
    if 'x1dReplaySession' in main or MARKER in main or 'replayInstallHoldTimer' in main:
        raise ValueError('已有回放会话接入，拒绝重复组合')
    # 活动保持归协调方原 root 段；这里只回报本模块的 QML 实际构造。
    addition='''    QtObject {
        id: replayJointResourceProof
        Component.onCompleted: {
            if (typeof x1dReplaySession!=="undefined") x1dReplaySession.resourceReady = true
        }
    }
'''
    result=dict(resources)
    result['/main.qml']=main.rstrip()[:-1]+MARKER+'\n'+addition+'}\n'
    return result

def identity(resources):
    """协调方先组合所有模块，再用最终文本身份构建 joint 守护库。"""
    main=resources['/main.qml']
    if main.count(MARKER)!=1:raise ValueError('缺少唯一回放组合标记')
    return hashlib.sha256(main.encode('utf-8')).hexdigest()
