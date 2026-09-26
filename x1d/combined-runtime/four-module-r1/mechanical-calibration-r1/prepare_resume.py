"""仅从已确认停用、尚未替换文件的精确状态继续，复用已上传包。"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
    original=(HERE/'apply.sh').read_text(encoding='utf-8')
    header=original[:original.index('[ ! -e previous ]')]
    # 已创建 stop 请求，必须确认它仍为本次请求；不重新发起。
    header=header.replace('[ ! -e "$d/formal-stop.request" ]','[ "$(cat "$d/formal-stop.request")" = stop ]')
    checks='''[ -d previous ] && [ ! -L previous ]
for name in formal-ui.rcc libhbl-formal.so libhbl-formal-observer.so manifest.sha256; do cmp "previous/$name" "$d/$name"; done
cmp previous/package-manifest.sha256 "$d/formal-state/package-manifest.sha256"
expected=$(printf 'formal-worker-stopped-default-off\\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=%s' "$oldfarm")
[ "$(cat "$d/formal-worker.status")" = "$expected" ]
'''
    rollback=original[original.index('stopped=0\n'):original.index('(set -C; printf stop')]
    continuation=original[original.index('stopped=1\nsystemctl stop victory-gui'):]
    (HERE/'resume.sh').write_text(header+checks+rollback+continuation,encoding='utf-8',newline='\n')
if __name__=='__main__':main()
