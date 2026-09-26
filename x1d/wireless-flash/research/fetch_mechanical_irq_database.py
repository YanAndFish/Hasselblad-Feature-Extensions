"""下载同一固定公开数据库版本的 BRAM/DSP 配置位定义，不访问相机。"""
from pathlib import Path
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json

HERE = Path(__file__).resolve().parents[1]
COMMIT = 'e8b8e8e46a91334f6232df84d36954323e15a1d1'
FILES = ('segbits_bram_r.db', 'segbits_dsp_r.db')


def fetch():
    if Path.cwd().resolve() != HERE.parents[1]:
        raise RuntimeError('工作区不匹配')
    target = HERE/'build/mechanical-irq-candidate/database'
    target.mkdir(parents=True, exist_ok=True)
    manifest = HERE/'research/mechanical-irq-database-extension.json'
    if manifest.exists():
        old = json.loads(manifest.read_text(encoding='utf-8'))
        if old['database_commit'] != COMMIT:
            raise ValueError('数据库版本不匹配')
        for name, expected in old['resources'].items():
            data = (target/name).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected['sha256']:
                raise ValueError('已缓存文件校验失败')
        return old
    def read(name):
        url = f'https://raw.githubusercontent.com/openXC7/prjxray-db/{COMMIT}/zynq7/{name}'
        with urlopen(url, timeout=30) as response:
            data = response.read(2000000)
        if not data or len(data) >= 2000000:
            raise ValueError('数据库文件大小不符')
        return name, url, data
    result = {'database_commit': COMMIT, 'resources': {}, 'hardwareRequests': 0}
    with ThreadPoolExecutor(max_workers=2) as pool:
        downloaded = list(pool.map(read, FILES))
    for name, url, data in downloaded:
        (target/name).write_bytes(data)
        result['resources'][name] = {'url': url, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    print(json.dumps(fetch()))
