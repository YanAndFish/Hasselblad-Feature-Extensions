"""上传芯片预准备完整包；解码只派发一次，读取完成哈希后才解包。"""
import base64
import hashlib
import json
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "build/mechanical-hw-ready-candidate"
# BusyBox awk 的 %c 不用于二进制 NUL；先产生八进制转义，再由 shell printf %b 解码。
DECODER = 'BEGIN{s="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"}{for(i=1;i<=length($0);i++){c=substr($0,i,1);if(c=="=")break;v=index(s,c)-1;if(v<0)continue;b=b*64+v;n+=6;if(n>=8){n-=8;o=int(b/2^n);b%=2^n;printf "\\\\%03o",o}}}'


def stage(session):
    manifest = json.loads((OUT / "package-validation.json").read_text(encoding="utf-8"))
    payload = (OUT / "session-package.tar.gz").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest["packageSha256"] or len(payload) != manifest["packageBytes"]:
        raise RuntimeError("Fixed package changed")
    session.command("create-own-stage", "test ! -e /tmp/hbl-wireless-flash && mkdir -m 700 /tmp/hbl-wireless-flash")
    for index, start in enumerate(range(0, len(DECODER), 90)):
        session.command("decoder-" + str(index), "printf %s " + shlex.quote(DECODER[start:start+90]) +
                        (" >" if index == 0 else " >>") + "/tmp/hbl-wireless-flash/d.awk")
    encoded = base64.b64encode(payload).decode("ascii")
    parts = [encoded[i:i+176] for i in range(0, len(encoded), 176)]
    for index, part in enumerate(parts):
        session.command("package-" + str(index), "printf %s " + shlex.quote(part) +
                        (" >" if index == 0 else " >>") + "/tmp/hbl-wireless-flash/p64")
        if (index+1) % 100 == 0:
            print("package chunks", index+1, "/", len(parts), flush=True)
    import time
    session.command("decode-dispatched", 'd=/tmp/hbl-wireless-flash;(printf \'%b\' "$(awk -f "$d/d.awk" "$d/p64")" >"$d/session.tar.gz";sha256sum "$d/session.tar.gz" >"$d/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(30):
        time.sleep(1)
        result=session.command("verify-existing-archive-"+str(attempt),'d=/tmp/hbl-wireless-flash;if test -f "$d/decode.sha"; then cat "$d/decode.sha"; else printf pending; fi')
        if result["output"]!="pending": break
    else: raise RuntimeError("Archive decode still pending; do not dispatch again")
    if result["output"].split()[0] != digest:
        raise RuntimeError("Uploaded package hash mismatch; do not extract")
    result = session.command("extract-and-verify", "cd /tmp/hbl-wireless-flash && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && printf package-verified")
    if result["output"] != "package-verified":
        raise RuntimeError("Package members not verified")
    print(json.dumps({"package_verified": True, "chunks": len(parts), "bytes": len(payload)}), flush=True)

