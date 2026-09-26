// 界面资源仅在已验签的进程内解封。密钥在原生程序内，不能抵抗管理员动态提取。
const std = @import("std");
const config = @import("resource_seal_config.zig");
const Aead = std.crypto.aead.chacha_poly.XChaCha20Poly1305;
const magic = "HBLRSC01";
const overhead = magic.len + Aead.nonce_length + Aead.tag_length;
const max_size = 32 * 1024 * 1024;

export fn hbl_resource_open(out: [*]u8, capacity: usize, sealed: [*]const u8, length: usize) c_int {
    if (length <= overhead or length > max_size + overhead) return 0;
    const n = length - overhead;
    if (capacity < n or !std.mem.eql(u8, sealed[0..magic.len], magic)) return 0;
    const nonce: [24]u8 = sealed[8..32].*;
    const tag: [16]u8 = sealed[length - 16 ..][0..16].*;
    Aead.decrypt(out[0..n], sealed[32..][0..n], tag, magic, nonce, config.key) catch {
        std.crypto.utils.secureZero(u8, out[0..n]);
        return 0;
    };
    if (n < 20 or !std.mem.eql(u8, out[0..4], "qres")) {
        std.crypto.utils.secureZero(u8, out[0..n]);
        return 0;
    }
    return @intCast(n);
}

// 只导出在本地打包工具中，ARM 发行库不包含加密入口。
fn pack(out: [*]u8, capacity: usize, plain: [*]const u8, length: usize, nonce: *const [24]u8) callconv(.C) c_int {
    if (length < 20 or length > max_size or capacity < length + overhead) return 0;
    @memcpy(out[0..8], magic);
    @memcpy(out[8..32], nonce);
    Aead.encrypt(out[32..][0..length], out[32 + length ..][0..16], plain[0..length], magic, nonce.*, config.key);
    return @intCast(length + overhead);
}
comptime {
    if (config.pack_enabled) @export(pack, .{ .name = "hbl_resource_pack" });
}
