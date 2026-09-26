"""时钟和右侧 I/O 的局部布线扩展，只接收离线数据库和配置帧。

trace 给出结构连接，不模拟 BUFG/BUFH 的使能、选路、原语反相或 I/O 电气行为。
数据库中穿过原语的 always ppip 仍须结合该原语配置单独核对。
"""

from collections import defaultdict


def routing_class(base):
    """接收 fpga_routing.Routing，避免导入时读文件或创建缓存。"""

    class ClockIoRouting(base):
        EXTENDED_KINDS = {
            "HCLK_L", "HCLK_R", "HCLK_CMT_L",
            "CLK_HROW_BOT_R", "CLK_HROW_TOP_R",
            "CLK_BUFG_BOT_R", "CLK_BUFG_TOP_R", "CLK_BUFG_REBUF",
            "RIOI", "RIOI_SING", "RIOI_TBYTESRC", "RIOI_TBYTETERM",
            "RIOB18", "RIOB18_SING",
        }

        def features(self, name):
            if name in self.active_features:
                return self.active_features[name]
            segment = self.grid[name].get("bits", {}).get("CLB_IO_CLK", {})
            alias = segment.get("alias")
            if not alias:
                return super().features(name)
            shift = alias["start_offset"] * 32
            count = segment["words"] * 32
            values = self.segment_values(name)
            reverse_sites = {value: key for key, value in alias["sites"].items()}
            found = []
            for feature, entries in self.segbits[alias["type"]].items():
                # 别名只允许使用本 tile 的有效字，不能借邻近 tile 的配置补齐。
                if not all(shift <= bit < shift + count for _, bit, _ in entries):
                    continue
                if not all(bool(values[frame] & (1 << (bit - shift))) == value
                           for frame, bit, value in entries):
                    continue
                fields = feature.split(".")
                fields[0] = reverse_sites.get(fields[0], fields[0])
                found.append(".".join(fields))
            self.active_features[name] = found
            return found

        def pips(self, name):
            if name in self.selected:
                return self.selected[name], self.selected_back[name]
            kind = self.grid[name]["type"]
            if kind not in self.EXTENDED_KINDS:
                return super().pips(name)
            valid = {}
            for pip in self.tile_types[kind]["pips"].values():
                valid[pip["dst_wire"] + "." + pip["src_wire"]] = pip
                if str(pip["is_directional"]) == "0":
                    valid[pip["src_wire"] + "." + pip["dst_wire"]] = pip
            forward, back = defaultdict(list), defaultdict(list)
            for feature in self.features(name):
                # IN_USE、反相和 buffer 使能标志不是 wire-to-wire PIP。
                if feature not in valid:
                    continue
                pip = valid[feature]
                src, dest = pip["src_wire"], pip["dst_wire"]
                if dest not in forward[src]:
                    forward[src].append(dest)
                    back[dest].append(src)
                if str(pip["is_directional"]) == "0" and src not in forward[dest]:
                    forward[dest].append(src)
                    back[src].append(dest)
            self.selected[name], self.selected_back[name] = forward, back
            return forward, back

    return ClockIoRouting
