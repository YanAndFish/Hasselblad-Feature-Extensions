"""AF r5 干净基线完整交付入口。report / inspect 完全离线。"""
import argparse, json, sys
sys.dont_write_bytecode = True
import delivery_package as package

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',nargs='?',default='report',choices=('report','stage','install-staged','inspect','restore-preflight','rollback-held'))
    p.add_argument('--evidence')
    a = p.parse_args()
    if a.action=='report':
        r,_=package.verify()
        result={'offlineReady':True,'hardwareRequests':0,'packageSha256':r['packageSha256'],
            'physicalR5Verified':False,'physicalRoundtripVerified':False,'guiRevision':'ui-interaction-r4','busRevision':'bus-roundtrip-r3','firstFarmReplyAfterHoldMs':20000,'normalFarmReplyMs':2000,
            'requires':'独占原厂 Linux/AF 基线；不与其他驻留模块合装；首次 stage 不得已有临时目录'}
    elif a.action=='stage':
        if a.evidence:p.error('stage creates fresh evidence')
        from session import stage
        result={'stageEvidence':str(stage())}
    else:
        if not a.evidence:p.error('--evidence required')
        if a.action=='install-staged':
            from session import install
            result=install(a.evidence)
        else:
            import recovery
            result={'inspect':recovery.inspect,'restore-preflight':recovery.restore_preflight,
                'rollback-held':recovery.rollback_held}[a.action](a.evidence)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
