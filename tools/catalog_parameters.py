"""从固定 4.2.0 Qt 元数据提取枚举；名称存在不等于实机可读。"""
from inspect_phocus import Binary, ROOT
import json
import struct


def run():
    binary = Binary()
    data = binary.read(0x1a68a8, 7324)
    strings = binary.read(0x1a1010, 22680)
    def string(index):
        offset, size = struct.unpack_from("<II", strings, index * 8)
        return strings[offset:offset + size].decode("ascii")
    header = struct.unpack_from("<14I", data)
    if header[0] != 10 or header[8:10] != (72, 14):
        raise ValueError("固定元数据布局不符")
    enums = {}
    for i in range(header[8]):
        name, alias, flags, count, offset = struct.unpack_from("<5I", data, (header[9] + i * 5) * 4)
        values = [struct.unpack_from("<II", data, (offset + n * 2) * 4) for n in range(count)]
        enums[string(name)] = [{"name": string(k), "id": value} for k, value in values]
    parameters = enums["eCamDevParam"]
    for parameter in parameters:
        value = parameter["id"]
        parameter["httpLoopIncludesId"] = 1 <= value < len(parameters) - 1
        parameter["readCaseAddress"] = hex(0x91128 + struct.unpack("<H", binary.read(0x195538 + (value - 2) * 2, 2))[0] * 4) if 2 <= value <= 168 else None
    # 仅更新当前发行目录已经收录的参数，不自动扩大发行范围。
    current = json.loads((ROOT / "research/parameter-catalog.json").read_text(encoding="utf-8"))
    included = {p["id"] for p in current["parameters"]}
    parameters = [p for p in parameters if p["id"] in included]
    result = {"source": "official-firmware-static", "firmware": "4.2.0", "binarySha256": "56c9a777fb9c5ed228fc32b47013822b34bd9109822871089700d23dd40a1516",
              "enumAddress": "0x1a68a8", "stringsAddress": "0x1a1010", "handlerAddress": "0xdc6b8",
              "parameters": parameters, "parameterTypes": enums["eParameterType"]}
    (ROOT / "research/parameter-catalog.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for p in parameters:
        print(p["id"], p["name"], p["readCaseAddress"], "HTTP-loop" if p["httpLoopIncludesId"] else "outside-loop")


if __name__ == "__main__":
    run()
