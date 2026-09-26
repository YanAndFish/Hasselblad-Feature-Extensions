"""只读取固定匿名状态文件；不发送 AF query/apply，也不读取照片。"""
import argparse,json
import bus_package as package
import transfer,stage
def observe():
    package.verify();session=transfer.Session('af-bus-r5-observe')
    state={'observed':False,'afCommands':0,'photoReads':0}
    commands=[('services','systemctl is-active victory-gui msg2dbus-farm'),
        ('backend','cat /tmp/hbl-af-settings/backend-r5.status')]
    for name,parts in [('backend-r5-flow.status',[(1,11),(12,22),(23,33)]),
                       ('backend-r5-transport.status',[(1,10),(11,23)]),
                       ('ui-r4.status',[(1,10),(11,20)])]:
        for first,last in parts:
            commands.append((name+'-'+str(first),"cut -d' ' -f"+str(first)+'-'+str(last)+' /tmp/hbl-af-settings/'+name))
    try:
        for label,command in commands:session.command(label,command)
        state['observed']=True
    finally:stage.record(session,state,'observation.json')
    return state
if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(observe(),ensure_ascii=False,indent=2))
