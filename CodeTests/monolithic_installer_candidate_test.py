"""单进程 GUI/安装/验签候选；只执行界面自测与离线验包，不访问 USB。"""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'x1d/patch-distribution'
sys.path.insert(0, str(P))
import licensing as lic
import build


def run(args, timeout=180):
    return subprocess.run(list(map(str, args)), cwd=ROOT, capture_output=True,
                          timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    assert Path.cwd().resolve() == ROOT
    out = P / 'build/monolithic-installer-candidate' / str(time.time_ns())
    source = out / 'source'
    source.mkdir(parents=True)
    for f in (P / 'native-client').glob('*.zig'):
        (source / f.name).write_bytes(f.read_bytes())
    public = lic.openssl('pkey', '-in', lic.PRIVATE / 'signing-key.pem', '-pubout', '-outform', 'DER')
    assert len(public) == 44 and public[:12] == bytes.fromhex('302a300506032b6570032100')
    (source / 'release_config.zig').write_text('pub const public_key: [32]u8 = .{' + ','.join(map(str, public[12:])) + '};\n')
    verifier = (P / 'release_guard.zig').read_text(encoding='utf-8').split('\nfn run() !void {')[0]
    verifier = verifier.replace('fn verifySignature(', 'pub fn verifySignature(').replace('fn verifyClient(', 'pub fn verifyClient(')
    begin = verifier.index('    const components = ')
    end = verifier.index('    // A signed file list', begin)
    verifier = verifier[:begin] + '''    // 候选专用单程序配置，无可替换 helper 或解释器。
    inline for (.{"X1D整合候选.exe", "x1d-authorized-candidate.tgz", "release.sig", "build-report.json"}) |required| {
        if (!seen.contains(required)) return error.Incomplete;
    }
    var names = seen.keyIterator();
    while (names.next()) |entry| {
        const name = entry.*;
        if (std.mem.startsWith(u8, name, "components/") or std.mem.startsWith(u8, name, "runtime/")) return error.NativeProfile;
        if (std.ascii.endsWithIgnoreCase(name, ".exe") and !std.mem.eql(u8, name, "X1D整合候选.exe")) return error.NativeProfile;
        inline for (.{".py", ".pyc", ".pyd", ".ps1", ".vbs", ".cmd", ".bat", ".dll"}) |extension| {
            if (std.ascii.endsWithIgnoreCase(name, extension)) return error.NativeProfile;
        }
    }
''' + verifier[end:]
    (source / 'release_verifier.zig').write_text(verifier, encoding='utf-8')
    core = (source / 'native_installer_main.zig').read_text(encoding='utf-8')
    begin = core.index('pub const Gate = struct {')
    end = core.index('\npub const Reporter = struct {', begin)
    core = core[:begin] + 'pub const Gate = @import("integrated_gate.zig").Gate;\n' + core[end:]
    core = core.replace('const hidden_process = @import("hidden_process.zig");', '''const Sink = *const fn ([*]const u8, usize) callconv(.C) void;
var sink: ?Sink = null;
fn writeOutput(_: void, bytes: []const u8) error{}!usize {
    if (sink) |callback| callback(bytes.ptr, bytes.len);
    return bytes.len;
}
fn outputWriter() std.io.Writer(void, error{}, writeOutput) { return .{.context = {}}; }''')
    begin = core.index('fn run() !void {')
    end = core.index('    var gate = Gate{', begin)
    core = core[:begin] + 'fn runIntegrated(action_text: []const u8, directory: []const u8) !void {\n    const action = try parseAction(action_text);\n' + core[end:]
    begin = core.index('pub fn main() void {')
    core = core[:begin] + '''export fn hbl_installer_run(action: [*:0]const u8, directory: [*:0]const u8, callback: Sink) callconv(.C) c_int {
    sink = callback;
    defer sink = null;
    runIntegrated(std.mem.span(action), std.mem.span(directory)) catch |failure| {
        outputWriter().print("操作停止：{s}\\n", .{@errorName(failure)}) catch {};
        return 1;
    };
    return 0;
}
'''
    core = core.replace('std.io.getStdOut().writer()', 'outputWriter()')
    (source / 'integrated_installer.zig').write_text(core, encoding='utf-8')
    library = out / 'installer.lib'
    result = run([build.ZIG, 'build-lib', source / 'integrated_installer.zig', '-target', 'x86_64-windows-gnu', '-O', 'ReleaseSafe', '-fstrip', '-femit-bin=' + str(library)])
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    ui = (P / 'native_client_ui.cpp').read_text(encoding='utf-8')
    begin = ui.index('static bool process(')
    end = ui.index('static std::wstring failureReason(', begin)
    ui = ui[:begin] + '''extern "C" int hbl_installer_run(const char*, const char*, void (*)(const char*, size_t));
static std::string nativeOutput;
static ULONGLONG lastNativeProgress=0;
static void nativeSink(const char *text,size_t length){
 if(nativeOutput.size()+length<=131072)nativeOutput.append(text,length);
 auto now=GetTickCount64();
 if(mainWindow&&now-lastNativeProgress>=100){
  auto snapshot=new std::wstring(wide(nativeOutput));
  if(!PostMessage(mainWindow,progressMessage,0,LPARAM(snapshot)))delete snapshot;
  lastNativeProgress=now;
 }
}
static DWORD WINAPI worker(void *raw){
 std::unique_ptr<Action> task(static_cast<Action*>(raw));
 nativeOutput.clear();lastNativeProgress=0;
 const auto action=utf8(actions[task->index]),path=utf8(directory);
 const int code=hbl_installer_run(action.c_str(),path.c_str(),nativeSink);
 auto result=new Result{DWORD(code),task->index==0&&code==0&&nativeOutput.find("DEVICE_READY=1\\n")!=std::string::npos,wide(nativeOutput)};
 if(!PostMessage(mainWindow,finishedMessage,WPARAM(task->index),LPARAM(result)))delete result;
 return 0;
}
''' + ui[end:]
    ui = ui.replace('if(*args&&!testing)return 2;', 'if(*args&&!testing&&std::wstring(args)!=L"--check-package")return 2;')
    anchor = 'directory.resize(slash);'
    ui = ui.replace(anchor, anchor + '''
 if(std::wstring(args)==L"--check-package"){
   const auto path=utf8(directory);nativeOutput.clear();
   const int code=hbl_installer_run("check-package",path.c_str(),nativeSink);
   std::fwrite(nativeOutput.data(),1,nativeOutput.size(),stdout);return code;
 }
''', 1)
    ui = ui.replace('X1D R41', 'X1D 整合候选').replace('R41  /', '整合候选  /')
    (source / 'integrated_ui.cpp').write_text(ui, encoding='utf-8')
    package = out / 'package'
    package.mkdir()
    exe = package / 'X1D整合候选.exe'
    result = run([build.ZIG, 'c++', '-target', 'x86_64-windows-gnu', '-std=c++17', '-O2', '-s', '-mwindows', '-municode', '-Wl,/subsystem:windows', '-static', source / 'integrated_ui.cpp', library, '-luser32', '-lgdi32', '-lcomctl32', '-lntdll', '-ladvapi32', '-o', exe])
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    binary = exe.read_bytes()
    assert struct.unpack_from('<H', binary, struct.unpack_from('<I', binary, 60)[0] + 24 + 68)[0] == 2
    result = run([exe, '--self-test'])
    assert result.returncode == 0 and json.loads(result.stdout)['passed'], result.stdout
    with zipfile.ZipFile(P / 'build/candidate-r41/X1D-R41-安装包.zip') as archive:
        for name in ['x1d-authorized-candidate.tgz', 'release.sig', 'build-report.json']:
            (package / name).write_bytes(archive.read('X1D-R41-安装包/' + name))

    def sign():
        manifest = ''.join(hashlib.sha256(f.read_bytes()).hexdigest() + '  ' + f.name + '\n' for f in sorted(package.iterdir()) if f.is_file() and f.name not in ['client.sig', 'client.manifest'])
        (package / 'client.manifest').write_bytes(manifest.encode('utf-8'))
        message = out / 'manifest-message'
        message.write_bytes(b'HBL-X1D-CLIENT-V1\0' + hashlib.sha256(manifest.encode()).digest())
        (package / 'client.sig').write_bytes(lic.openssl('pkeyutl', '-sign', '-rawin', '-inkey', lic.PRIVATE / 'signing-key.pem', '-in', message))

    cases = []
    def check(name, passed):
        result = run([exe, '--check-package'])
        assert (result.returncode == 0) == passed, (name, result.stdout, result.stderr)
        cases.append({'name': name, 'accepted': passed})
    sign()
    check('complete_single_program', True)
    # 没有外部guard可替换；额外放入helper也不能成为有效入口。
    injected = package / 'release-guard.exe'
    injected.write_bytes(b'not an executable')
    check('unsigned_extra_guard', False)
    sign()
    check('signed_extra_guard_rejected_by_profile', False)
    # 保留攻击副本证据，移出候选包后重新签名，不删除文件。
    injected.rename(out / 'rejected-extra-guard.bin')
    sign()
    check('restored_single_program', True)
    report = {'passed': True, 'candidateOnly': True, 'hardwareRequests': 0,
              'productionPackageChanged': False, 'guiSubsystem': 2, 'runtimeExecutables': 1,
              'guiCoreVerifierIntegrated': True, 'cases': cases,
              'binarySha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
              'sources': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in source.iterdir() if f.suffix in ['.zig', '.cpp']},
              'limitations': ['No device test', 'No independent attack test', 'Whole native binary remains patchable', 'Not full UI business migration']}
    (out / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, 'report': str(out / 'validation.json')}))


if __name__ == '__main__':
    main()
