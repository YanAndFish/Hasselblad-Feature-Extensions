"""固定 Qt RCC v1 纯文本资源编码。"""
import struct,zlib
def qhash(text):
    h = 0
    for c in text:
        h = (h << 4) + ord(c)
        h ^= (h & 0xF0000000) >> 23
        h &= 0x0FFFFFFF
    return h


def rcc(files):
    """Qt 5.5.1 v1，固定根目录；以原厂散列排序规则生成最小覆盖资源。"""
    root = {"name": "", "children": {}}
    for path, text in files.items():
        node = root
        parts = path.strip("/").split("/")
        for part in parts:
            node = node.setdefault("children", {}).setdefault(part, {"name": part})
        node["text"] = text
    nodes = [root]
    for node in nodes:
        if "children" in node:
            children = sorted(node["children"].values(), key=lambda x: (qhash(x["name"]), x["name"]))
            node["first"] = len(nodes)
            nodes.extend(children)
    names = bytearray()
    payload = bytearray()
    tree = bytearray()
    for node in nodes:
        name = node["name"]
        offset = len(names)
        names += struct.pack(">HI", len(name), qhash(name)) + name.encode("utf-16-be")
        if "children" in node:
            tree += struct.pack(">IHII", offset, 2, len(node["children"]), node["first"])
        else:
            text = node["text"].encode("utf-8")
            compressed = struct.pack(">I", len(text)) + zlib.compress(text, 9)
            tree += struct.pack(">IHHHI", offset, 1, 0, 1, len(payload))
            payload += struct.pack(">I", len(compressed)) + compressed
    return b"qres" + struct.pack(">IIII", 1, 20 + len(payload) + len(names), 20, 20 + len(payload)) + payload + names + tree


