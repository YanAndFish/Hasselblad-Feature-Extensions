// 第一代 X2D 100C 的有限 WinUSB 桥。默认不打开设备；不载入官方客户端 DLL。
// 协议依据：官方 X2D 4.2.0 phocus/msg2dbus + Phocus PC 4.1.1。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;

namespace X2DAdbCheck {
    public sealed class UsbFailure : Exception {
        public string Code;
        public int Win32;
        public UsbFailure(string code, int error = 0) : base(code) { Code = code; Win32 = error; }
    }
    public sealed class WireValue { public int Id; public string Encoded; }
    public sealed class ReadStep {
        public int Id, Sequence, ReplyBytes;
        public bool WriteCompleted, ReplyCompleted;
        public long ElapsedMs;
    }
    public sealed class ReadResult {
        public bool Ok, Opened, Closed;
        public int Requests, ReplyBytes, Win32;
        public long ElapsedMs;
        public string Error = "", Stage = "enumerate";
        public int InterfaceNumber = -1, PipeIn = -1, PipeOut = -1;
        public List<WireValue> Values = new List<WireValue>();
        public List<ReadStep> Steps = new List<ReadStep>();
    }
    public sealed class ProbeResult { public int MatchingInterfaces; public bool Opened = false; public int Requests = 0; }

