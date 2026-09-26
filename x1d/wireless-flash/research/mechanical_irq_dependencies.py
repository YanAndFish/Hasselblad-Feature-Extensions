"""追踪 IRQ 数据/使能/复位逻辑依赖；未覆盖资源和超限明确保留。无设备入口。"""
from collections import deque
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parents[1]
TARGETS={
    'sensor_idle':('CLBLL_R_X61Y69','CLBLL_LL_DQ'),
    'sensor_external_preflash_input':('unresolved','CLBLM_R_X19Y65','CLBLM_M_A3'),
}

def refs(cell):
    if cell['op']=='alias': return [('input',cell['input'])]
    if cell['op']=='ff': return [(key,cell[key]) for key in ('d','ce','sr')]
    if cell['op'] in ('table','mux','xor'): return [(str(n),v) for n,v in enumerate(cell['inputs'])]
    return []

def analyze(route,logic,limit=30000):
    inventory=json.loads((HERE/'research/mechanical-irq-inventory.json').read_text(encoding='utf-8'))
    assert inventory['fpgaSha256']=='8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30'
    results=[]
    for row in inventory['irqInputs']:
        pin=tuple(row['pin']); drivers,_,_=route.drivers(pin)
        assert drivers==[tuple(row['driver'])],pin
        root=drivers[0]
        if row['constantLow']:
            results.append({'input':row['input'],'gicId':row['gicId'],'constantLow':True,'targetPaths':{}})
            continue
        todo=deque([root]); parents={root:None}; via={}; visited=set(); boundaries={}; paths={}; capped=False
        while todo:
            node=todo.popleft()
            if node in visited: continue
            if len(visited)>=limit: capped=True; break
            visited.add(node)
            for name,target in TARGETS.items():
                if node==target and name not in paths:
                    path=[]; current=node
                    while current is not None:
                        path.append({'node':current,'edgeFromParent':via.get(current)})
                        current=parents[current]
                    paths[name]=list(reversed(path))
            if isinstance(node,int): continue
            try: cell=logic.cell(node)
            except (KeyError,ValueError) as error:
                boundaries[node]={'reason':'decode-error','detail':str(error)[:500]}; continue
            if cell['op']=='boundary': boundaries[node]=cell; continue
            for edge,ref in refs(cell):
                if ref not in parents:
                    parents[ref]=node; via[ref]=edge; todo.append(ref)
        results.append({'input':row['input'],'gicId':row['gicId'],'root':root,'constantLow':False,
                        'visited':len(visited),'pending':len(todo),'capped':capped,'targetPaths':paths,
                        'boundaryCount':len(boundaries),'boundaries':[{'node':n,'cell':c} for n,c in sorted(boundaries.items())]})
        print('irq dependency',row['input'],'nodes',len(visited),'boundaries',len(boundaries),'targets',list(paths),'capped',capped,flush=True)
    report={'source':'official X1D 1.25.0 fixed FPGA configuration','fpgaSha256':inventory['fpgaSha256'],
            'targets':TARGETS,'limitPerInput':limit,'irqInputs':results,'hardwareRequests':0,
            'newInterruptImplemented':False,'clockDependenciesScanned':False,
            'limitations':['扫描逻辑数据、使能及复位依赖；不是事件等价或物理时序证明。',
                           '经过总线或处理器边界的依赖不在模型中；未命中不能推出绝无间接联系。',
                           'RAM/SRL、未解资源与达到上限的范围保持未知，不按常量处理。'],
            'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (HERE/'research/mechanical-irq-dependencies.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'inputs':len(results),'idleHits':[r['input'] for r in results if 'sensor_idle' in r['targetPaths']],
            'externalHits':[r['input'] for r in results if 'sensor_external_preflash_input' in r['targetPaths']],
            'capped':[r['input'] for r in results if r.get('capped')],'hardwareRequests':0}

if __name__=='__main__':
    from mechanical_fpga_route import load
    route,logic,_=load()
    print(analyze(route,logic))
