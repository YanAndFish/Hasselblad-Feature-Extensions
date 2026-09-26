using System;
using System.Text;
using System.Web.Script.Serialization;

namespace HasselbladDebug {
    public static class Program {
        private static int checks;
        private static void Require(bool value) { checks++; if (!value) throw new UsbFailure("USB_SELFTEST_FAILED"); }
        private static bool Denied(Action action) { try { action(); return false; } catch (UsbFailure) { return true; } }
        private static object SelfTest() {
            checks = 0;
            // 人工端点地址；不是实机描述符采集。
            byte[] control = ReadOnlyProtocol.ControlPipes(new byte[] { 3,4,0x84,0x85 });
            Require(control[0] == 0x85 && control[1] == 4);
            foreach (byte[] bad in new byte[][] { new byte[0], new byte[] { 3,0x84 }, new byte[] { 3,4,0x84 },
                new byte[] { 3,0x84,4,0x85 }, new byte[] { 3,3,0x84,0x85 }, new byte[] { 0,4,0x84,0x85 }, new byte[] { 0x13,4,0x84,0x85 } })
                Require(Denied(delegate { ReadOnlyProtocol.ControlPipes(bad); }));
            Require(Convert.ToBase64String(ReadOnlyProtocol.Request(27, 1)) == "BAAIBQUBAAIbAA==");
            Require(Convert.ToBase64String(ReadOnlyProtocol.Request(28, 2)) == "BAAIBQUCAAIcAA==");
            foreach (ushort id in new ushort[] { 25, 87, 88, 61 }) {
                byte[] request = ReadOnlyProtocol.Request(id, 3);
                Require(request.Length == 10 && request[7] == 2 && request[8] == id && request[9] == 0);
            }
            foreach (ushort id in new ushort[] { 0, 1, 3, 22, 74, 112, 139, 65535 }) Require(Denied(delegate { ReadOnlyProtocol.Request(id, 1); }));
            Require(Denied(delegate { ReadOnlyProtocol.Request(27, 0); }));
            byte[] packet = new byte[1024];
            byte[] prefix = new byte[] { 3,0,5,8,5,1,0,130,105,49 };
            Array.Copy(prefix, packet, prefix.Length);
            Require(Encoding.ASCII.GetString(new ReadOnlyProtocol.Reply(1).Add(packet,1024)) == "i1");
            foreach (int field in new int[] { 0,2,3,4,5,7 }) {
                byte[] bad = (byte[])packet.Clone(); bad[field] = 255;
                Require(Denied(delegate { new ReadOnlyProtocol.Reply(1).Add(bad,10); }));
            }
            ReadOnlyProtocol.Reply split = new ReadOnlyProtocol.Reply(1);
            byte[] first = new byte[1024]; Array.Copy(prefix,first,8); first[4] = 0;
            for (int index = 8; index < 260; index++) first[index] = (byte)'a';
            Require(split.Add(first,1024) == null);
            byte[] last = new byte[] { 3,0,5,8,2,(byte)'b',(byte)'c' };
            byte[] combined = split.Add(last,last.Length);
            Require(combined.Length == 254 && combined[0] == (byte)'a' && combined[252] == (byte)'b' && combined[253] == (byte)'c');
            Require(Denied(delegate { split.Add(last,last.Length); }));
            Require(Denied(delegate { new ReadOnlyProtocol.Reply(1).Add(new byte[4],4); }));
            string[] texts = { "S6,v4.2.0", "i1", "i2", "fbff0000000000000", "i1", "i1" };
            int calls = 0;
            ReadResult collected = new ReadResult();
            ReadOnlyProtocol.Collect(delegate(ushort id, ushort seq) { calls++; Require(seq == calls); return Encoding.ASCII.GetBytes(texts[seq - 1]); }, collected);
            Require(calls == 6 && collected.Values.Count == 6 && collected.Values[2].Id == 25 && collected.Values[5].Id == 61);
            // 未知版本、未运行、未知参数值都必须停止，不能先完成整批再只在界面隐藏。
            foreach (string[] invalid in new string[][] {
                new string[] { "S6,v4.3.0", "1" }, new string[] { "S6,4.2.0", "1" },
                new string[] { "i0", "2" }, new string[] { "i01", "2" }, new string[] { "i-1", "3" },
                new string[] { "f7ff0000000000000", "4" }, new string[] { "f7ff8000000000000", "4" },
                new string[] { "r1", "4" }, new string[] { "i2", "5" }, new string[] { "i2", "6" } }) {
                int stop = int.Parse(invalid[1]); calls = 0;
                Require(Denied(delegate { ReadOnlyProtocol.Collect(delegate(ushort id, ushort seq) {
                    calls++; return Encoding.ASCII.GetBytes(seq == stop ? invalid[0] : texts[seq - 1]);
                }, new ReadResult()); }));
                Require(calls == stop);
            }
            Require(ReadOnlyProtocol.ReviewedValue(87, Encoding.ASCII.GetBytes("f3fb5555555555555")));
            Require(!ReadOnlyProtocol.ReviewedValue(87, Encoding.ASCII.GetBytes("f3fb999999999999a")));
            Require(!ReadOnlyProtocol.ReviewedValue(25, Encoding.ASCII.GetBytes("i3601")));
            return new { Passed = true, Opened = false, Requests = 0, Checks = checks };
        }
        public static int Main(string[] arguments) {
            Console.OutputEncoding = new UTF8Encoding(false);
            JavaScriptSerializer json = new JavaScriptSerializer();
            try {
                if (arguments.Length > 1) throw new UsbFailure("USB_MODE_DENIED");
                string mode = arguments.Length == 0 ? "metadata" : arguments[0];
                object result;
                switch (mode) {
                    case "metadata": result = WinUsbReadOnly.Probe(); break;
                    case "snapshot": result = WinUsbReadOnly.ReadSnapshot(); break;
                    case "selftest": result = SelfTest(); break;
                    default: throw new UsbFailure("USB_MODE_DENIED");
                }
                Console.WriteLine(json.Serialize(result));
                return 0;
            } catch (UsbFailure error) {
                Console.WriteLine(json.Serialize(new { Ok = false, Error = error.Code, Win32 = error.Win32, Opened = false, Requests = 0 }));
                return 1;
            } catch {
                Console.WriteLine("{\"Ok\":false,\"Error\":\"USB_HELPER_FAILED\",\"Opened\":false,\"Requests\":0}");
                return 1;
            }
        }
    }
}
