from pathlib import Path
import os,subprocess,json,hashlib,sys,importlib.util,secrets
P=Path(__file__).resolve().parent;R=P.parents[2];C=R/'.research-cache/x1d-1.25.0';B=C/'baseline';O=P/'build'
def main():
 assert Path.cwd().resolve()==R
 O.mkdir(exist_ok=True);env=dict(os.environ)
 sealed='--sealed-qml' in sys.argv
 experimental_network='--experimental-network' in sys.argv
 seal_lib=None
 seal_id=None
 if sealed:
  sys.path.insert(0,str(P))
  from seal_resources import build as build_seal
  seal_id=secrets.token_hex(16)
  seal_lib=build_seal(key_id=seal_id,create=True)
 distribution=R/'x1d/patch-distribution'
 sys.path.insert(0,str(distribution))
 spec=importlib.util.spec_from_file_location('component_guard_builder',distribution/'build.py')
 guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
 public=guard.lic.openssl('pkey','-in',guard.lic.PRIVATE/'signing-key.pem','-pubout','-outform','DER')
 guardlib=O/'component-guard.a'
 guard.compile_guard(public,guardlib,library=True)
 for k,n in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
  d=O/n;d.mkdir(exist_ok=True);env[k]=str(d)
 inc=O/'include/QtCore';inc.mkdir(parents=True,exist_ok=True)
 (inc/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n')
 (inc/'qfeatures.h').write_text('/* Qt5.5 */\n')
 qt=C/'qt-public';base=qt/'qtbase-opensource-src-5.5.1';zig=C/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
 target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
 flags=target+['-I',str(base/'src/3rdparty/angle/include'),'-marm','-O2','-fPIC','-fno-stack-protector','-I',str(O/'include'),'-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion']
 if sealed:flags+=['-DHBL_SEALED_UI=1']
 if experimental_network:flags+=['-DHBL_EXPERIMENTAL_NETWORK=1']
 layout=O/'relocations.ld';layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
 # Only the three Qt interposition entry points are public ABI. Internal C++
 # helpers must not become a readable map of the native business state machine.
 exports=['_ZN9QResource16registerResourceERK7QStringS2_',
          '_ZN8QProcess5startERK7QStringRK11QStringList6QFlagsIN9QIODevice12OpenModeFlagEE',
          '_ZN21QQmlApplicationEngine4loadERK4QUrl']
 export_map=O/'entry-exports.map'
 export_map.write_text('{ global:\n'+''.join(' '+symbol+';\n' for symbol in exports)+' local: *;\n};\n')
 libs=[B/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ['Quick','Qml','Gui','Network','Core']]+[B/n for n in ['usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so']]
 replay=[]
 for source,language in [(P/'jpeg_provider.cpp','c++'),(R/'x1d/candidates/replay-reader/native/jpeg_container.c','cc')]:
  obj=O/(source.stem+'.o')
  r=subprocess.run([str(zig),language,'-std=c++11' if language=='c++' else '-std=c11']+flags+['-c',str(source),'-o',str(obj)],env=env,capture_output=True,text=True,timeout=90)
  if r.returncode:raise RuntimeError(r.stderr)
  replay.append(str(obj))
 for name,source,shared in [('hotspot-ui','main.cpp',False),('libhotspot-entry.so','entry.cpp',True)]:
  if not shared and not experimental_network:continue
  obj=O/(name+'.o')
  extra=[str(guardlib)]+[str(B/'usr/lib/libQt5DBus.so.5.5.1'),str(B/'usr/lib/libappscommon.so.1.0.0')] if shared else []
  if shared and seal_lib:extra+=[str(seal_lib)]
  linkage=['-Wl,--version-script='+str(export_map)] if shared else []
  for cmd in [['c++','-std=c++11']+flags+['-c',str(P/source),'-o',str(obj)],['cc']+target+['-shared' if shared else '-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),str(obj)]+linkage+extra+[str(p) for p in libs]+['-o',str(O/name)]]:
   r=subprocess.run([str(zig)]+cmd,env=env,capture_output=True,text=True,timeout=90)
   if r.returncode:raise RuntimeError(r.stderr)
 radio=(P/'radio-mode.sh').read_bytes().replace(b'\r\n',b'\n')
 if experimental_network:
  for name in ['Main.qml','Entry.qml','network.sh']:(O/name).write_bytes((P/name).read_bytes().replace(b'\r\n',b'\n'))
  (O/'dhcp.sh').write_bytes((P.parent/'hotspot-dhcp.sh').read_bytes().replace(b'/run/hbl-hotspot-test',b'/run/hbl-hotspot-ui').replace(b'\r\n',b'\n'))
 else:
  block=b'if [ -f /run/hbl-hotspot-ui/started ];then\n    /bin/sh /run/hbl-hotspot-ui/network.sh restore || exit 71\nfi\n'
  assert radio.count(block)==1, 'Experimental network cleanup boundary changed'
  radio=radio.replace(block,b'')
 (O/'radio-mode.sh').write_bytes(radio)
 names=['libhotspot-entry.so','radio-mode.sh']
 if experimental_network:names+=['hotspot-ui','Main.qml','Entry.qml','network.sh','dhcp.sh']
 if (O/'flash-ui.rcc').exists():names.append('flash-ui.rcc')
 files={n:hashlib.sha256((O/n).read_bytes()).hexdigest() for n in names}
 (O/'manifest.sha256').write_text(''.join(h+'  '+n+'\n' for n,h in files.items()),newline='\n')
 sources={str(path.relative_to(R)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(P.glob('*.h'))}
 for name in ['entry.cpp','main.cpp','build.py','build_flash_preview.py','seal_resources.py','radio-mode.sh']:
  path=P/name;sources[str(path.relative_to(R)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
 sys.path.insert(0,str(C/'python'))
 from elftools.elf.elffile import ELFFile
 import io
 elf=ELFFile(io.BytesIO((O/'libhotspot-entry.so').read_bytes()))
 actual_exports=[symbol.name for symbol in elf.get_section_by_name('.dynsym').iter_symbols()
                 if symbol.name and symbol['st_shndx']!='SHN_UNDEF'
                 and symbol['st_info']['bind'] in ('STB_GLOBAL','STB_WEAK')
                 and symbol['st_other']['visibility']=='STV_DEFAULT']
 assert sorted(actual_exports)==sorted(exports), 'Unexpected native implementation exports'
 assert not any(section.name.startswith('.debug') or section.name=='.symtab' for section in elf.iter_sections())
 binary=(O/'libhotspot-entry.so').read_bytes()
 if not experimental_network:
  for marker in [b'temporaryHotspotEntry',b'panel-created-waiting-wifi-page',b'/ctrl/wlp1s0',b'network.sh',b'dhcp.sh']:
   assert marker not in binary and marker.decode('ascii').encode('utf-16le') not in binary, 'Experimental network code leaked into production native entry'
 (O/'build.json').write_text(json.dumps({'compiled':True,'hardwareValidated':False,'sealedQml':sealed,'experimentalNetwork':experimental_network,'resourceSealId':seal_id,'files':files,'sources':sources,'definedExports':actual_exports,'debugSymbolsRemoved':True},indent=2))
 print('Temporary UI compiled; not installed')
if __name__=='__main__':main()
