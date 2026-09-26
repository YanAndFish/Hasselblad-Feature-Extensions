"""安装/恢复脚本的本机命令模拟；所有绝对路径在工作副本中映射到测试目录。
真实脚本只做 sh -n；模拟组件不访问 Linux 设备、服务、网络或相机。
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'CodeTests/formal_install_output'
assert Path.cwd().resolve()==ROOT
SHELL=Path('C:/Program Files/Git/bin/sh.exe')
SOURCES=[HERE/name for name in ('formal-install.sh','formal-restore.sh','formal-prepare-radio.sh.in')]
HASHES={
 'd29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b':b'fixture-gui',
 '2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263':b'fixture-appscommon',
 '988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1':b'fixture-msg2dbus',
 'e5eb76a8b333e402b213843e2e93ff771615adcbc05ca7113d04ef0951555159':b'BASE',
}
FAKE=r'''from pathlib import Path
import json,os,sys,subprocess
r=Path(os.environ['FORMAL_TEST_ROOT']);d=r/'package';service=r/'services';service.mkdir(exist_ok=True)
name=sys.argv[1];args=sys.argv[2:]
with (r/'commands.jsonl').open('a',encoding='utf-8') as log:
 log.write(json.dumps({'command':name,'args':args})+'\n')
def write(p,text):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def state(s): return (service/s).read_text() if (service/s).exists() else 'inactive'
def pid(s): return 101 if s=='victory-gui' else 202
def dropin(s): return r/'run/systemd/system'/(s+'.service.d')/'80-hbl-formal-flash.conf'
def loaded(s):
 number=pid(s);formal=dropin(s).is_file()
 lib='libhbl-formal.so' if s=='victory-gui' else 'libhbl-formal-observer.so'
 write(r/'proc'/str(number)/'maps',(str(d/lib).replace('\\','/')+'\n') if formal else '')
 write(r/'proc'/str(number)/'environ','')
 if formal and s=='msg2dbus-farm':
  write(d/'formal-observer.status','stage=ready meta=1 observe=1\n')
  write(d/'formal-worker.status','formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=202\n')
  write(d/'formal-worker.sock','socket-double')
 if formal and s=='victory-gui':
  write(d/'formal-runtime.status','formal-qml-component-failed\n' if (r/'fail_gui').exists() else 'formal-ui-loaded-default-off\n')
  write(d/'formal-ui.sock','socket-double')
if name=='id': print('0');sys.exit(0)
if name=='stat':
 p=Path(args[-1]);print('1000:777' if (r/'wrong_owner').exists() and p==d else '0:700' if p.is_dir() else '0:600');sys.exit(0)
if name=='systemctl':
 op=args[0]
 if op=='is-active':
  s=args[-1];active=state(s)
  if s=='hostapd' and active=='inactive' and (r/'unit_initial_unknown').exists():
   if '--quiet' not in args:print('unknown')
   sys.exit(1)
  if '--quiet' not in args: print(active)
  sys.exit(0 if active=='active' else 3)
 if op=='show':
  s=args[-1];keys=[args[i+1] for i in range(1,len(args)-1) if args[i]=='-p']
  for key in keys:
   if key=='MainPID':print('MainPID='+str(pid(s)))
   elif key=='LoadState':print('LoadState=not-found' if s=='hostapd' and (r/'unit_not_loaded').exists() else 'LoadState=loaded')
   elif key=='ActiveState':print('ActiveState=unknown' if s=='hostapd' and (r/'unit_unknown_state').exists() else 'ActiveState='+state(s))
   elif key=='Environment':print('Environment=LD_PRELOAD=/unowned.so' if (r/'unknown_preload').exists() else 'Environment=')
   else:sys.exit(91)
  sys.exit(0)
 if op=='daemon-reload':sys.exit(0)
 if op in ('start','restart','stop'):
  for s in args[1:]:
   if op=='start' and s=='network-manager' and (r/'fail_network_restore_once').exists():
    (r/'fail_network_restore_once').unlink();sys.exit(90)
   write(service/s,'inactive' if op=='stop' else 'active')
   if s in ('victory-gui','msg2dbus-farm'):
    if op!='stop':loaded(s)
    else:
     p=d/('formal-ui.sock' if s=='victory-gui' else 'formal-worker.sock')
     if p.exists():p.unlink()
  sys.exit(0)
 sys.exit(91)
if name=='rmmod':
 p=r/'sys/module/brcmfmac/parameters/firmware_path'
 if not p.exists():sys.exit(92)
 p.unlink();sys.exit(0)
if name=='dd':
 # 目标 BusyBox 1.23.2 的受限选项；拒绝 GNU conv 扩展后才执行主机文件复制。
 if any(a.split('=',1)[0] not in ('if','of','bs','count','skip','seek') or '=' not in a for a in args):sys.exit(80)
 sys.exit(subprocess.run([os.environ['FORMAL_TEST_REAL_DD']]+args,close_fds=False).returncode)
if name=='modprobe':
 if (r/'fail_modprobe_once').exists():
  (r/'fail_modprobe_once').unlink();sys.exit(93)
 original='test' if args==['brcmfmac','firmware_path=test'] else ''
 write(r/'sys/module/brcmfmac/parameters/firmware_path',original)
 path=(r/'sys/module/firmware_class/parameters/path').read_bytes().strip(b'\x00\n').decode()
 write(r/'marker','formal' if path==str(d).replace('\\','/') else 'factory')
 sys.exit(0)
if name=='wl':
 if args[:1]==['phyreg']:
  if args==['phyreg','0','b']:print('0x5854' if (r/'marker').read_text()=='formal' else '0x0000')
  elif args==['phyreg','17','b']:print('0x0000')
  else:sys.exit(94)
 elif args not in (['mpc','0'],['band','b'],['up'],['scansuppress','1'],['chanspec','2/20'],['phy_txpwrindex','10','10']):sys.exit(95)
 sys.exit(0)
if name=='sleep':
 if (d/'formal-stop.request').exists() and state('msg2dbus-farm')=='active':
  first='formal-worker-stop-failed' if (r/'stop_fails').exists() else 'formal-worker-stopped-default-off'
  write(d/'formal-worker.status',first+'\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=202\n')
 sys.exit(0)
if name=='formal-netlink-probe':sys.exit(0 if (r/'marker').read_text()=='formal' else 96)
if name=='formal-sync-hook-check':
 sys.exit(0 if os.environ.get('HBL_FORMAL_SYNC_SELFTEST')=='1' and os.environ.get('FORMAL_TEST_PRELOAD','').endswith('libhbl-formal-observer.so') else 97)
if name=='formal-client-check':sys.exit(0 if args==['--check-direct'] else 98)
if name=='formal-system-check':
 if args==['--check']:sys.exit(0)
 if args==['--check-files']:sys.exit(0 if (d/'formal-hold.check').read_text()=='HBL hold file ABI check\n' else 68)
 if args==['--begin-hold']:
  if (r/'not_active').exists():sys.exit(66)
  write(d/'formal-state/hold.deadline','HHD1 1200000\n');sys.exit(0)
 if args==['--require-held']:
  ready=state('victory-gui')=='active' and (d/'formal-runtime.status').exists() and (d/'formal-runtime.status').read_text().strip()=='formal-ui-loaded-default-off'
  sys.exit(0 if ready and not (r/'expired_hold').exists() else 66)
 sys.exit(99)
sys.exit(99)
'''

def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_bytes(data if isinstance(data,bytes) else data.encode('utf-8'))
def make_case(name,original_module='',original_class='/factory-search',net='active',host='inactive',flag=None):
 root=OUT/name
 if root.exists():
  # 只清理本测试确定的目录；根路径和父路径先核对。
  assert root.resolve().parent==OUT.resolve() and root.resolve()!=OUT.resolve()
  shutil.rmtree(root)
 root.mkdir(parents=True)
 d=root/'package';d.mkdir()
 bindir=root/'bin';bindir.mkdir()
 for svc,state in [('victory-gui','active'),('msg2dbus-farm','active'),('network-manager',net),('hostapd',host)]:write(root/'services'/svc,state)
 for pid in ('101','202'):
  write(root/'proc'/pid/'environ','');write(root/'proc'/pid/'maps','')
 write(root/'sys/module/firmware_class/parameters/path',original_class)
 write(root/'sys/module/brcmfmac/parameters/firmware_path',original_module)
 (root/'run/systemd/system').mkdir(parents=True)
 write(root/'usr/bin/victory-gui',b'fixture-gui');write(root/'usr/lib/libappscommon.so.1.0.0',b'fixture-appscommon')
 write(root/'usr/bin/msg2dbus',b'fixture-msg2dbus');write(root/'lib/firmware/test/brcm/brcmfmac4356-pcie.bin',b'BASE')
 write(root/'marker','factory');write(root/'fake.py',FAKE)
 if flag:write(root/flag,'1')
 for cmd in ('id','stat','systemctl','rmmod','modprobe','sleep','wl','dd','formal-sync-hook-check','formal-client-check','formal-netlink-probe','formal-system-check'):
  wrapper='#!/bin/sh\nexec "$FORMAL_TEST_PYTHON" "$FORMAL_TEST_FAKE" '+cmd+' "$@"\n'
  write((d if cmd.startswith('formal-') else bindir)/cmd,wrapper)
 for file in ('libhbl-formal.so','libhbl-formal-observer.so','formal-ui.rcc'):write(d/file,'test fixture only')
 write(d/'formal-hold.check','HBL hold file ABI check\n')
 write(d/'delta/0.bin',b'EST');final=b'BEST'
 replacements={
  '/tmp/hbl-wireless-flash':str(d).replace('\\','/'),
  '/run/systemd/system':str(root/'run/systemd/system').replace('\\','/'),
  '/sys/module':str(root/'sys/module').replace('\\','/'),
  '/proc/':str(root/'proc').replace('\\','/')+'/',
  '/usr/bin/wl':str(bindir/'wl').replace('\\','/'),
  '/usr/bin/victory-gui':str(root/'usr/bin/victory-gui').replace('\\','/'),
  '/usr/lib/libappscommon.so.1.0.0':str(root/'usr/lib/libappscommon.so.1.0.0').replace('\\','/'),
  '/usr/bin/msg2dbus':str(root/'usr/bin/msg2dbus').replace('\\','/'),
  '/lib/firmware/test/brcm/brcmfmac4356-pcie.bin':str(root/'lib/firmware/test/brcm/brcmfmac4356-pcie.bin').replace('\\','/'),
  '@FORMAL_FIRMWARE_SHA256@':sha(final),
  '@FORMAL_DELTA_COMMANDS@':('dd if="$d/delta/0.bin" bs=1 seek=1 conv=notrunc of="$d/test/brcm/brcmfmac4356-pcie.bin" 2>/dev/null' if flag=='unsupported_dd' else
                           'dd if="$d/delta/0.bin" bs=1 seek=1 1<>"$d/test/brcm/brcmfmac4356-pcie.bin" 2>/dev/null'),
 }
 replacements.update({old:sha(data) for old,data in HASHES.items()})
 for source in SOURCES:
  text=source.read_text(encoding='utf-8')
  for old,new in replacements.items():text=text.replace(old,new)
  # Windows shell 的场景验证使用明确普通文件替身；生产 -S 断言独立静态核对。
  text=text.replace('[ -S "$d/formal-worker.sock" ]','[ -f "$d/formal-worker.sock" ]').replace('[ -S "$d/formal-ui.sock" ]','[ -f "$d/formal-ui.sock" ]')
  text=text.replace('HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD=', 'HBL_FORMAL_SYNC_SELFTEST=1 FORMAL_TEST_PRELOAD=')
  write(d/source.name.removesuffix('.in'),text)
 paths=sorted(p for p in d.rglob('*') if p.is_file())
 write(d/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(d).as_posix()+'\n' for p in paths))
 posix_bin='/'+bindir.drive[0].lower()+bindir.as_posix()[2:]
 env=dict(os.environ,FORMAL_TEST_ROOT=str(root),FORMAL_TEST_FAKE=str(root/'fake.py'),FORMAL_TEST_PYTHON=sys.executable,
          FORMAL_TEST_BIN=posix_bin,FORMAL_TEST_REAL_DD=str(SHELL.parents[1]/'usr/bin/dd.exe'))
 env.pop('LD_PRELOAD',None)
 return root,d,env
def execute(case,name,*args):
 root,d,env=case
 if name=='formal-install.sh' and not args:
  first=execute(case,name,'--stage-ui')
  return first if first.returncode else execute(case,name,'--start-observer')
 result=subprocess.run([str(SHELL),'-c','PATH="$FORMAL_TEST_BIN:$PATH"; export PATH; script=$1; shift; . "$script"',
                        'formal-script-simulation',str(d/name),*args],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=50)
 write(root/(name+('-'+args[0].lstrip('-') if args else '')+'.result.json'),json.dumps({'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False,indent=2))
 return result
def commands(root):
 p=root/'commands.jsonl'
 return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
def is_active(root,service):return (root/'services'/service).read_text()=='active'
def run():
 OUT.mkdir(parents=True,exist_ok=True);checks=[]
 def check(label,condition):
  assert condition,label
  checks.append(label)
 for source in SOURCES:
  result=subprocess.run([str(SHELL),'-n',str(source)],capture_output=True,text=True)
  check('POSIX-sh语法-'+source.name,result.returncode==0)
 plain='\n'.join(p.read_text(encoding='utf-8') for p in SOURCES)
 check('生产脚本验证真实socket','[ -S "$d/formal-worker.sock" ]' in plain and '[ -S "$d/formal-ui.sock" ]' in plain)
 check('无独立worker服务或持久配置写入','ExecStart=' not in plain and '/etc/' not in plain)
 check('安装不调用无线发送或hold选择器',all(('phyreg '+str(n)+' ') not in plain for n in [14,26,27,40,48,512]))
 check('模板仅包含约定两个占位',sorted(__import__('re').findall('@[A-Z0-9_]+@',SOURCES[2].read_text(encoding='utf-8')))==['@FORMAL_DELTA_COMMANDS@','@FORMAL_FIRMWARE_SHA256@'])
 for name,module,path,net,host,flag in [('normal-empty','', '/factory-search','active','inactive',None),('normal-test','test','', 'inactive','active',None),
                                     ('unit-initial-unknown','', '/factory-search','active','inactive','unit_initial_unknown')]:
  case=make_case(name,module,path,net,host,flag);root,d,_=case;result=execute(case,'formal-install.sh')
  check(name+'安装成功',result.returncode==0 and (d/'formal-install.status').read_text().strip()=='formal-linux-ready-default-off')
  events=commands(root);names=[e['command'] for e in events]
  check(name+'自检先于卸载驱动',names.index('formal-sync-hook-check')<names.index('formal-client-check')<names.index('rmmod')<names.index('formal-netlink-probe'))
  check(name+'没有发送选择器',all(e['args'] in [['phyreg','0','b'],['phyreg','17','b']] for e in events if e['command']=='wl' and e['args'][:1]==['phyreg']))
  check(name+'两项原始状态及模块路径保存',(d/'formal-state/module-firmware.path').read_text()==module and (d/'formal-state/network-manager.active').read_text().strip()==net and (d/'formal-state/hostapd.active').read_text().strip()==host)
  check(name+'采用loaded及实际ActiveState快照',all(
      (d/'formal-state'/(svc+'.unit')).read_text()=='LoadState=loaded\nActiveState='+value+'\n'
      for svc,value in [('network-manager',net),('hostapd',host)]) and not any(
      e['command']=='systemctl' and e['args'][0]=='is-active' and e['args'][-1] in ('network-manager','hostapd') for e in events))
  check(name+'临时firmware_class恢复',(root/'sys/module/firmware_class/parameters/path').read_bytes().strip(b'\x00')==path.encode())
  result=execute(case,'formal-restore.sh','--after-farm-unhook')
  check(name+'未先停止拒绝最终恢复',result.returncode!=0 and is_active(root,'msg2dbus-farm'))
  before=len(commands(root));result=execute(case,'formal-restore.sh','stop');later=commands(root)[before:]
  check(name+'停止只关闭UI并保留observer',result.returncode==0 and not is_active(root,'victory-gui') and is_active(root,'msg2dbus-farm') and not any(e['command']=='rmmod' for e in later))
  check(name+'停止成功状态准确',(d/'formal-restore.status').read_text().strip()=='formal-linux-stopped-observer-retained')
  result=execute(case,'formal-restore.sh','--after-farm-unhook')
  check(name+'确认解钩后恢复成功',result.returncode==0 and (d/'formal-restore.status').read_text().strip()=='original-linux-services-and-radio-restored')
  check(name+'原服务active状态正确',is_active(root,'victory-gui') and is_active(root,'msg2dbus-farm') and is_active(root,'network-manager')==(net=='active') and is_active(root,'hostapd')==(host=='active'))
  check(name+'原始驱动参数恢复',(root/'sys/module/brcmfmac/parameters/firmware_path').read_text()==module)
  before=len(commands(root));result=execute(case,'formal-restore.sh','--after-farm-unhook')
  check(name+'最终恢复可重入且不重复装卸驱动',result.returncode==0 and not any(e['command'] in ('modprobe','rmmod') for e in commands(root)[before:]))
 for flag in ('unknown_preload','wrong_owner'):
  case=make_case(flag,flag=flag);root,d,_=case;result=execute(case,'formal-install.sh')
  check(flag+'前置拒绝不修改服务驱动',result.returncode!=0 and not (d/'formal-state').exists() and not any(e['command'] in ('modprobe','rmmod') or e['command']=='systemctl' and e['args'][0] in ('stop','start','restart') for e in commands(root)))
 for flag in ('unsupported_dd','unit_not_loaded','unit_unknown_state'):
  case=make_case(flag,flag=flag);root,d,_=case;result=execute(case,'formal-install.sh');events=commands(root)
  check(flag+'拒绝且不启停不存在服务或驱动',result.returncode!=0 and not (d/'formal-state/radio-snapshot-complete').exists() and not (d/'formal-state/radio-mutated').exists() and not any(
      e['command'] in ('rmmod','modprobe') or e['command']=='systemctl' and e['args'][0] in ('start','stop','restart') and e['args'][-1]!='victory-gui' for e in events))
  if flag=='unsupported_dd':check('不支持的dd参数不会截断原始副本',(d/'test/brcm/brcmfmac4356-pcie.bin').read_bytes()==b'BASE')
 case=make_case('stale-enable');root,d,_=case;write(d/'formal-enable.ready','ready\n');result=execute(case,'formal-install.sh')
 check('拒绝旧安装解锁文件且不自行重开',result.returncode!=0 and not (d/'formal-state').exists() and not any(e['command'] in ('modprobe','rmmod') for e in commands(root)))
 case=make_case('corrupt-manifest');root,d,_=case;write(d/'formal-ui.rcc','tampered');result=execute(case,'formal-install.sh')
 check('manifest不符在任何服务修改前拒绝',result.returncode!=0 and not (d/'formal-state').exists() and not any(e['command']=='systemctl' for e in commands(root)))
 for flag in ('fail_modprobe_once','fail_gui'):
  case=make_case(flag,flag=flag);root,d,_=case;result=execute(case,'formal-install.sh')
  check(flag+'失败自动恢复本次修改',result.returncode!=0 and (d/'formal-install.status').read_text().strip()=='formal-install-failed-original-linux-restored' and is_active(root,'victory-gui') and is_active(root,'msg2dbus-farm') and is_active(root,'network-manager') and not is_active(root,'hostapd'))
  check(flag+'失败恢复原始参数',(root/'sys/module/brcmfmac/parameters/firmware_path').read_text()=='' and (root/'sys/module/firmware_class/parameters/path').read_text()=='/factory-search')
 case=make_case('foreign-dropin');root,d,_=case;check('外部变更场景安装',execute(case,'formal-install.sh').returncode==0)
 foreign=root/'run/systemd/system/victory-gui.service.d/80-hbl-formal-flash.conf';write(foreign,'external replacement')
 before=len(commands(root));result=execute(case,'formal-restore.sh','stop')
 check('外部替换dropin原样保留',result.returncode!=0 and foreign.read_text()=='external replacement' and not any(e['command']=='systemctl' and e['args'][0]=='stop' for e in commands(root)[before:]))
 case=make_case('foreign-module');root,d,_=case;check('模块外部变更场景安装',execute(case,'formal-install.sh').returncode==0)
 check('模块外部变更场景先停止',execute(case,'formal-restore.sh','stop').returncode==0)
 write(root/'sys/module/brcmfmac/parameters/firmware_path','');before=len(commands(root));result=execute(case,'formal-restore.sh','--after-farm-unhook')
 check('已注入后外部切换module参数拒绝覆盖',result.returncode!=0 and not any(e['command'] in ('modprobe','rmmod') or e['command']=='systemctl' and e['args'][0]=='stop' for e in commands(root)[before:]))
 case=make_case('partial-network-restore');root,d,_=case;check('部分恢复失败场景安装',execute(case,'formal-install.sh').returncode==0)
 check('部分恢复失败场景先停止',execute(case,'formal-restore.sh','stop').returncode==0)
 write(root/'fail_network_restore_once','1');result=execute(case,'formal-restore.sh','--after-farm-unhook')
 check('原驱动恢复成功独立记录',result.returncode!=0 and (d/'formal-state/radio-original-loaded').exists() and not (d/'formal-state/radio-restored').exists())
 before=len(commands(root));result=execute(case,'formal-restore.sh','--after-farm-unhook')
 check('部分恢复重试不重复装卸原驱动',result.returncode==0 and is_active(root,'network-manager') and not any(e['command'] in ('rmmod','modprobe') for e in commands(root)[before:]))
 case=make_case('stop-failure');root,d,_=case;check('关闭失败场景安装',execute(case,'formal-install.sh').returncode==0);write(root/'stop_fails','1')
 before=len(commands(root));result=execute(case,'formal-restore.sh','stop')
 check('worker真实关闭未确认禁止继续恢复',result.returncode!=0 and not (d/'formal-state/stop-confirmed').exists() and is_active(root,'msg2dbus-farm') and not any(e['command']=='rmmod' for e in commands(root)[before:]))
 case=make_case('held-order');root,d,_=case
 result=execute(case,'formal-install.sh','--stage-ui')
 check('第一阶段仅安装UI保持不操作无线',result.returncode==0 and (d/'formal-state/ui-hold-ready').exists() and not (d/'formal-state/install-complete').exists() and not any(e['command'] in ('rmmod','modprobe','formal-netlink-probe') for e in commands(root)))
 before=len(commands(root));write(root/'expired_hold','1')
 result=execute(case,'formal-install.sh','--start-observer')
 check('保持过期阻止第二阶段且不重启GUI',result.returncode!=0 and not any(e['command'] in ('rmmod','modprobe') or e['command']=='systemctl' and e['args'][0]=='restart' for e in commands(root)[before:]))
 case=make_case('sleeping-start',flag='not_active');root,d,_=case
 result=execute(case,'formal-install.sh','--stage-ui')
 check('当前非Active不安装GUI或驱动',result.returncode!=0 and not any(e['command'] in ('rmmod','modprobe') or e['command']=='systemctl' and e['args'][0]=='restart' for e in commands(root)))
 check('旧无参数安装入口已拒绝','[ "$#" = 1 ] || exit 59' in SOURCES[0].read_text(encoding='utf-8'))
 report={'passed':True,'checkCount':len(checks),'checks':checks,'sourceHashes':{p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in SOURCES+[Path(__file__)]},
         'simulation':'private-filesystem-and-command-doubles-no-device-io','shellSyntax':'Git sh -n','hardwareRequests':0,'radioRequests':0,
         'productionSocketPredicates':'static-checked-test-copies-use-explicit-regular-file-doubles',
         'preloadSimulation':'selftest-copy-uses-FORMAL_TEST_PRELOAD-no-native-library-loading',
         'targetCompatibilityCases':['BusyBox-1.23.2-dd-rejects-conv-before-write','dd-seek-with-readwrite-stdout-preserves-file',
                                     'loaded-inactive-hostapd-with-is-active-unknown','reject-not-loaded-or-unknown-active-state']}
 write(OUT/'validation.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'passed':len(checks),'hardwareRequests':0,'radioRequests':0},ensure_ascii=False))

if __name__=='__main__':run()
