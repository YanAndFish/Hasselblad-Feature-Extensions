"""固定组合包的有界串行传输；导入与默认运行均离线。"""
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import shlex
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
from linux_command import Session as OriginalSession

REMOTE='/tmp/hbl-x1d-combined'
PHASES=('preflight','ui','observer','provider','bridge','enable','release',
        'replay-prepare','replay-config','replay-jpeg','replay-restore','worker-stop','restore-linux')

class Session:
    """每64个请求独立一份原格式日志；避免大包逐帧重写数千条旧记录。"""
    def __init__(self,name):
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):raise ValueError('session name')
        self.directory=HERE/'build/sessions'/(name+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        self.directory.mkdir(parents=True,exist_ok=False)
        self.sessions=[];self.failed=False;self.dispatched=set()
    @property
    def entries(self):return [entry for session in self.sessions for entry in session.entries]
    def command(self,label,command,timeout_ms=15000):
        if self.failed:raise RuntimeError('session stopped')
        if not self.sessions or len(self.sessions[-1].entries)>=64:
            session=OriginalSession(self.directory.name+'-'+str(len(self.sessions))+'.json')
            session.output=self.directory/(str(len(self.sessions)).zfill(4)+'.json')
            self.sessions.append(session)
        try:return self.sessions[-1].command(label,command,timeout_ms)
        except BaseException:
            self.failed=True
            raise
    def summary(self):
        entries=self.entries
        return {'directory':self.directory.relative_to(ROOT).as_posix(),'requests':sum(e['submitted'] for e in entries),
                'allHandlesClosed':all(e['closed'] for e in entries),'failed':self.failed,'dispatched':sorted(self.dispatched)}

DECODER='BEGIN{s="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"}{for(i=1;i<=length($0);i++){c=substr($0,i,1);if(c=="=")break;v=index(s,c)-1;if(v<0)continue;b=b*64+v;n+=6;if(n>=8){n-=8;o=int(b/2^n);b%=2^n;printf "\\\\%03o",o}}}'