    public static class ReadOnlyProtocol {
        public static byte[] ControlPipes(byte[] descriptorOrder) {
            // X2D 4.2.0 FunctionFS: ep1=数据 OUT、ep2=控制 OUT、ep3=数据 IN、ep4=控制 IN。
            // PC 控制虚表 +0x68 -> 0x1805bab50 -> +0xc9，接收 mode0 -> +0xc8。
            if (descriptorOrder == null || descriptorOrder.Length != 4) throw new UsbFailure("USB_PIPE_MISMATCH");
            HashSet<byte> seen = new HashSet<byte>();
            for (int index = 0; index < 4; index++) {
                byte id = descriptorOrder[index];
                if ((id & 0x0f) == 0 || (id & 0x70) != 0 || ((id & 0x80) != 0) != (index >= 2) || !seen.Add(id))
                    throw new UsbFailure("USB_PIPE_MISMATCH");
            }
            return new byte[] { descriptorOrder[3], descriptorOrder[1] }; // IN、OUT；只选控制角色。
        }
        public static byte[] Request(ushort id, ushort sequence) {
            // 即使上层传入其他 ID，也不能发送。命令类型固定为 ReadParameter (2)。
            if ((id != 27 && id != 28 && id != 25 && id != 87 && id != 88 && id != 61) || sequence == 0) throw new UsbFailure("USB_REQUEST_DENIED");
            return new byte[] { 4, 0, 8, 5, 5, (byte)sequence, (byte)(sequence >> 8), 2, (byte)id, (byte)(id >> 8) };
        }
        public static bool ReviewedValue(ushort id, byte[] value) {
            if (value == null || value.Length == 0 || value.Length > 100) return false;
            foreach (byte ch in value) if (ch < 32 || ch > 126) return false;
            string text = Encoding.ASCII.GetString(value);
            if (id == 27) {
                Match match = Regex.Match(text, @"\AS([2-9]|[1-9]\d),(v?\d{1,3}(?:\.\d{1,3}){1,4})\z");
                return match.Success && int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture) == match.Groups[2].Value.Length;
            }
            if (id == 25) {
                int seconds;
                return Regex.IsMatch(text, @"\Ai(?:0|[1-9]\d{0,3})\z") && int.TryParse(text.Substring(1), out seconds) && seconds <= 3600;
            }
            if (id == 87) {
                ulong bits;
                if (!Regex.IsMatch(text, @"\Af(?:0|[1-9a-f][0-9a-f]{0,15})\z")
                    || !ulong.TryParse(text.Substring(1), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out bits)) return false;
                double ev = BitConverter.Int64BitsToDouble(unchecked((long)bits));
                return !double.IsNaN(ev) && !double.IsInfinity(ev) && Math.Abs(ev) <= 100 && Math.Abs(ev * 12 - Math.Round(ev * 12)) < 1e-8;
            }
            return (id == 28 || id == 88 || id == 61) && (text == "i0" || text == "i1");
        }
        // 可用人工委托验证停止条件，不打开任何设备。调用者不能指定批次或命令。
        public static void Collect(Func<ushort, ushort, byte[]> read, ReadResult result) {
            ushort sequence = 1;
            foreach (ushort id in new ushort[] { 27, 28, 25, 87, 88, 61 }) {
                byte[] value = read(id, sequence++);
                try {
                    result.Values.Add(new WireValue { Id = id, Encoded = Convert.ToBase64String(value) });
                    if (!ReviewedValue(id, value)) throw new UsbFailure("USB_VALUE_UNREVIEWED");
                    string text = Encoding.ASCII.GetString(value);
                    if (id == 27 && text != "S5,4.2.0" && text != "S6,v4.2.0") throw new UsbFailure("USB_FIRMWARE_MISMATCH");
                    if (id == 28 && text != "i1") throw new UsbFailure("USB_CAMERA_NOT_RUNNING");
                } finally { Array.Clear(value, 0, value.Length); }
            }
        }
        public sealed class Reply {
            private readonly ushort expected;
            private readonly List<byte> inner = new List<byte>();
            private bool completed;
            public Reply(ushort sequence) { expected = sequence; }
            public byte[] Add(byte[] packet, int count) {
                if (completed || count < 5 || count > 1024 || count > packet.Length) throw new UsbFailure("USB_FRAME_LENGTH");
                if (packet[0] != 3 || packet[1] != 0 || packet[2] != 5 || packet[3] != 8) throw new UsbFailure("USB_REPLY_ROUTE");
                int length = packet[4] == 0 ? 255 : packet[4];
                if (count < 5 + length || inner.Count + length > 603) throw new UsbFailure("USB_FRAME_LENGTH");
                // 固件将控制回包补至 1024 字节；补齐区不进入解析器、日志或 IPC。
                for (int i = 0; i < length; i++) inner.Add(packet[5 + i]);
                if (packet[4] == 0) return null;
                completed = true;
                if (inner.Count < 3 || (inner[0] | inner[1] << 8) != expected) throw new UsbFailure("USB_REPLY_SEQUENCE");
                if (inner[2] != 0x82) throw new UsbFailure("USB_REPLY_TYPE");
                byte[] value = inner.GetRange(3, inner.Count - 3).ToArray();
                inner.Clear();
                return value;
            }
        }
    }

    public sealed class AdbUsbCheck : IDisposable {
        private static readonly Guid InterfaceGuid = new Guid("F72FE0D4-CBCB-407d-8814-9ED673D0DD6B");
        private SafeFileHandle file;
        private IntPtr usb;
        private byte pipeIn, pipeOut;
        private bool released = true;
        private int releaseError;
        public bool ClosedCleanly { get { return released && releaseError == 0; } }

        [StructLayout(LayoutKind.Sequential)] private struct InterfaceData { public int Size; public Guid ClassGuid; public int Flags; public IntPtr Reserved; }
        [StructLayout(LayoutKind.Sequential, Pack = 1)] private struct UsbInterface {
            public byte Length, DescriptorType, Number, Alternate, EndpointCount, Class, Subclass, Protocol, StringIndex;
        }
        [StructLayout(LayoutKind.Sequential)] private struct PipeInfo { public int Type; public byte Id; public ushort PacketSize; public byte Interval; }
        [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr SetupDiGetClassDevsW(ref Guid guid, string enumerator, IntPtr parent, uint flags);
        [DllImport("setupapi.dll", SetLastError = true)] private static extern bool SetupDiEnumDeviceInterfaces(IntPtr set, IntPtr device, ref Guid guid, uint index, ref InterfaceData data);
        [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool SetupDiGetDeviceInterfaceDetailW(IntPtr set, ref InterfaceData data, IntPtr detail, uint size, out uint required, IntPtr device);
        [DllImport("setupapi.dll", SetLastError = true)] private static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("winusb.dll", SetLastError = true)] private static extern bool WinUsb_Initialize(SafeFileHandle file, out IntPtr handle);
        [DllImport("winusb.dll", SetLastError = true)] private static extern bool WinUsb_Free(IntPtr handle);
        [DllImport("winusb.dll", SetLastError = true)] private static extern bool WinUsb_QueryInterfaceSettings(IntPtr handle, byte alternate, out UsbInterface descriptor);
        [DllImport("winusb.dll", SetLastError = true)] private static extern bool WinUsb_QueryPipe(IntPtr handle, byte alternate, byte index, out PipeInfo pipe);
        [DllImport("winusb.dll", SetLastError = true)] private static extern bool WinUsb_SetPipePolicy(IntPtr handle, byte pipe, uint policy, uint size, ref uint value);
        [DllImport("winusb.dll", SetLastError = true)] private static extern bool WinUsb_WritePipe(IntPtr handle, byte pipe, byte[] data, uint count, out uint transferred, IntPtr overlapped);
        [DllImport("winusb.dll", SetLastError = true)] private static extern bool WinUsb_ReadPipe(IntPtr handle, byte pipe, byte[] data, uint count, out uint transferred, IntPtr overlapped);

        private static void Check(bool ok, string code) { if (!ok) throw new UsbFailure(code, Marshal.GetLastWin32Error()); }
        private static List<string> Enumerate() {
            Guid guid = InterfaceGuid;
            IntPtr set = SetupDiGetClassDevsW(ref guid, null, IntPtr.Zero, 0x12); // PRESENT | DEVICEINTERFACE，只读系统元数据。
            if (set == new IntPtr(-1)) throw new UsbFailure("USB_ENUMERATE", Marshal.GetLastWin32Error());
            List<string> paths = new List<string>();
            try {
                for (uint index = 0; index < 128; index++) {
                    InterfaceData item = new InterfaceData(); item.Size = Marshal.SizeOf(typeof(InterfaceData));
                    if (!SetupDiEnumDeviceInterfaces(set, IntPtr.Zero, ref guid, index, ref item)) {
                        int error = Marshal.GetLastWin32Error();
                        if (error == 259) return paths;
                        throw new UsbFailure("USB_ENUMERATE", error);
                    }
                    uint required;
                    SetupDiGetDeviceInterfaceDetailW(set, ref item, IntPtr.Zero, 0, out required, IntPtr.Zero);
                    if (required < 8 || required > 4096) throw new UsbFailure("USB_ENUMERATE");
                    IntPtr buffer = Marshal.AllocHGlobal((int)required);
                    try {
                        Marshal.WriteInt32(buffer, IntPtr.Size == 8 ? 8 : 6);
                        Check(SetupDiGetDeviceInterfaceDetailW(set, ref item, buffer, required, out required, IntPtr.Zero), "USB_ENUMERATE");
                        string devicePath = Marshal.PtrToStringUni(IntPtr.Add(buffer, 4));
                        if (devicePath != null && devicePath.StartsWith(@"\\?\usb#vid_2756&pid_0009&mi_06#", StringComparison.OrdinalIgnoreCase)
                            && devicePath.EndsWith("#{" + InterfaceGuid.ToString() + "}", StringComparison.OrdinalIgnoreCase)) paths.Add(devicePath);
                        // 唯一设备路径只在本进程内用于打开，绝不输出。
                    } finally { Marshal.FreeHGlobal(buffer); }
                }
                throw new UsbFailure("USB_ENUMERATE_LIMIT");
            } finally { SetupDiDestroyDeviceInfoList(set); }
        }
        public static ProbeResult Probe() { return new ProbeResult { MatchingInterfaces = Enumerate().Count }; }

        private void Open(ReadResult result) {
            List<string> paths = Enumerate();
            if (paths.Count == 0) throw new UsbFailure("USB_NOT_PRESENT");
            if (paths.Count != 1) throw new UsbFailure("USB_AMBIGUOUS");
            result.Stage = "open";
            file = CreateFileW(paths[0], 0xc0000000, 3, IntPtr.Zero, 3, 0x40000080, IntPtr.Zero);
            if (file.IsInvalid) throw new UsbFailure("USB_OPEN", Marshal.GetLastWin32Error());
            result.Opened = true;
            Check(WinUsb_Initialize(file, out usb), "USB_INITIALIZE");
            result.Stage = "interface";
            UsbInterface descriptor;
            Check(WinUsb_QueryInterfaceSettings(usb, 0, out descriptor), "USB_INTERFACE");
            if (descriptor.Number != 6 || descriptor.Alternate != 0 || descriptor.Class != 255 || descriptor.Subclass != 66 || descriptor.Protocol != 1
                || descriptor.EndpointCount != 2) throw new UsbFailure("USB_INTERFACE_MISMATCH");
            result.InterfaceNumber = descriptor.Number;
            byte[] pipeOrder = new byte[2];
            for (byte index = 0; index < descriptor.EndpointCount; index++) {
                PipeInfo pipe;
                Check(WinUsb_QueryPipe(usb, 0, index, out pipe), "USB_PIPE");
                if (pipe.Type != 2) throw new UsbFailure("USB_PIPE_MISMATCH");
                pipeOrder[index] = pipe.Id;
            }
            if ((pipeOrder[0] & 128) == (pipeOrder[1] & 128)) throw new UsbFailure("ADB_ENDPOINTS");
            byte[] control = (pipeOrder[0] & 128) != 0 ? pipeOrder : new byte[] {pipeOrder[1],pipeOrder[0]};
            pipeIn = control[0]; pipeOut = control[1];
            result.PipeIn = pipeIn; result.PipeOut = pipeOut;
            uint timeout = 2000;
            // 仅设置本次主机句柄的 I/O 超时；不设置 USB 接口/相机参数、不复位端点。
            Check(WinUsb_SetPipePolicy(usb, pipeIn, 3, 4, ref timeout), "USB_TIMEOUT_POLICY");
            Check(WinUsb_SetPipePolicy(usb, pipeOut, 3, 4, ref timeout), "USB_TIMEOUT_POLICY");
        }
        private static uint Cmd(string name) { return BitConverter.ToUInt32(Encoding.ASCII.GetBytes(name),0); }
        private void WriteBytes(byte[] bytes) {
            uint sent;Check(WinUsb_WritePipe(usb,pipeOut,bytes,(uint)bytes.Length,out sent,IntPtr.Zero),"ADB_WRITE");
            if(sent!=bytes.Length)throw new UsbFailure("ADB_SHORT_WRITE");
        }
        private void Send(string command,uint a,uint b,byte[] payload) {
            byte[] header=new byte[24];uint checksum=0;foreach(byte item in payload)checksum+=item;
            uint c=Cmd(command);uint[] fields={c,a,b,(uint)payload.Length,checksum,c^0xffffffff};
            for(int i=0;i<6;i++)Array.Copy(BitConverter.GetBytes(fields[i]),0,header,4*i,4);
            WriteBytes(header);if(payload.Length>0)WriteBytes(payload);
        }
        private byte[] ReceiveExact(int length) {
            if(length<0||length>4096)throw new UsbFailure("ADB_LENGTH");
            byte[] result=new byte[length];int offset=0;
            while(offset<length){byte[] piece=new byte[length-offset];uint got;
                Check(WinUsb_ReadPipe(usb,pipeIn,piece,(uint)piece.Length,out got,IntPtr.Zero),"ADB_READ");
                if(got==0||got>piece.Length)throw new UsbFailure("ADB_SHORT_READ");
                Array.Copy(piece,0,result,offset,(int)got);offset+=(int)got;
            }return result;
        }
        private sealed class Packet {public uint Command,A,B;public byte[] Data;}
        private Packet Receive() {
            byte[] h=ReceiveExact(24);uint cmd=BitConverter.ToUInt32(h,0),size=BitConverter.ToUInt32(h,12);
            if((cmd^0xffffffff)!=BitConverter.ToUInt32(h,20)||size>4096)throw new UsbFailure("ADB_HEADER");
            byte[] data=ReceiveExact((int)size);uint sum=0;foreach(byte v in data)sum+=v;
            if(sum!=BitConverter.ToUInt32(h,16))throw new UsbFailure("ADB_CHECKSUM");
            return new Packet {Command=cmd,A=BitConverter.ToUInt32(h,4),B=BitConverter.ToUInt32(h,8),Data=data};
        }
        // Standard ADB handshake only. AUTH stops; no credentials generated or guessed.
        // Query remains fixed and read-only. The separately named remount probe is
        // a mutation and requires explicit authorization for that operation.
        public static string Query() {
            return RunShell("id;cat /proc/self/attr/current;cat /sys/fs/selinux/enforce;grep -E 'CapEff|CapBnd' /proc/self/status;cat /proc/mounts | grep -E ' /system | /vendor ';getprop ro.boot.verifiedbootstate;getprop ro.boot.veritymode;getprop ro.boot.vbmeta.device_state;cat /proc/cmdline | tr ' ' '\\n' | grep -E '^(androidboot\\.(veritymode|verifiedbootstate|vbmeta\\.device_state|flash\\.locked)|veritymode|verifiedbootstate|dm)=';ls /system/bin/avbctl /dev/block/by-name/vbmeta* /sys/block/dm-*/dm/name 2>/dev/null;true;");
        }
        public static string ProbeSystemRemount() {
            // Baseline must be the already observed read-only ext4 system_2.
            // No regular file is created or modified. A camera-local watchdog
            // restores read-only even if the host disconnects after the request.
            return RunShell(@"[ ""$(id -u)"" = 0 ] || exit 31
[ ""$(cat /proc/self/attr/current)"" = u:r:su:s0 ] || exit 32
state() {
    while read -r dev path fs options rest; do
        if [ ""$path"" = /system ]; then printf '%s %s %s\n' ""$dev"" ""$fs"" ""$options""; fi
    done < /proc/mounts
}
original=$(state)
case ""$original"" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
restore() {
    case ""$(state)"" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac
}
trap restore EXIT HUP INT TERM
( /system/bin/sleep 5; restore ) </dev/null >/dev/null 2>&1 &
echo BEFORE; state
/system/bin/mount -o remount,rw /system
echo RW_COMMAND_RESULT=$?
echo AFTER_RW; state
restore
echo AFTER_RESTORE; state
[ ""$(state)"" = ""$original"" ] && echo RESTORED_EXACT || echo RESTORE_MISMATCH
");
        }
        public static string InspectRemountTools() {
            return RunShell("id;cat /proc/self/attr/current;ls -l /system/bin/mount /system/bin/sleep /system/bin/toybox /system/xbin/busybox /sbin/busybox;cat /proc/mounts | grep ' /system ';true;");
        }
        // Explicitly authorized diagnostic library placement, not a boot install.
        public static string InstallDiagnosticLibrary() {
            return RunShell(@"set -u
[ ""$(id -u)"" = 0 ] && [ ""$(cat /proc/self/attr/current)"" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ ""$path"" != /system ] || printf '%s %s %s\n' ""$dev"" ""$fs"" ""$options""; done < /proc/mounts; }
original=$(state)
case ""$original"" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
target=/system/lib64/libx2d_preview_probe.so
source=/blackbox/x2d-autoload-probe/libx2d_preview_probe.so
expected=8735037ab1fa050f27e155acf9eee85719d31588e72d82815b824a9e62ba9106
[ ! -e ""$target"" ] && [ ! -L ""$target"" ] || exit 34
set -- $(/system/bin/sha256sum ""$source"")
[ ""${1:-none}"" = ""$expected"" ] || exit 35
restore() { case ""$(state)"" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
success=0
created=0
finish() { if [ ""$success"" = 0 ] && [ ""$created"" = 1 ]; then /system/bin/rm -f ""$target""; fi; restore; }
trap finish EXIT HUP INT TERM
( /system/bin/sleep 5; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system || exit 36
( set -C; : > ""$target"" ) || exit 37
created=1
/system/bin/cat ""$source"" > ""$target"" || exit 38
/system/bin/chmod 0644 ""$target"" || exit 39
set -- $(/system/bin/sha256sum ""$target"")
[ ""${1:-none}"" = ""$expected"" ] || exit 40
success=1
restore
echo LIBRARY_INSTALLED
/system/bin/ls -lZ ""$target""
state
[ ""$(state)"" = ""$original"" ] && echo RESTORED_EXACT || echo RESTORE_MISMATCH
");
        }
        public static string RemoveDiagnosticLibrary() {
            return RunShell(@"set -u
[ ""$(id -u)"" = 0 ] && [ ""$(cat /proc/self/attr/current)"" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ ""$path"" != /system ] || printf '%s %s %s\n' ""$dev"" ""$fs"" ""$options""; done < /proc/mounts; }
original=$(state)
case ""$original"" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
target=/system/lib64/libx2d_preview_probe.so
set -- $(/system/bin/sha256sum ""$target"")
[ ""${1:-none}"" = 8735037ab1fa050f27e155acf9eee85719d31588e72d82815b824a9e62ba9106 ] || exit 35
restore() { case ""$(state)"" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
trap restore EXIT HUP INT TERM
( /system/bin/sleep 5; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system || exit 36
/system/bin/rm ""$target"" || exit 37
restore
[ ! -e ""$target"" ] && [ ! -L ""$target"" ] && echo LIBRARY_REMOVED
state
[ ""$(state)"" = ""$original"" ] && echo RESTORED_EXACT || echo RESTORE_MISMATCH
");
        }
        public static string[] RunShellBatch(string[] scripts, string requiredMarker) {
            if (scripts == null || scripts.Length == 0 || scripts.Length > 256) throw new UsbFailure("ADB_BATCH_LIMIT");
            foreach (string script in scripts) if (script == null || Encoding.UTF8.GetByteCount("shell:" + script + "\0") > 4096) throw new UsbFailure("ADB_COMMAND_LIMIT");
            using (AdbUsbCheck s = new AdbUsbCheck()) {
                s.Open(new ReadResult());
                s.Send("CNXN", 0x01000000, 4096, Encoding.ASCII.GetBytes("host::\0"));
                Packet p = s.Receive();
                // A previous closed stream can leave a final CLSE queued on USB.
                // Never accept AUTH or an arbitrary packet as a connection reply.
                for (int stale = 0; p.Command == Cmd("CLSE") && stale < 4; stale++) p = s.Receive();
                if (p.Command == Cmd("AUTH")) throw new UsbFailure("ADB_AUTHORIZATION_REQUIRED");
                if (p.Command != Cmd("CNXN")) throw new UsbFailure("ADB_CONNECT");
                List<string> outputs = new List<string>();
                uint local = 0;
                foreach (string script in scripts) {
                    local++;
                    s.Send("OPEN", local, 0, Encoding.UTF8.GetBytes("shell:" + script + "\0"));
                    uint remote = 0;
                    StringBuilder output = new StringBuilder();
                    bool closed = false;
                    for (int i = 0; i < 128; i++) {
                        p = s.Receive();
                        if (p.Command == Cmd("CLSE") && p.B < local) continue;
                        if (p.B != local) throw new UsbFailure("ADB_STREAM_ID");
                        if (p.Command == Cmd("OKAY")) { remote = p.A; continue; }
                        if (p.Command == Cmd("WRTE")) {
                            if (remote == 0 || p.A != remote) throw new UsbFailure("ADB_REMOTE_ID");
                            if (output.Length + p.Data.Length > 8192) throw new UsbFailure("ADB_OUTPUT_LIMIT");
                            output.Append(Encoding.UTF8.GetString(p.Data));
                            s.Send("OKAY", local, remote, new byte[0]); continue;
                        }
                        if (p.Command == Cmd("CLSE")) {
                            s.Send("CLSE", local, p.A, new byte[0]); closed = true; break;
                        }
                        throw new UsbFailure("ADB_STREAM_PACKET");
                    }
                    if (!closed) throw new UsbFailure("ADB_PACKET_LIMIT");
                    if (!String.IsNullOrEmpty(requiredMarker) && !output.ToString().Contains(requiredMarker)) throw new UsbFailure("ADB_BATCH_COMMAND_FAILED");
                    outputs.Add(output.ToString());
                }
                return outputs.ToArray();
            }
        }
        private static string RunShell(string script) {
            using(AdbUsbCheck s=new AdbUsbCheck()) {
                s.Open(new ReadResult());s.Send("CNXN",0x01000000,4096,Encoding.ASCII.GetBytes("host::\0"));
                Packet p=s.Receive();
                if(p.Command==Cmd("AUTH"))return "ADB_AUTHORIZATION_REQUIRED";
                if(p.Command!=Cmd("CNXN"))throw new UsbFailure("ADB_CONNECT");
                string command="shell:"+script+"\0";
                s.Send("OPEN",1,0,Encoding.ASCII.GetBytes(command));uint remote=0;StringBuilder result=new StringBuilder();
                for(int i=0;i<64;i++){
                    p=s.Receive();
                    if(p.B!=1)throw new UsbFailure("ADB_STREAM_ID");
                    if(p.Command==Cmd("OKAY")){remote=p.A;continue;}
                    if(p.Command==Cmd("WRTE")){
                        if(remote==0||p.A!=remote)throw new UsbFailure("ADB_REMOTE_ID");
                        if(result.Length+p.Data.Length>8192)throw new UsbFailure("ADB_OUTPUT_LIMIT");
                        result.Append(Encoding.UTF8.GetString(p.Data));s.Send("OKAY",1,remote,new byte[0]);continue;
                    }
                    if(p.Command==Cmd("CLSE")){s.Send("CLSE",1,p.A,new byte[0]);return "ADB_CONNECTED\n"+result.ToString();}
                    throw new UsbFailure("ADB_STREAM_PACKET");
                }throw new UsbFailure("ADB_PACKET_LIMIT");
            }
        }
        public void Dispose() {
            if (usb != IntPtr.Zero) {
                if (!WinUsb_Free(usb)) { released = false; releaseError = Marshal.GetLastWin32Error(); }
                usb = IntPtr.Zero;
            }
            if (file != null) file.Dispose();
        }
    }
}
