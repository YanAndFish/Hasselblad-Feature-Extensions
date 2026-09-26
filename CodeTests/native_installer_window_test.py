"""Exercise the production no-console launcher with a harmless native child; no USB."""
from pathlib import Path
import json, shutil, subprocess, hashlib

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'x1d/patch-distribution/build/candidate-r41/window-test'
ZIG=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
SOURCE=ROOT/'x1d/patch-distribution/native-client/hidden_process.zig'

def main():
    assert Path.cwd().resolve()==ROOT
    OUT.mkdir(exist_ok=True)
    shutil.copyfile(SOURCE,OUT/'hidden_process.zig')
    (OUT/'probe.cpp').write_text('''#include <windows.h>
#include <stdio.h>
int main(int argc,char **argv){HWND console=GetConsoleWindow(); bool visible=console && IsWindowVisible(console);
printf("visible-console=%s;argc=%d",visible?"yes":"no",argc);for(int i=1;i<argc;++i)printf(";%s",argv[i]);return visible?1:0;}
''',encoding='utf-8')
    (OUT/'harness.zig').write_text('''const std=@import("std");const hidden=@import("hidden_process.zig");
pub fn main() !void {const a=std.heap.page_allocator;const args=try std.process.argsAlloc(a);defer std.process.argsFree(a,args);
const cwd=try std.fs.selfExeDirPathAlloc(a);defer a.free(cwd);
const out=try hidden.run(a,args[1],cwd,&.{"one two","end\\\\","quo\\\"ted"});defer a.free(out);try std.io.getStdOut().writeAll(out);}
''',encoding='utf-8')
    cache=['--cache-dir',str(OUT/'cache'),'--global-cache-dir',str(OUT/'global')]
    probe=OUT/'中文 space probe.exe'; harness=OUT/'hidden-harness.exe'
    subprocess.run([str(ZIG),'c++','-target','x86_64-windows-gnu','-O2',str(OUT/'probe.cpp'),'-luser32','-o',str(probe)],check=True,capture_output=True,timeout=120)
    subprocess.run([str(ZIG),'build-exe',str(OUT/'harness.zig'),'-O','ReleaseSafe','-femit-bin='+str(harness),*cache],check=True,capture_output=True,timeout=120)
    run=subprocess.run([str(harness),str(probe)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=35)
    assert run.returncode==0,(run.stdout,run.stderr)
    assert run.stdout==b'visible-console=no;argc=4;one two;end\\;quo"ted',run.stdout
    result={'passed':True,'hardwareRequests':0,'childHasVisibleConsole':False,'quotedArgumentsPreserved':True,'sourceSha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    (OUT/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
