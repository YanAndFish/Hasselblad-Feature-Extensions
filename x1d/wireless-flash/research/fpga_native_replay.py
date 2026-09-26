"""将既有离线采样模型转成 C，供全尺寸周期复核；没有设备访问。"""

import ast
import re


def c_half_step(python_source, name):
    """只接受 compile_half_step 实际产生的有限 Python 语法。"""
    if name not in ("positive", "negative"):
        raise ValueError("无效函数名")
    tree = ast.parse(python_source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("必须为单个采样函数")

    def expression(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            if not 0 <= node.value < (1 << 64):
                raise ValueError("整数超出 uint64 范围")
            return "UINT64_C(%d)" % node.value
        if isinstance(node, ast.Name) and re.fullmatch(r"v|u|t[0-9]+", node.id):
            return node.id
        if isinstance(node, ast.Subscript):
            if not isinstance(node.value, ast.Name) or node.value.id not in ("v", "u"):
                raise ValueError("非法数组")
            if not isinstance(node.slice, ast.Constant) or type(node.slice.value) is not int or node.slice.value < 0:
                raise ValueError("非法索引")
            return "%s[%d]" % (node.value.id, node.slice.value)
        if isinstance(node, ast.BinOp):
            operators = {ast.LShift: "<<", ast.RShift: ">>", ast.BitAnd: "&",
                         ast.BitOr: "|", ast.BitXor: "^"}
            if type(node.op) not in operators:
                raise ValueError("不支持的运算")
            return "(%s %s %s)" % (expression(node.left), operators[type(node.op)], expression(node.right))
        if isinstance(node, ast.IfExp):
            return "(%s ? %s : %s)" % (expression(node.test), expression(node.body), expression(node.orelse))
        raise ValueError("不支持的表达式")

    output = ["static void %s(uint64_t *v) {" % name]
    for statement in tree.body[0].body:
        if isinstance(statement, ast.Pass):
            continue
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            raise ValueError("不支持的语句")
        target = statement.targets[0]
        if isinstance(target, ast.Name) and target.id == "u" and isinstance(statement.value, ast.Tuple):
            output.append("uint64_t u[] = {%s};" % ",".join(expression(x) for x in statement.value.elts))
        elif isinstance(target, ast.Name) and re.fullmatch(r"t[0-9]+", target.id):
            output.append("uint64_t %s = %s;" % (target.id, expression(statement.value)))
        elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == "v":
            output.append("%s = %s;" % (expression(target), expression(statement.value)))
        else:
            raise ValueError("不支持的赋值")
    return "\n".join(output + ["}"])


def replay_source(snapshot, cases, compile_half_step, freeze, check_vectors=()):
    """生成固定输入的本地程序；输出状态变化和最终向量，不生成物理时间。"""
    positive = compile_half_step(snapshot, snapshot.states, snapshot.indices, False)[1]
    negative = compile_half_step(snapshot, snapshot.states, snapshot.indices, True)[1]
    source = ["#include <stdint.h>", "#include <inttypes.h>", "#include <stdio.h>",
              c_half_step(positive, "positive"), c_half_step(negative, "negative")]
    count = len(snapshot.indices)
    source.append("int main(void) {")
    for number, vector in enumerate(check_vectors):
        if len(vector) != count or any(type(x) is not int or x not in (0, 1) for x in vector):
            raise ValueError("检查向量必须逐项给出全部状态")
        source.append("{ uint64_t v[] = {%s};" % ",".join(map(str, vector)))
        for phase in ("positive", "negative"):
            source.append('%s(v); printf("CHECK,%d,%s,");' % (phase, number, phase))
            source.append('for (int i=0;i<%d;i++) printf("%%u",(unsigned)v[i]); puts("");' % count)
        source.append("}")
    for number, case in enumerate(cases):
        cycles = case["cycles"]
        if type(cycles) is not int or not 0 < cycles < (1 << 32):
            raise ValueError("无效周期数")
        initial = {freeze(node): value for node, value in case["initial_boundary_values"]}
        vector = snapshot.initial_values(initial)
        probes = [snapshot.indices[freeze(node)] for node in case["probes"]]
        if not probes:
            raise ValueError("缺少观测点")
        updates = {}
        for item in case["boundary_updates"]:
            tick = item["cycle"]
            if type(tick) is not int or not 0 <= tick < cycles:
                raise ValueError("边界更新时间越界")
            for node, value in item["values"]:
                node = freeze(node)
                if node not in snapshot.boundaries or type(value) is not int or value not in (0, 1):
                    raise ValueError("只能更新已显式声明的单比特边界")
                updates.setdefault(tick, []).append((snapshot.indices[node], value))
        source.append("{ uint64_t v[] = {%s};" % ",".join(map(str, vector)))
        source.append("uint64_t prior[%d] = {%s};" % (len(probes), ",".join(["2"] * len(probes))))
        source.append("for (uint32_t tick=0;tick<%d;tick++) { switch (tick) {" % cycles)
        for tick, values in sorted(updates.items()):
            source.append("case %d: %s break;" % (tick, " ".join("v[%d]=%d;" % pair for pair in values)))
        source.append("default: break; } positive(v); negative(v);")
        source.append("if (%s) {" % " || ".join("prior[%d]!=v[%d]" % (i, index) for i, index in enumerate(probes)))
        source.append('printf("EVENT,%d,%%" PRIu32 ",",tick);' % number)
        for i, index in enumerate(probes):
            source.append('prior[%d]=v[%d]; printf("%%u",(unsigned)v[%d]);' % (i, index, index))
        source.append('puts(""); } }')
        source.append('printf("FINAL,%d,");' % number)
        source.append('for (int i=0;i<%d;i++) printf("%%u",(unsigned)v[i]); puts(""); }' % count)
    return "\n".join(source + ["return 0; }"]) + "\n"
