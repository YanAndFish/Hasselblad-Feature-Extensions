"""AF r7 离线状态入口；当前没有实机安装子命令。"""
import argparse, json, sys
sys.dont_write_bytecode = True


def main():
    from pathlib import Path
    readiness=json.loads((Path(__file__).resolve().parent/'readiness.json').read_text(encoding='utf-8'))
    p=argparse.ArgumentParser(description='AF r7 offline profile readiness; no installation entry is enabled')
    p.add_argument('action',nargs='?',default='report',choices=('report',))
    p.parse_args()
    print(json.dumps(readiness,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
